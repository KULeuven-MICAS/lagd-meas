# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Open-loop VCO spectrum, phase noise and jitter: VcoLUT (lib/vco_lut.py) sets the VCO codes for a frequency
# and Kvco from the lookup table, the SMU holds Vctrl at the predicted operating point, and the R&S FSV signal
# analyzer measures the output pad: one averaged trace per span, stitched into the full phase-noise curve
# (pll_util.phase_noise_from_traces) and integrated (pll_util.integrate_phase_noise) over the offsets;
# RBW = span / pll_spectrum.RBW_SPAN_RATIO, VBW = 3 RBW, RMS detector, power averaging and linear video filter, as in
# lib/pll_spectrum.py. The averaged traces are saved too, for plotting the spectrum.
#
# Output path: pll_clk_o_en = 1, the VCO divided by 2**set_div_freq only (no external divider), with
# set_div_freq the smallest that brings the pad frequency at or below `out_f_max`. Division keeps the time
# jitter; the phase noise and phase jitter are also given referred to the VCO (+20 log10(N), x N).
#
# A free-running VCO wanders: close-in offsets (< ~10 kHz) are dominated by drift during the averaged sweeps,
# so the default offsets start at 10 kHz.
#
# Results (plotted in sw/tools/notebooks/vco_spectrum.ipynb):
#   results/vco/vco_spectrum_<sample>_<stamp>.csv          one row per setting: carrier, jitter
#   results/vco/vco_spectrum_<sample>_<stamp>_traces.csv   the averaged analyzer traces (one row per trace point)
#
# Tests:
#   view_vco(f, kvco, sample)                  # set the VCO + analyzer and leave it running for manual evaluation
#   capture_spectrum(f, kvco, sample, center, span, averages)  # set VCO + Vctrl, averaged spectrum -> vco_capture_*.csv
#   measure_vco_spectrum(f, kvco, sample)      # one setting
#   vco_spectrum_sweep(targets, sample)        # a list of (f, kvco) targets, one CSV pair for all
#   manual_vctrl_sweep(f, kvco, sample, vctrls)  # Vctrl from a battery + potentiometer, waits for you at each step
#   vco_pnm_sweep(points, sample)              # Vctrl tuned by hand to a target f_vco, spectra + analyzer Phase Noise
#                                              # mode; points: matched_points() (PLL runs) + ofat_points() (one factor
#                                              # at a time)
#

import csv
import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut, vco_measure
from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keithley_smu_2450 import KeithleySMU2450
from sw.lib.lab_instruments.drivers.rohde_schwarz_fsv_spectrum import RohdeSchwarzFSVSpectrum
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import VCO_CHARAC_CFG
from sw.lib.pll_spectrum import PNM_AVERAGES, PNM_COLUMNS, RBW_SPAN_RATIO, TRACE_FIELDS, measure_phase_noise_mode, \
    offsets_for, trace_rows
from sw.lib.pll_spectrum import RESULTS_DIR as PLL_RESULTS_DIR
from sw.lib.pll_util import integrate_phase_noise, phase_noise_from_traces

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Offset [Hz] -> analyzer span [Hz] of the trace covering the curve up to that offset; the offsets are also the
# integration band of the jitter (as pll_spectrum.OFFSET_SPAN_MAP).
VCO_OFFSET_SPAN_MAP = {
    1e4: 21e3,
    1e5: 210e3,
    5e5: 2.1e6,
    1e6: 2.1e6,
}
# manual_vctrl_sweep: default Vctrl steps [V], the operating window of the lookup table (vco_lut.VCTRL_WINDOW).
MANUAL_VCTRLS = (0.50, 0.55, 0.60, 0.65, 0.70)
# Highest pad frequency: the colleague's PLL jitter runs used ~37.5 MHz on this output.
OUT_F_MAX = 50e6

SPECTRUM_COLUMNS = (["time", "lut_csv", "f_target", "kvco_target"] + list(vco_lut.LUT_FIELDS)
                    + ["vctrl_pred", "kvco_pred", "vctrl_set", "f_vco_pred", "vctrl_meas", "set_div_freq",
                       "total_div", "f_out_meas",
                       "f_vco_meas", "f_dev_pct", "n_averages", "detector", "average_type", "video_filter",
                       "offset_min", "offset_max", "time_jitter_trace_ps", "phase_jitter_trace_out_mrad",
                       "phase_jitter_trace_vco_mrad"]
                    + list(pll_setup.SUPPLY_COLUMNS) + ["status"])
# One row per trace point; `offset` = freq - center (the carrier), power in dBm as on the analyzer.
TRACE_COLUMNS = ["f_target", "vctrl_set", "total_div", "span", "rbw", "vbw", "center", "freq", "offset", "power_dbm"]
# vco_pnm_sweep: open-loop phase noise, Vctrl from a battery + potentiometer tuned by hand to a target f_vco.
# Points of two kinds, each with a `factor` label (one or more, space separated; the notebook groups on it):
# 1. PLL-matched (matched_points): the PLL measurements to repeat open loop, (results/pll CSV, column values a row
#    must have, factor): per locked setting its VCO codes, internal divider and f_vco, to overlay on the PLL curve.
#    c9 min 9 at 760 MHz (max 0 / 8 / 12 / 14 / 15, the loop-gain sweep: codes and f_vco are the same for every Icp,
#    so one Icp; also the max-code factor) and the 1 GHz max-code sweep (the table's setting per max code: min and
#    coarse change too, so no factor of its own).
PLL_MATCHED_RUNS = (
    ("pll_test_current_max_S5_20261020_200224.csv", dict(set_current=4), "vco_current_max"),
    ("pll_test_current_max_S5_20261020_150031.csv", {}, "pll_1GHz"),
)
# 2. One factor at a time (ofat_points) around OFAT_BASE, every point on the same internal divider OFAT_SET_DIV_FREQ
#    (/16: the pad at 45-62.5 MHz for 720 MHz-1 GHz). (factor, values, f_vco [Hz] held fixed; None: the factor is
#    f_vco itself): vco_current_min at 900 MHz, vco_tune_coarse (ring length) at 820 MHz (c11, c9, c7 all reach it),
#    f_vco inside the c9 band (the ring current). The base point at 900 MHz is shared by min and f_vco.
OFAT_BASE = dict(vco_tune_coarse=9, vco_current_min=9, vco_current_max=0)
OFAT_SET_DIV_FREQ = 4
OFAT_FACTORS = (
    ("vco_current_min", (5, 9, 13), 900e6),
    ("vco_tune_coarse", (11, 9, 7), 820e6),
    ("f_vco", (720e6, 800e6, 900e6, 1000e6), None),
)
# Live view while tuning: span on the pad [Hz] around the target carrier, moving average over TUNE_AVERAGES sweeps
# (the free-running carrier wanders). The Phase Noise mode starts at the carrier found in the widest spectrum
# (carrier_of: power-weighted centre and total power within +-CARRIER_BAND [Hz] of the peak, so a carrier smeared by the
# wander counts in full), verified within PNM_FREQ_TOLERANCE [Hz] and PNM_LEVEL_TOLERANCE [dB] and tracked during the
# sweep (2026-10-21: the carrier moved ~1 MHz on the pad between captures and read ~10 dB low in a 5 kHz RBW).
TUNE_SPAN = 10e6
TUNE_AVERAGES = 10
CARRIER_BAND = 1e6
PNM_FREQ_TOLERANCE = 5e6
PNM_LEVEL_TOLERANCE = 20.0
# After tuning, before the Phase Noise mode: one averaged spectrum per span [Hz] around the carrier, RBW = span /
# RBW_SPAN_RATIO (40 MHz: +-20 MHz, RBW ~50 kHz, the whole offset band; 5 MHz: RBW ~7 kHz, the spurs close in),
# RMS detector + power averaging over SPECTRUM_AVERAGES sweeps. Saved as kind "spectrum" (freq absolute, dBm).
SPECTRUM_SPANS = (40e6, 5e6)
SPECTRUM_AVERAGES = 10
# vctrl_source="smu": Vctrl from the SMU (meas_setup.yaml smu_vctrl) instead of the potentiometer, tuned automatically
# (smu_tune): the carrier of an averaged spectrum (span SPECTRUM_SPANS[0], TUNE_SMU_AVERAGES sweeps) moved onto the
# target by secant steps in Vctrl (first step with |Kvco| TUNE_KVCO0 [Hz/V]) until within TUNE_TOL_REL of it, at most
# TUNE_MAX_STEPS steps, Vctrl kept inside SMU_VCTRL_RANGE [V] (a target outside: status "unreachable").
SMU_VCTRL_RANGE = (0.30, 0.75)
SMU_SETTLE = 0.5
TUNE_SMU_AVERAGES = 5
TUNE_KVCO0 = 2e9
TUNE_TOL_REL = 1e-3
TUNE_MAX_STEPS = 10
MIN_TUNE_CARRIER_DBM = -20.0
# f_vco_target: the f_vco to tune to (the PLL's for matched points); vctrl_hint: where to start (the PLL's Vctrl, or
# the lookup table's for the OFAT points); vctrl_pll / carrier_pll_dbm / jitter_pll_ps: the PLL run (NaN for OFAT).
POINT_FIELDS = (["factor", "pll_csv", "pll_match", "f_vco_target", "vctrl_hint", "vctrl_pll", "carrier_pll_dbm",
                 "jitter_pll_ps"] + list(vco_lut.LUT_FIELDS) + ["set_div_freq", "total_div", "f_pad"])
# vdd_set / pll_vdd / pll_i / pll_p: the PLL supply when the sweep is given one (pll_test_vdd), else empty / NaN
VCO_PNM_COLUMNS = (["time"] + POINT_FIELDS
                   + ["vctrl_source", "vctrl_set", "tune_steps", "vctrl_read", "f_pad_spectrum", "carrier_spectrum_dbm",
                      "f_vco_meas", "f_dev_pct", "vdd_set"] + list(pll_setup.SUPPLY_COLUMNS) + PNM_COLUMNS
                   + ["status"])
# Traces: the averaged spectra ("spectrum", freq absolute, dBm), the analyzer's L(f) curve ("L_pnmode", freq = offset,
# dBc/Hz on the pad) and its spur list ("pnm_spur", freq = offset, dBc)
VCO_PNM_TRACE_COLUMNS = ["f_vco_target"] + list(vco_lut.LUT_FIELDS) + ["set_div_freq", "vdd_set"] + TRACE_FIELDS
# capture_spectrum: one row per trace point of an averaged spectrum.
CAPTURE_COLUMNS = (["time", "note", "f_target", "kvco_target"] + list(vco_lut.LUT_FIELDS)
                   + ["vctrl_pred", "vctrl_meas", "kvco_pred", "set_div_freq", "total_div", "center", "span", "rbw",
                      "vbw", "averages", "detector", "average_type", "video_filter"] + list(pll_setup.SUPPLY_COLUMNS)
                   + ["freq", "level_dbm"])


def spectrum_cfg(f_vco, out_f_max=OUT_F_MAX):
    """VCO_CHARAC_CFG (open loop, Vctrl from the pad) on the direct output: f_vco / 2**set_div_freq <= out_f_max."""
    set_div_freq = next((n for n in range(8) if f_vco / 2 ** n <= out_f_max), 7)  # 3-bit field
    return dict(VCO_CHARAC_CFG, pll_clk_o_en=1, set_div_freq=set_div_freq)


def open_spectrum():
    config = vco_measure.load_instr_cfg()
    return RohdeSchwarzFSVSpectrum(inst.BaseSpectrumAnalyzerData.from_mapping(config["spectrum_analyzer"]))


def keep_remote_alive():
    """Workaround from pll_integrated_jitter.py: open and close a dummy session to reset the analyzer's 300 s
    remote-control timer."""
    try:
        open_spectrum()._open_resource().close()
    except pyvisa.VisaIOError as e:
        logging.warning("Failed to open/close dummy session: %s", e)


def find_carrier(spectrum, f_est, rel_span=0.3, steps=(1e-2, 1e-4)):
    """Center the analyzer on the carrier near `f_est` [Hz]; returns the carrier frequency [Hz].

    The lookup table is a few % off on another day, too far for center_on_fundamental's 2.1 kHz search:
    first a peak search over `rel_span` * f_est, then narrower spans (`steps` relative to the found carrier),
    then center_on_fundamental for the exact peak and the reference level.
    """
    spectrum.set_sweep_mode(continuous=False)
    spectrum.set_trace_mode(trace=1, mode="WRITe")
    f = f_est
    for span in [rel_span * f_est] + [s * f_est for s in steps]:
        spectrum.set_center_frequency(f)
        spectrum.set_span(span)
        spectrum.set_rbw(max(span / 1000, 1.0))
        spectrum.trigger_single_sweep(wait=True)
        spectrum.peak_search(marker=1)
        f = float(spectrum.query("CALC:MARK1:X?").strip())
        logging.info("  carrier search, span %.3g Hz: peak at %.6f MHz", span, f / 1e6)
    spectrum.center_on_fundamental(center_freq=f, search_span=2.1e3)
    return float(spectrum.query("FREQ:CENT?").strip())


def measure_pad_spectrum(spectrum, f_out_est, total_div, row, csv_path, n_averages=10, offset_span_map=None):
    """Find the carrier near `f_out_est` [Hz] on the output pad, take one averaged trace per span of
    `offset_span_map` and integrate the phase-noise curve from these traces over its offsets (jitter on the pad and
    referred to the VCO, x `total_div`).

    Fills `row` (carrier, jitter, analyzer method, status "ok") and appends the averaged trace of every span
    to <csv_path stem>_traces.csv, tagged with row["f_target"] and row["vctrl_set"].
    """
    offset_span_map = offset_span_map or VCO_OFFSET_SPAN_MAP
    keep_remote_alive()
    f_out = find_carrier(spectrum, f_out_est)
    row.update(f_out_meas=f_out, f_vco_meas=f_out * total_div,
               f_dev_pct=(f_out * total_div / row["f_target"] - 1) * 100)
    logging.info("  carrier on the pad (= PLL output) %.4f MHz -> VCO %.2f MHz (%+.2f %% from the target)",
                 f_out / 1e6, f_out * total_div / 1e6, row["f_dev_pct"])

    traces = spectrum.phase_noise_traces(f_out, list(offset_span_map.values()), averages=n_averages,
                                         rbw_span_ratio=RBW_SPAN_RATIO)
    row.update(detector=spectrum.get_detector(), average_type=spectrum.get_average_type(),
               video_filter=spectrum.get_video_filter_type())
    append_rows(trace_csv_path(csv_path), TRACE_COLUMNS,
                [dict(f_target=row["f_target"], vctrl_set=row.get("vctrl_set"), total_div=total_div, span=t["span"],
                      rbw=t["rbw"], vbw=t["vbw"], center=t["center"], freq=f, offset=f - t["center"], power_dbm=p)
                 for t in traces for f, p in zip(t["freq"], t["level"])])
    o_tr, l_tr = phase_noise_from_traces(traces, sorted(offset_span_map))  # power-averaged: no correction
    t_jit, phi_out = integrate_phase_noise(f_out, o_tr, l_tr)
    row.update(time_jitter_trace_ps=t_jit * 1e12, phase_jitter_trace_out_mrad=phi_out * 1e3,
               phase_jitter_trace_vco_mrad=phi_out * total_div * 1e3, status="ok")
    logging.info("  RMS jitter %.0f-%.0f Hz (full curve, %d points): %.3f ps; phase %.3f mrad on the pad (= PLL "
                 "output), %.3f mrad at the VCO", o_tr[0], o_tr[-1], len(o_tr), t_jit * 1e12, phi_out * 1e3,
                 phi_out * total_div * 1e3)


def measure_vco_spectrum(f_vco, kvco=None, sample=None, lut=None, csv_path=None, n_averages=10,
                         offset_span_map=None, out_f_max=OUT_F_MAX, settle=2.0, spectrum=None, supply=None):
    """Configure the VCO for `f_vco` [Hz] / |Kvco| `kvco` [Hz/V] from the lookup table, hold Vctrl at the
    predicted operating point and measure the spectrum, phase noise and integrated jitter on the output pad.

    `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`.
    Appends one row to `csv_path` (default a new results/vco/vco_spectrum_<sample>_<stamp>.csv) and the
    traces to <csv_path stem>_traces.csv; returns the row.
    """
    offset_span_map = offset_span_map or VCO_OFFSET_SPAN_MAP
    csv_path = csv_path or spectrum_csv_path(sample)
    lut = lut or vco_lut.VcoLUT(sample=sample)
    row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, f_target=f_vco,
               kvco_target=kvco, n_averages=n_averages, offset_min=min(offset_span_map),
               offset_max=max(offset_span_map))
    try:
        cfg = lut.update_config(spectrum_cfg(f_vco, out_f_max), f_vco, kvco)
    except ValueError as e:  # no setting reaches f_vco
        logging.warning("VCO spectrum %.1f MHz: %s", f_vco / 1e6, e)
        append_rows(csv_path, SPECTRUM_COLUMNS, [dict(row, status="unreachable")])
        return row
    op = lut.predict(cfg, f_vco)
    _, total_div = calculate_div_factor(cfg)
    row.update(vco_lut.vco_codes(cfg), **op, set_div_freq=cfg["set_div_freq"], total_div=total_div)
    logging.info("VCO spectrum: %.1f MHz, Vctrl %.3f V, output / %d -> %.2f MHz expected", f_vco / 1e6,
                 op["vctrl_pred"], total_div, f_vco / total_div / 1e6)

    pll = pll_setup.open_pll(cfg)
    own_spectrum = spectrum is None
    smu = None
    try:
        smu = KeithleySMU2450(inst.BaseInstrumentData.from_mapping(vco_measure.load_instr_cfg()["smu_vctrl"]))
        smu.set_voltage(op["vctrl_pred"])
        smu.output_on()
        vco_measure.set_vctrl(smu, op["vctrl_pred"], settle)
        row["vctrl_meas"] = smu.measure()[0]

        spectrum = spectrum or open_spectrum()
        measure_pad_spectrum(spectrum, f_vco / total_div, total_div, row, csv_path, n_averages, offset_span_map)
        row.update(pll_setup.measure_pll_supply(supply, label="%.1f MHz" % (f_vco / 1e6)))
    except Exception:
        logging.exception("VCO spectrum measurement failed at %.1f MHz", f_vco / 1e6)
        row["status"] = "error"
    finally:
        if smu is not None:
            smu.close()  # back to 0 V, output off
        if own_spectrum and spectrum is not None:
            spectrum.close()
        pll.close()
    append_rows(csv_path, SPECTRUM_COLUMNS, [row])
    logging.info("VCO spectrum written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return row


def set_vco(f_vco, kvco=None, sample=None, lut=None, out_f_max=OUT_F_MAX, settle=2.0):
    """Set the VCO for `f_vco` / `kvco` from the lookup table (direct output, see spectrum_cfg) and drive Vctrl
    with the SMU at the predicted operating point. `lut`: vco_lut.VcoLUT; None = the newest table of `sample`.

    Returns dict(cfg, op (lut.predict: vctrl_pred, kvco_pred), total_div, f_out (expected pad frequency), smu,
    vctrl_meas); the SMU is left on (smu.close() turns it off). On an error the SMU output is switched off and
    every connection closed.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample)
    cfg = lut.update_config(spectrum_cfg(f_vco, out_f_max), f_vco, kvco)
    op = lut.predict(cfg, f_vco)
    pll = pll_setup.open_pll(cfg)
    pll.close()  # closes the FPGA ports only; the config stays on the chip
    _, total_div = calculate_div_factor(cfg)
    smu = None
    try:
        smu = KeithleySMU2450(inst.BaseInstrumentData.from_mapping(vco_measure.load_instr_cfg()["smu_vctrl"]))
        smu.set_voltage(op["vctrl_pred"])
        smu.output_on()
        vco_measure.set_vctrl(smu, op["vctrl_pred"], settle)
        v_meas = smu.measure()[0]
    except BaseException:
        if smu is not None:
            smu.close()  # instrument error: Vctrl back to 0 V, output off
        raise
    logging.info("VCO set: %.1f MHz, Vctrl %.3f V (SMU on, measured %.4f V); output / %d (set_div_freq %d, "
                 "pll_clk_o_en 1) -> %.4f MHz expected", f_vco / 1e6, op["vctrl_pred"], v_meas, total_div,
                 cfg["set_div_freq"], f_vco / total_div / 1e6)
    return dict(cfg=cfg, op=op, total_div=total_div, f_out=f_vco / total_div, smu=smu, vctrl_meas=v_meas)


def view_vco(f_vco, kvco=None, sample=None, lut=None, rel_span=0.3, out_f_max=OUT_F_MAX, settle=2.0,
             supply=None):
    """set_vco, then point the analyzer at the expected pad frequency and leave everything running for manual
    evaluation: the SMU stays on at the predicted Vctrl, the config stays loaded, and the analyzer sweeps
    continuously over `rel_span` * the expected pad frequency (press LOCAL to take over).
    On an error the SMU output is switched off and every connection closed.
    `supply`: the PLL supply SMU, its current and power are logged; it stays on too, off on an error.
    Turn Vctrl and the PLL supply off afterwards on the SMUs (or with close()).
    """
    vco = None
    try:
        vco = set_vco(f_vco, kvco, sample=sample, lut=lut, out_f_max=out_f_max, settle=settle)
        pll_setup.measure_pll_supply(supply, label="%.1f MHz" % (f_vco / 1e6))
    except BaseException:
        if vco is not None:
            vco["smu"].close()  # Vctrl back to 0 V, output off
        if supply is not None:
            supply.close()  # error: PLL supply off too
        raise
    spectrum = None
    try:
        spectrum = open_spectrum()
        spectrum.set_center_frequency(vco["f_out"])
        spectrum.set_span(rel_span * vco["f_out"])
        spectrum.set_sweep_mode(continuous=True)
        spectrum.set_display_update(True)
    except BaseException:
        vco["smu"].close()  # instrument error: Vctrl back to 0 V, output off
        if supply is not None:
            supply.close()  # PLL supply off too
        raise
    finally:
        if spectrum is not None:
            spectrum.close()  # settings stay on the analyzer; press LOCAL to take over
    logging.info("Analyzer: center %.4f MHz, span %.3f MHz, continuous sweep (press LOCAL to take over). "
                 "Vctrl is still on: switch the SMU output off when done.", vco["f_out"] / 1e6,
                 rel_span * vco["f_out"] / 1e6)


def capture_spectrum(f_vco, kvco=None, sample=None, lut=None, center=None, span=5e6, averages=20, rbw=None,
                     vbw=None, out_f_max=OUT_F_MAX, settle=2.0, note="", supply=None):
    """Reproducible averaged spectrum: set_vco (codes + Vctrl from the lookup table), one averaged analyzer trace
    around `center` (None: the expected pad frequency) over `span`, then Vctrl off and every connection closed.

    Written to results/vco/vco_capture_<sample>_<stamp>.csv, one row per trace point, with the setting in every
    row. `rbw`/`vbw` None: RBW = span / RBW_SPAN_RATIO, VBW = 3 RBW (as the phase-noise traces); `rbw` alone: VBW =
    3 rbw. `supply`: the PLL supply SMU (pll_setup.pll_supply), its voltage, current and power are recorded.
    Returns the CSV path.
    """
    vco = set_vco(f_vco, kvco, sample=sample, lut=lut, out_f_max=out_f_max, settle=settle)
    spectrum = None
    try:
        spectrum = open_spectrum()
        t = spectrum.averaged_trace(center or vco["f_out"], span, averages=averages, rbw=rbw, vbw=vbw,
                                    rbw_span_ratio=RBW_SPAN_RATIO if rbw is None and vbw is None else None)
        method = dict(detector=spectrum.get_detector(), average_type=spectrum.get_average_type(),
                      video_filter=spectrum.get_video_filter_type())
        power = pll_setup.measure_pll_supply(supply, label="%.1f MHz" % (f_vco / 1e6))
        spectrum.set_sweep_mode(continuous=True)  # screen live again afterwards
        spectrum.set_display_update(True)
    finally:
        vco["smu"].close()  # Vctrl back to 0 V, output off
        if spectrum is not None:
            spectrum.close()

    vco_lut.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = vco_lut.RESULTS_DIR / "vco_capture_{}_{}.csv".format(
        sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))
    setting = dict(time=datetime.now().isoformat(timespec="seconds"), note=note, f_target=f_vco, kvco_target=kvco,
                   **vco_lut.vco_codes(vco["cfg"]), **vco["op"], vctrl_meas=vco["vctrl_meas"],
                   set_div_freq=vco["cfg"]["set_div_freq"],
                   total_div=vco["total_div"], center=t["center"], span=t["span"], rbw=t["rbw"], vbw=t["vbw"],
                   averages=averages, **method, **power)
    append_rows(csv_path, CAPTURE_COLUMNS,
                [dict(setting, freq=f, level_dbm=l) for f, l in zip(t["freq"], t["level"])])
    i_max = int(np.argmax(t["level"]))
    logging.info("Spectrum: %d points, %d sweeps averaged, RBW %g Hz; peak %.1f dBm at %.4f MHz on the pad "
                 "(= PLL output; VCO %.2f MHz) -> %s", len(t["level"]), averages, t["rbw"], t["level"][i_max],
                 t["freq"][i_max] / 1e6, t["freq"][i_max] * vco["total_div"] / 1e6, csv_path)
    return csv_path


def vco_spectrum_sweep(targets, sample=None, lut=None, **kwargs):
    """measure_vco_spectrum for every (f_vco, kvco) in `targets`, one analyzer session, all into one CSV pair.
    `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`."""
    csv_path = spectrum_csv_path(sample)
    lut = lut or vco_lut.VcoLUT(sample=sample)
    spectrum = open_spectrum()
    try:
        rows = [measure_vco_spectrum(f, k, sample=sample, lut=lut, csv_path=csv_path, spectrum=spectrum, **kwargs)
                for f, k in targets]
    finally:
        spectrum.close()
    logging.info("VCO spectrum overview:")
    for r in rows:
        logging.info("  %8.1f MHz: %s", r["f_target"] / 1e6, "{:.3f} ps".format(r["time_jitter_trace_ps"])
                     if r.get("status") == "ok" else r.get("status"))
    return csv_path


def ask_vctrl(vctrl_set):
    """Wait until the user has set Vctrl to `vctrl_set` [V] on the potentiometer.
    Returns the voltage read on the multimeter (Enter alone: `vctrl_set`), "skip" or "stop"."""
    while True:
        answer = input("\n>>> Set Vctrl to %.3f V on the potentiometer. Enter = done (or type the voltage you read), "
                       "s = skip, q = stop: " % vctrl_set).strip().lower()
        if answer == "":
            return vctrl_set
        if answer == "s":
            return "skip"
        if answer == "q":
            return "stop"
        try:
            return float(answer)
        except ValueError:
            print("Not a voltage: %r" % answer)


def manual_vctrl_sweep(f_vco, kvco=None, sample=None, vctrls=MANUAL_VCTRLS, lut=None, n_averages=10,
                       offset_span_map=None, out_f_max=OUT_F_MAX, settle=1.0):
    """Spectrum and phase noise with Vctrl from a battery + potentiometer instead of the SMU (no SMU noise).

    The VCO codes for `f_vco` [Hz] / |Kvco| `kvco` [Hz/V] are taken from the lookup table and loaded on the chip
    (direct output, see spectrum_cfg). Then, for every voltage in `vctrls` [V], the script waits until you have
    set it on the potentiometer (ask_vctrl: press Enter, or type the voltage read on the multimeter), waits
    `settle` s and measures as measure_vco_spectrum: carrier near the lookup-table frequency at that Vctrl,
    phase-noise curve from the averaged traces, integrated jitter.

    One row per step in results/vco/vco_spectrum_<sample>_<stamp>.csv (vctrl_set = requested, vctrl_meas = typed
    or requested, f_vco_pred = lookup table at vctrl_set), traces in <stem>_traces.csv. Returns the CSV path.
    """
    offset_span_map = offset_span_map or VCO_OFFSET_SPAN_MAP
    csv_path = spectrum_csv_path(sample)
    lut = lut or vco_lut.VcoLUT(sample=sample)
    cfg = lut.update_config(spectrum_cfg(f_vco, out_f_max), f_vco, kvco)
    op = lut.predict(cfg, f_vco)
    _, total_div = calculate_div_factor(cfg)
    curve_v, curve_f = lut.curve(cfg)
    setting = dict(lut_csv=lut.path.name, f_target=f_vco, kvco_target=kvco, set_div_freq=cfg["set_div_freq"],
                   total_div=total_div, n_averages=n_averages, offset_min=min(offset_span_map),
                   offset_max=max(offset_span_map))
    setting.update(vco_lut.vco_codes(cfg))
    setting.update(op)


    pll = pll_setup.open_pll(cfg)
    pll.close()  # closes the FPGA ports only; the config stays on the chip
    logging.info("VCO codes for %.1f MHz loaded; output / %d (set_div_freq %d). Vctrl comes from the "
                 "potentiometer (no SMU).", f_vco / 1e6, total_div, cfg["set_div_freq"])

    rows = []
    spectrum = open_spectrum()
    try:
        for vctrl_set in vctrls:
            answer = ask_vctrl(vctrl_set)
            if answer == "stop":
                break
            f_pred = float(np.interp(vctrl_set, curve_v, curve_f))
            row = dict(setting, time=datetime.now().isoformat(timespec="seconds"), vctrl_set=vctrl_set,
                       f_vco_pred=f_pred)
            if answer == "skip":
                row["status"] = "skipped"
                rows.append(row)
                append_rows(csv_path, SPECTRUM_COLUMNS, [row])
                continue
            row["vctrl_meas"] = answer
            logging.info("Vctrl %.3f V (read %.4f V): lookup table %.2f MHz -> %.4f MHz expected on the pad",
                         vctrl_set, answer, f_pred / 1e6, f_pred / total_div / 1e6)
            time.sleep(settle)
            try:
                measure_pad_spectrum(spectrum, f_pred / total_div, total_div, row, csv_path, n_averages,
                                     offset_span_map)
            except BaseException:
                row["status"] = "error"
                append_rows(csv_path, SPECTRUM_COLUMNS, [row])
                raise
            rows.append(row)
            append_rows(csv_path, SPECTRUM_COLUMNS, [row])
    finally:
        spectrum.close()
        logging.info("Turn the potentiometer down / disconnect the battery.")

    logging.info("Manual Vctrl sweep -> %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    for r in rows:
        if r["status"] == "ok":
            logging.info("  Vctrl %.3f V: VCO %.2f MHz, %.3f ps", r["vctrl_set"], r["f_vco_meas"] / 1e6,
                         r["time_jitter_trace_ps"])
        else:
            logging.info("  Vctrl %.3f V: %s", r["vctrl_set"], r["status"])
    return csv_path


def pll_points(csv_name, factor="", **match):
    """The settings of a PLL measurement (results/pll/`csv_name`) to repeat open loop: one per locked, measured
    setting (VCO codes + f_vco) whose columns equal `match`, e.g. set_current=4. Internal divider only (ext_div 1).
    Returns a list of dicts with the POINT_FIELDS (`factor` as given)."""
    points = {}
    with (PLL_RESULTS_DIR / csv_name).open(newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("locked") not in ("1", "1.0") or r.get("status") != "ok"
                    or any(float(r[k]) != v for k, v in match.items())):
                continue
            if float(r.get("ext_div") or 1) != 1:
                logging.warning("%s: %s MHz has an external divider, skipped", csv_name, r["f_vco"])
                continue
            codes = {k: int(float(r[k])) for k in vco_lut.LUT_FIELDS}
            key = tuple(codes.values()) + (float(r["f_vco"]),)
            vctrl = float(r["vctrl_meas"] or "nan")
            points.setdefault(key, dict(
                factor=factor, pll_csv=csv_name, pll_match=" ".join("{}={:g}".format(k, v) for k, v in match.items()),
                f_vco_target=float(r["f_vco"]), vctrl_hint=vctrl, vctrl_pll=vctrl,
                carrier_pll_dbm=float(r["carrier_dbm"] or "nan"), jitter_pll_ps=float(r["time_jitter_trace_ps"]),
                set_div_freq=int(float(r["set_div_freq"])), total_div=int(float(r["total_div"])),
                f_pad=float(r["f_vco"]) / float(r["total_div"]), **codes))
    return list(points.values())


def matched_points(runs=PLL_MATCHED_RUNS):
    """pll_points of every (csv, match, factor) in `runs`."""
    return [p for csv_name, match, factor in runs for p in pll_points(csv_name, factor, **match)]


def ofat_points(sample=None, lut=None, base=OFAT_BASE, factors=OFAT_FACTORS, set_div_freq=OFAT_SET_DIV_FREQ):
    """One factor at a time around `base` (OFAT_FACTORS): per (factor, values, f_vco) a point per value with the other
    codes of `base`, at f_vco (or at the value, for the factor f_vco), on the internal divider 2**`set_div_freq`.
    A point shared by several factors (the same codes and f_vco) appears once, with all their names in `factor`.
    vctrl_hint: the lookup table's Vctrl at f_vco (`lut`, None: the newest table of `sample`; NaN when the table says
    the codes do not reach it: a warning, the point stays, tune or skip it). Returns dicts with the POINT_FIELDS."""
    lut = lut or vco_lut.VcoLUT(sample=sample)
    points = {}
    for factor, values, f_fixed in factors:
        for value in values:
            codes = dict(base)
            f_vco = f_fixed
            if factor == "f_vco":
                f_vco = value
            else:
                codes[factor] = value
            key = tuple(codes[k] for k in vco_lut.LUT_FIELDS) + (f_vco,)
            if key in points:
                points[key]["factor"] += " " + factor
                continue
            vctrls, f_vcos = lut.curve(dict(VCO_CHARAC_CFG, **codes))
            order = np.argsort(f_vcos)
            inside = len(f_vcos) > 1 and min(f_vcos) <= f_vco <= max(f_vcos)
            vctrl = float(np.interp(f_vco, np.asarray(f_vcos)[order], np.asarray(vctrls)[order])) if inside \
                else float("nan")
            if not inside:
                logging.warning("c%d min %d max %d: the table does not reach %.0f MHz (tune or skip)",
                                codes["vco_tune_coarse"], codes["vco_current_min"], codes["vco_current_max"],
                                f_vco / 1e6)
            nan = float("nan")
            points[key] = dict(factor=factor, pll_csv="", pll_match="", f_vco_target=f_vco, vctrl_hint=vctrl,
                               vctrl_pll=nan, carrier_pll_dbm=nan, jitter_pll_ps=nan, set_div_freq=set_div_freq,
                               total_div=2 ** set_div_freq, f_pad=f_vco / 2 ** set_div_freq, **codes)
    return list(points.values())


def ask_tuned(p):
    """Wait until the user has tuned Vctrl so that the carrier sits at the target of point `p`.
    Returns the Vctrl read on the multimeter (Enter alone: NaN), "skip" or "stop"."""
    start = "" if np.isnan(p["vctrl_hint"]) else "set Vctrl to ~{:.3f} V, then ".format(p["vctrl_hint"])
    while True:
        answer = input("\n>>> c{} min {} max {}: {}tune until the carrier is at {:.4f} MHz on the analyzer (VCO "
                       "{:.1f} MHz). Enter = done (or type the Vctrl you read), s = skip, q = stop: ".format(
                           p["vco_tune_coarse"], p["vco_current_min"], p["vco_current_max"], start,
                           p["f_pad"] / 1e6, p["f_vco_target"] / 1e6)).strip().lower()
        if answer == "":
            return float("nan")
        if answer in ("s", "q"):
            return {"s": "skip", "q": "stop"}[answer]
        try:
            return float(answer)
        except ValueError:
            print("Not a voltage: %r" % answer)


def carrier_of(trace, band=CARRIER_BAND):
    """(frequency [Hz], power [dBm]) of the carrier in an averaged spectrum `trace` (freq, level in dBm, rbw): the
    power-weighted centre and the total power of the points within +-`band` of the peak (each point x its spacing /
    RBW: a carrier smeared over several RBWs by the wander counts in full)."""
    freq, level = np.asarray(trace["freq"], dtype=float), np.asarray(trace["level"], dtype=float)
    f_peak = freq[int(np.argmax(level))]
    near = np.abs(freq - f_peak) <= band
    p_mw = 10 ** (level[near] / 10)
    step = np.median(np.diff(freq))
    return float(np.sum(freq[near] * p_mw) / np.sum(p_mw)), float(10 * np.log10(np.sum(p_mw) * step / trace["rbw"]))


def capture_spectra(f_pad, spans=SPECTRUM_SPANS, averages=SPECTRUM_AVERAGES):
    """One averaged spectrum around `f_pad` [Hz] per span in `spans` (narrowest last), RBW = span / RBW_SPAN_RATIO,
    RMS detector + power averaging over `averages` sweeps (driver averaged_trace). Returns the traces (kind
    "spectrum", freq absolute, level in dBm); the analyzer is closed afterwards, also on an error."""
    spectrum = open_spectrum()
    try:
        traces = [dict(spectrum.averaged_trace(f_pad, span, averages=averages, rbw_span_ratio=RBW_SPAN_RATIO),
                       kind="spectrum") for span in sorted(spans, reverse=True)]
    finally:
        spectrum.close()
    for t in traces:
        i_max = int(np.argmax(t["level"]))
        logging.info("  spectrum, span %.3g MHz (RBW %g Hz): carrier %.1f dBm at %.4f MHz", t["span"] / 1e6, t["rbw"],
                     t["level"][i_max], t["freq"][i_max] / 1e6)
    return traces


def open_vctrl_smu():
    """The Vctrl SMU (meas_setup.yaml smu_vctrl) at 0 V with its output on; close() takes it back to 0 V, off."""
    smu = KeithleySMU2450(inst.BaseInstrumentData.from_mapping(vco_measure.load_instr_cfg()["smu_vctrl"]))
    try:
        smu.set_voltage(0.0)
        smu.output_on()
    except BaseException:
        smu.close()
        raise
    logging.info("Vctrl from the SMU (output on at 0 V): the battery + potentiometer must be disconnected")
    return smu


def smu_tune(smu, p, total_div, vctrl_range=SMU_VCTRL_RANGE, span=SPECTRUM_SPANS[0], averages=TUNE_SMU_AVERAGES,
             kvco0=TUNE_KVCO0, tol_rel=TUNE_TOL_REL, max_steps=TUNE_MAX_STEPS, settle=SMU_SETTLE):
    """Tune the SMU's Vctrl until the carrier of point `p` sits at its target f_pad: start at vctrl_hint (NaN: the
    middle of `vctrl_range`), read the carrier (carrier_of on an averaged spectrum of `span` around f_pad,
    `averages` sweeps), step Vctrl by the frequency error over the slope (first step |Kvco| `kvco0` [Hz/V] at the VCO,
    then the secant of the last two steps) until within `tol_rel` of f_pad, at most `max_steps` steps, Vctrl clipped
    to `vctrl_range` [V]. Returns dict(vctrl_set, tune_steps, vctrl_read (SMU measured), status): "tuned",
    "unreachable" (the step stays at a limit of `vctrl_range`), "no_carrier" (below MIN_TUNE_CARRIER_DBM) or
    "not_tuned"."""
    f_target = p["f_pad"]
    v_lo, v_hi = vctrl_range
    v = p["vctrl_hint"] if not np.isnan(p["vctrl_hint"]) else (v_lo + v_hi) / 2
    v = min(max(v, v_lo), v_hi)
    prev = None
    status, n = "not_tuned", 0
    spectrum = open_spectrum()
    try:
        for n in range(1, max_steps + 1):
            vco_measure.set_vctrl(smu, v, settle)
            f, level = carrier_of(spectrum.averaged_trace(f_target, span, averages=averages,
                                                          rbw_span_ratio=RBW_SPAN_RATIO))
            logging.info("  tune %d: Vctrl %.4f V -> carrier %.4f MHz, %.1f dBm (target %.4f MHz)", n, v, f / 1e6,
                         level, f_target / 1e6)
            if level < MIN_TUNE_CARRIER_DBM:
                status = "no_carrier"
                break
            if abs(f - f_target) <= tol_rel * f_target:
                status = "tuned"
                break
            slope = -kvco0 / total_div  # f falls with Vctrl
            if prev is not None and abs(v - prev[0]) > 1e-4 and (f - prev[1]) / (v - prev[0]) < 0:
                slope = (f - prev[1]) / (v - prev[0])
            v_new = min(max(v + (f_target - f) / slope, v_lo), v_hi)
            if v_new == v:  # at a limit and still not there
                status = "unreachable"
                break
            prev, v = (v, f), v_new
    finally:
        spectrum.close()
    vctrl_read = smu.measure()[0]
    logging.info("  %s after %d steps: Vctrl %.4f V (SMU reads %.4f V)", status, n, v, vctrl_read)
    return dict(vctrl_set=v, tune_steps=n, vctrl_read=vctrl_read, status=status)


def vco_pnm_sweep(points=None, sample=None, vctrl_source="pot", averages=PNM_AVERAGES,
                  freq_tolerance=PNM_FREQ_TOLERANCE, level_tolerance=PNM_LEVEL_TOLERANCE, tune_span=TUNE_SPAN,
                  tune_averages=TUNE_AVERAGES, spectrum_spans=SPECTRUM_SPANS, spectrum_averages=SPECTRUM_AVERAGES,
                  supply=None, vdd_set=None, csv_path=None):
    """Open-loop VCO spectrum and phase noise at tuned operating points. `points`: dicts with the POINT_FIELDS; None:
    matched_points() (the PLL runs, to overlay on their curves) followed by ofat_points(sample) (one factor at a
    time).

    Per point the VCO codes and internal divider are loaded (open loop, Vctrl from the pad) and the analyzer shows the
    pad live around the target carrier (f_vco_target / total_div, span `tune_span`, moving average over
    `tune_averages` sweeps). You tune Vctrl until the carrier sits there (start: vctrl_hint) and press Enter.
    `vctrl_source`: "pot" (battery + potentiometer on the Vctrl pin header, tuned by hand as above) or "smu" (the SMU
    smu_vctrl on the pin header, tuned automatically by smu_tune; points it cannot tune are recorded with its status
    and skipped; the SMU goes back to 0 V and off at the end, also on an error). Then one
    averaged spectrum per span of `spectrum_spans` (capture_spectra, `spectrum_averages` sweeps; saved right away) and
    the analyzer's Phase Noise mode (pll_spectrum.measure_phase_noise_mode: carrier from the widest spectrum,
    carrier_of; verified within `freq_tolerance` [Hz] and `level_tolerance` [dB] and tracked during the sweep,
    `averages` trace averages), L(f) from 1 kHz up to f_pad / OUT_OFFSET_RATIO, the band of the PLL measurements.
    One row per point in results/vco/vco_pnm_<sample>_<stamp>.csv; the spectra, the L(f) curve and the spur list in
    <stem>_traces.csv (plotted in sw/tools/notebooks/vco_pnm.ipynb). Returns the CSV path.
    `supply`: the PLL supply (pll_setup.PllSupplyChannel), measured per point (pll_vdd, pll_i, pll_p; None: NaN);
    `vdd_set`: the voltage it was set to, recorded in every row and trace row. `csv_path`: append to this CSV (and its
    _traces.csv) instead of a new vco_pnm_* pair, e.g. one file over several calls.
    """
    points = points if points is not None else matched_points() + ofat_points(sample=sample)
    vco_lut.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if csv_path is None:
        csv_path = vco_lut.RESULTS_DIR / "vco_pnm_{}_{}.csv".format(sample or "nosample",
                                                                     datetime.now().strftime("%Y%m%d_%H%M%S"))
    logging.info("Open-loop phase noise: %d points -> %s", len(points), csv_path)
    rows = []
    smu = open_vctrl_smu() if vctrl_source == "smu" else None
    try:
        for i, p in enumerate(points, 1):
            cfg = dict(VCO_CHARAC_CFG, pll_clk_o_en=1, set_div_freq=p["set_div_freq"],
                       **{k: p[k] for k in vco_lut.LUT_FIELDS})
            _, total_div = calculate_div_factor(cfg)
            if total_div != p["total_div"]:
                logging.warning("point %d: divider %d instead of %d: skipped", i, total_div, p["total_div"])
                continue
            logging.info("=== point %d/%d (%s%s): c%d min %d max %d, VCO %.1f MHz / %d -> pad %.4f MHz ===", i,
                         len(points), p["factor"], ", " + p["pll_csv"] if p["pll_csv"] else "", p["vco_tune_coarse"],
                         p["vco_current_min"], p["vco_current_max"], p["f_vco_target"] / 1e6, total_div,
                         p["f_pad"] / 1e6)
            pll = pll_setup.open_pll(cfg)
            pll.close()  # closes the FPGA ports only; the config stays on the chip
            row = dict(p, time=datetime.now().isoformat(timespec="seconds"), vctrl_source=vctrl_source,
                       vdd_set=vdd_set, **pll_setup.measure_pll_supply(supply))
            if smu is not None:
                row.update(smu_tune(smu, p, total_div))
                if row["status"] != "tuned":
                    append_rows(csv_path, VCO_PNM_COLUMNS, [row])
                    continue
            else:
                spectrum = open_spectrum()
                try:
                    spectrum.live_view(p["f_pad"], tune_span, averages=tune_averages)
                finally:
                    spectrum.close()  # the live view keeps running
                answer = ask_tuned(p)
                if answer == "stop":
                    break
                if answer == "skip":
                    row["status"] = "skipped"
                    append_rows(csv_path, VCO_PNM_COLUMNS, [row])
                    continue
                row["vctrl_read"] = answer
            key = dict(f_vco_target=p["f_vco_target"], set_div_freq=p["set_div_freq"], vdd_set=vdd_set,
                       **{k: p[k] for k in vco_lut.LUT_FIELDS})
            try:
                spectra = capture_spectra(p["f_pad"], spectrum_spans, spectrum_averages)
            except BaseException:
                row["status"] = "error"
                append_rows(csv_path, VCO_PNM_COLUMNS, [row])
                raise  # instrument error: stop
            append_rows(trace_csv_path(csv_path), VCO_PNM_TRACE_COLUMNS, trace_rows(spectra, **key))  # saved right away
            row["f_pad_spectrum"], row["carrier_spectrum_dbm"] = carrier_of(spectra[0])  # the widest span
            logging.info("  carrier %.4f MHz, %.1f dBm (within +-%g MHz of the peak)", row["f_pad_spectrum"] / 1e6,
                         row["carrier_spectrum_dbm"], CARRIER_BAND / 1e6)
            try:
                pnm, traces = measure_phase_noise_mode(row["f_pad_spectrum"] * total_div, total_div,
                                                       sorted(offsets_for(p["f_pad"])),
                                                       carrier_dbm=row["carrier_spectrum_dbm"], averages=averages,
                                                       freq_tolerance_hz=freq_tolerance,
                                                       level_tolerance_db=level_tolerance)
            except pyvisa.VisaIOError:
                row["status"] = "error"
                append_rows(csv_path, VCO_PNM_COLUMNS, [row])
                raise  # instrument connection lost: stop
            except Exception:
                logging.exception("point %d: Phase Noise mode failed (carrier not found?), continuing", i)
                row["status"] = "error"
                append_rows(csv_path, VCO_PNM_COLUMNS, [row])
                continue
            f_vco_meas = pnm["pnm_f_out_meas"] * total_div
            row.update(pnm, f_vco_meas=f_vco_meas, f_dev_pct=(f_vco_meas / p["f_vco_target"] - 1) * 100, status="ok")
            rows.append(row)
            append_rows(csv_path, VCO_PNM_COLUMNS, [row])
            append_rows(trace_csv_path(csv_path), VCO_PNM_TRACE_COLUMNS, trace_rows(traces, **key))
    finally:
        if smu is not None:
            smu.close()  # Vctrl back to 0 V, output off
    if vctrl_source == "pot":
        logging.info("Turn the potentiometer down / disconnect the battery.")
    logging.info("Open-loop phase noise -> %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    for r in rows:
        logging.info("  %-22s c%d min %d max %d, %.1f MHz: open loop %.1f ps (%s Hz), PLL %.1f ps", r["factor"],
                     r["vco_tune_coarse"], r["vco_current_min"], r["vco_current_max"], r["f_vco_meas"] / 1e6,
                     r["time_jitter_pnm_ps"], r["pnm_band"], r["jitter_pll_ps"])
    return csv_path


def spectrum_csv_path(sample):
    vco_lut.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return vco_lut.RESULTS_DIR / "vco_spectrum_{}_{}.csv".format(
        sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def trace_csv_path(csv_path):
    return Path(csv_path).with_name(Path(csv_path).stem + "_traces.csv")


def append_rows(csv_path, columns, rows):
    """Append rows to a CSV (header written when the file is new)."""
    new = not Path(csv_path).exists() or Path(csv_path).stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def start_log_file():
    """Also write the log to results/logs/vco_spectrum_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "vco_spectrum_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():  # core in reset: no pollution
        # Set the VCO and point the analyzer at it, then leave it for manual evaluation
        # view_vco(1.0e9, 1.0e9, sample="S5")

        # PLL supply: fixed on the board, always on (no SMU since 2026-10-19): power columns stay NaN
        # Averaged spectrum: sets the VCO (S5 table) and Vctrl, captures, Vctrl off;
        # plotted in vco_spectrum.ipynb
        # capture_spectrum(1.0e9, 1.0e9, sample="S5", center=31e6, span=5e6, averages=20)
        # capture_spectrum(2.4e9, 1.0e9, sample="S5", span=15e6, averages=20)  # / 64 -> 37.5 MHz
        # capture_spectrum(2.4e9, 5.0e9, sample="S5", span=15e6, averages=20)  # |Kvco| ~5 GHz/V

        # Vctrl from a battery + potentiometer (no SMU): codes for 2.4 GHz, waits for you at every Vctrl step
        # manual_vctrl_sweep(2.4e9, 1.0e9, sample="S5", vctrls=MANUAL_VCTRLS)

        # Open loop, battery + potentiometer on the Vctrl pin header: tune until the carrier sits at the target, Enter;
        # spectra + analyzer Phase Noise mode (tracks the drift). The PLL runs of PLL_MATCHED_RUNS (14 points) then
        # OFAT_FACTORS one factor at a time (9 points), ~5 min each
        # (done 2026-10-21 13:43, vco_pnm_S5_20261021_134315)
        # vco_pnm_sweep(sample="S5")
        # The same points with Vctrl from the SMU (smu_vctrl on the pin header, potentiometer disconnected), tuned
        # automatically: no prompts, ~2 min per point
        vco_pnm_sweep(sample="S5", vctrl_source="smu")
        # only the one-factor-at-a-time points:
        # vco_pnm_sweep(ofat_points(sample="S5"), sample="S5")

        # One setting: 1 GHz with |Kvco| ~1 GHz/V from the S5 table
        # measure_vco_spectrum(1.0e9, 1.0e9, sample="S5")

        # Several settings, one CSV pair
        # vco_spectrum_sweep([(f, None) for f in (200e6, 500e6, 1e9, 2e9, 5e9)], sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

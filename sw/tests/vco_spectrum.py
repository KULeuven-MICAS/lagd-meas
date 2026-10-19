# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Open-loop VCO spectrum, phase noise and jitter: VcoLUT (lib/vco_lut.py) sets the VCO codes for a frequency
# and Kvco from the lookup table, the SMU holds Vctrl at the predicted operating point, and the R&S FSV signal
# analyzer measures the output pad: phase-noise markers at a set of offsets, integrated with
# pll_util.calculate_integrated_jitter; RBW = span / pll_spectrum.RBW_SPAN_RATIO, VBW = 3 RBW, RMS detector, power
# averaging and linear video filter, as in lib/pll_spectrum.py. The averaged trace of every span is saved too
# (measure_phase_noise_profile(..., traces=[])), for plotting the spectrum.
#
# Output path: pll_clk_o_en = 1, the VCO divided by 2**set_div_freq only (no external divider), with
# set_div_freq the smallest that brings the pad frequency at or below `out_f_max`. Division keeps the time
# jitter; the phase noise and phase jitter are also given referred to the VCO (+20 log10(N), x N).
#
# A free-running VCO wanders: close-in offsets (< ~10 kHz) are dominated by drift during the averaged sweeps,
# so the default offsets start at 10 kHz.
#
# Results (plotted in sw/tools/notebooks/vco_spectrum.ipynb):
#   results/vco/vco_spectrum_<sample>_<stamp>.csv          one row per setting: carrier, L(f) at the offsets, jitter
#   results/vco/vco_spectrum_<sample>_<stamp>_traces.csv   the averaged analyzer traces (one row per trace point)
#
# Tests:
#   view_vco(f, kvco, sample)                  # set the VCO + analyzer and leave it running for manual evaluation
#   capture_spectrum(f, kvco, sample, center, span, averages)  # set VCO + Vctrl, averaged spectrum -> vco_capture_*.csv
#   measure_vco_spectrum(f, kvco, sample)      # one setting
#   vco_spectrum_sweep(targets, sample)        # a list of (f, kvco) targets, one CSV pair for all
#   manual_vctrl_sweep(f, kvco, sample, vctrls)  # Vctrl from a battery + potentiometer, waits for you at each step
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
from sw.lib.pll_spectrum import RBW_SPAN_RATIO
from sw.lib.pll_util import calculate_integrated_jitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Offset [Hz] -> analyzer span [Hz] for the phase-noise marker (as in pll_integrated_jitter.py).
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
                       "offset_min", "offset_max", "time_jitter_ps", "phase_jitter_out_mrad", "phase_jitter_vco_mrad"]
                    + ["L_out_{:.0f}".format(f) for f in VCO_OFFSET_SPAN_MAP]
                    + ["L_vco_{:.0f}".format(f) for f in VCO_OFFSET_SPAN_MAP]
                    + list(pll_setup.SUPPLY_COLUMNS) + ["status"])
# One row per trace point; `offset` = freq - center (the carrier), power in dBm as on the analyzer.
TRACE_COLUMNS = ["f_target", "vctrl_set", "total_div", "span", "rbw", "vbw", "center", "freq", "offset", "power_dbm"]
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
    """Find the carrier near `f_out_est` [Hz] on the output pad and measure the phase noise at the offsets of
    `offset_span_map` and the integrated jitter (on the pad and referred to the VCO, x `total_div`).

    Fills `row` (carrier, L(f), jitter, analyzer method, status "ok") and appends the averaged trace of every span
    to <csv_path stem>_traces.csv, tagged with row["f_target"] and row["vctrl_set"].
    """
    offset_span_map = offset_span_map or VCO_OFFSET_SPAN_MAP
    keep_remote_alive()
    f_out = find_carrier(spectrum, f_out_est)
    row.update(f_out_meas=f_out, f_vco_meas=f_out * total_div,
               f_dev_pct=(f_out * total_div / row["f_target"] - 1) * 100)
    logging.info("  carrier on the pad (= PLL output) %.4f MHz -> VCO %.2f MHz (%+.2f %% from the target)",
                 f_out / 1e6, f_out * total_div / 1e6, row["f_dev_pct"])

    traces = []  # the averaged trace of every span (RohdeSchwarzFSVSpectrum.get_trace)
    profile = spectrum.measure_phase_noise_profile(averages=n_averages, offset_span_map=offset_span_map,
                                                   traces=traces, rbw_span_ratio=RBW_SPAN_RATIO)
    row.update(detector=spectrum.get_detector(), average_type=spectrum.get_average_type(),
               video_filter=spectrum.get_video_filter_type())
    append_rows(trace_csv_path(csv_path), TRACE_COLUMNS,
                [dict(f_target=row["f_target"], vctrl_set=row.get("vctrl_set"), total_div=total_div, span=t["span"],
                      rbw=t["rbw"], vbw=t["vbw"], center=t["center"], freq=f, offset=f - t["center"], power_dbm=p)
                 for t in traces for f, p in zip(t["freq"], t["level"])])
    offsets, l_out = list(profile), list(profile.values())
    t_jit, phi_out = calculate_integrated_jitter(f_out, offsets, l_out)
    row.update(time_jitter_ps=t_jit * 1e12, phase_jitter_out_mrad=phi_out * 1e3,
               phase_jitter_vco_mrad=phi_out * total_div * 1e3, status="ok")
    for f, l in profile.items():
        row["L_out_{:.0f}".format(f)] = l
        row["L_vco_{:.0f}".format(f)] = l + 20 * np.log10(total_div)
    logging.info("  phase noise referred to the VCO: %s", ", ".join(
        "{:g} Hz: {:.1f} dBc/Hz".format(f, l + 20 * np.log10(total_div)) for f, l in profile.items()))
    logging.info("  RMS jitter %.0f-%.0f Hz: %.3f ps; phase %.3f mrad on the pad (= PLL output), %.3f mrad at "
                 "the VCO",
                 min(offsets), max(offsets), t_jit * 1e12, phi_out * 1e3, phi_out * total_div * 1e3)


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
        logging.info("  %8.1f MHz: %s", r["f_target"] / 1e6, "{:.3f} ps".format(r["time_jitter_ps"])
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
    L(f) at the offsets, integrated jitter, averaged traces.

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
                         r["time_jitter_ps"])
        else:
            logging.info("  Vctrl %.3f V: %s", r["vctrl_set"], r["status"])
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
        manual_vctrl_sweep(2.4e9, 1.0e9, sample="S5", vctrls=MANUAL_VCTRLS)

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

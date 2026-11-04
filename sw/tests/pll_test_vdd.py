# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Influence of the PLL supply. 2026-10-21 (pll_spur_zoom.py): the ~2 MHz hump and the spurs around it (1.6-2.4 MHz) and
# at 556 / 704 kHz phase-modulate the VCO from sources outside the PLL; their frequencies do not move with the PLL
# supply, but their level collapses below ~0.70 V (about 30 dB down at 0.60 V) and the hump disappears below 0.65 V.
# This test measures what that does to the PLL: per PLL supply voltage of VDDS (set automatically on the E36312A CH2,
# pll_setup.PllSupplyChannel; CH1 powers the board and is never touched) and per setting of POINTS:
#   1. the spectra around the carrier (pll_spur_zoom.showcase_traces: +-3 / +-10 / +-1 MHz, many averages)
#      and one wide spectrum (WIDE_CAPTURES: 1 MHz - 1.5 GHz, reference, harmonics, the VCO, pickup), capture 4
#   2. the full measurement (pll_test_vctrl.measure_pll_vctrl, Vctrl pad off): phase noise from the full curve, RMS
#      jitter (noise / spurs) and the analyzer's Phase Noise mode (L(f) curve, its jitter), with the supply voltage
#      and current recorded (pll_vdd, pll_i, pll_p)
# The supply goes back to the voltage it had at the start at the end, also on an error.
# The same without the loop (vco_vdd_sweep): the free-running VCO with the codes and pad divider of every setting,
# Vctrl from the SMU on the Vctrl pin header, retuned at every supply to the setting's f_vco
# (vco_spectrum.vco_pnm_sweep, vctrl_source "smu"): the spectra (40 / 5 MHz span) and the Phase Noise mode, which
# tracks the drifting carrier. Does the hump disappear at a low supply without the loop too?
#
# Results (plotted in sw/tools/notebooks/pll_test_vdd.ipynb; the battery runs, vdds None, in pll_battery.ipynb):
#   results/pll/pll_test_vdd_<sample>_<stamp>.csv                  one row per supply and setting (measure_pll_vctrl)
#   results/pll/pll_test_vdd_<sample>_<stamp>_traces.csv           its traces (full curve, Phase Noise mode, ...)
#   results/pll/pll_test_vdd_<sample>_<stamp>_spectra.csv          the spectra, one row per point (+ supply, setting)
#   results/vco/vco_vdd_<sample>_<stamp>.csv                       open loop: one row per supply and setting
#   results/vco/vco_vdd_<sample>_<stamp>_traces.csv                its spectra and Phase Noise mode curves
#
# Tests:
#   vdd_sweep(vdds, points, sample)        # every supply of `vdds` x every setting of `points`
#   vdd_sweep(None, points, sample)        # PLL supply from a battery: every setting once, supply not recorded
#   vco_vdd_sweep(vdds, points, sample)    # the same, open loop (Vctrl from the SMU)
#

import logging
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import FILTER_FIELDS, VCO_CHARAC_CFG
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows, open_spectrum, pad_divider
from sw.tests.pll_spur_zoom import LOCK_TIMEOUT, MAX_SWEEP_POINTS, SHOWCASE_CAPTURES, SPUR_POINTS, showcase_traces
from sw.tests.pll_test_vctrl import loop_cfg, measure_pll_vctrl
from sw.tests.vco_spectrum import vco_pnm_sweep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# PLL supply voltages [V], one after the other (the nominal 0.75 V first and last: drift check)
VDDS = (0.75, 0.80, 0.85, 0.70, 0.675, 0.65, 0.625, 0.60, 0.75)
SUPPLY_CHANNEL = 2  # E36312A (meas_setup.yaml power_supply_pll) channel of the PLL supply
SUPPLY_SETTLE = 2.0  # [s] after a supply step
# Settings measured per supply: c9 min 9 max 0 at 760 MHz (C1 7, Icp 4: hump and spurs strongest) and c9 min 14 max 0
# at 1 GHz (LOOP_FILTER), as in pll_spur_zoom
POINTS = SPUR_POINTS
# Wide spectra after the showcase captures (numbered on from them: capture 4, ...): (start, stop [Hz], RBW [Hz],
# averages), absolute frequencies (not around the carrier); starts at 1 MHz, clear of the LO feedthrough at 0 Hz.
# 32001 points over 1.5 GHz: ~47 kHz per point, ~2 per RBW
WIDE_CAPTURES = ((1e6, 1.5e9, 100e3, 10),)

SPECTRA_COLUMNS = (["time", "label", "f_vco", "f_ref"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
                   + ["set_div_freq", "total_div", "f_pad", "vdd_set", "pll_vdd", "pll_i", "locked", "f_carrier",
                      "carrier_dbm", "capture", "center", "span", "rbw", "averages", "freq", "level_dbm"])


def capture_spectra(point, supply, vdd, csv_path, fpga=None):
    """Lock the PLL at `point` (pll_spur_zoom.SPUR_POINTS entry, Vctrl pad off) and take the showcase spectra
    (showcase_traces, captures 1-3) and the wide spectra (WIDE_CAPTURES, captures 4, ...); appends them to
    `csv_path`, one row per trace point with the setting and supply. Not locked within LOCK_TIMEOUT: no spectra,
    nothing appended (2026-10-28: an unlocked run recorded the noise floor). Reference off and every connection closed
    at the end, also on an error. `fpga`: a pll_setup.FpgaUnplug (plugged in for the configuration, unplugged for the
    spectra; None: stays connected)."""
    cfg = dict(loop_cfg(point["f_vco"], loop_filter=point["loop_filter"]), **point["codes"])
    _, total_div = calculate_div_factor(cfg)
    f_ref, f_pad = point["f_vco"] / FB_DIV, point["f_vco"] / total_div
    fg = pll = spectrum = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        if fpga is not None:
            fpga.plug()
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=LOCK_TIMEOUT)
        logging.info("%s at %.3f V: PLL %s", point["label"], vdd, "LOCKED" if locked else "NOT LOCKED")
        if not locked:
            logging.warning("Not locked: spectra not captured")
            return
        if fpga is not None:
            fpga.unplug()
        v, i = supply.measure_stats()[:2] if supply is not None else (float("nan"), float("nan"))
        spectrum = open_spectrum()
        f_carrier, carrier_dbm, traces = showcase_traces(spectrum, f_pad)
        for start, stop, rbw, avg in WIDE_CAPTURES:
            spectrum.set_sweep_points(min(MAX_SWEEP_POINTS, int(5 * (stop - start) / rbw) + 1))
            traces.append(spectrum.averaged_trace((start + stop) / 2, stop - start, averages=avg, rbw=rbw))
            logging.info("  wide spectrum: %g - %g MHz, RBW %g Hz, %d averages", start / 1e6, stop / 1e6,
                         traces[-1]["rbw"], avg)
        base = dict(time=datetime.now().isoformat(timespec="seconds"), label=point["label"], f_vco=point["f_vco"],
                    f_ref=f_ref, set_div_freq=cfg["set_div_freq"], total_div=total_div, f_pad=f_pad, vdd_set=vdd,
                    pll_vdd=v, pll_i=i, locked=int(locked), f_carrier=f_carrier, carrier_dbm=carrier_dbm,
                    **point["codes"], **{k: cfg[k] for k in FILTER_FIELDS})
        append_rows(csv_path, SPECTRA_COLUMNS,
                    [dict(base, capture=n, center=t["center"], span=t["span"], rbw=t["rbw"], averages=avg, freq=f,
                          level_dbm=l)
                     for n, (t, avg) in enumerate(zip(traces, [c[-1] for c in SHOWCASE_CAPTURES + WIDE_CAPTURES]), 1)
                     for f, l in zip(t["freq"], t["level"])])
    finally:
        # Nested: the PLL ports and the reference are closed even when the analyzer cleanup fails (Ctrl+C mid-query,
        # 2026-10-28: the xillybus port stayed open and the next setting could not configure the chip)
        try:
            if spectrum is not None:
                try:
                    spectrum.set_sweep_mode(continuous=True)
                finally:
                    spectrum.close()
        finally:
            try:
                if pll is not None:
                    pll.close()
            finally:
                if fg is not None:
                    fg.close()  # reference off


def vdd_sweep(vdds=VDDS, points=POINTS, sample=None, unplug_fpga=False):
    """Per PLL supply voltage of `vdds` [V] (PllSupplyChannel CH SUPPLY_CHANNEL, SUPPLY_SETTLE s) and per setting of
    `points`: the spectra (capture_spectra) and the full measurement with the Phase Noise mode (measure_pll_vctrl).
    The supply goes back to its starting voltage at the end, also on an error. Returns the CSV path.
    `vdds` None: the PLL supply comes from a battery, every setting once; the E36312A is not opened and the supply
    columns (vdd_set, pll_vdd, pll_i, pll_p) are NaN.
    `unplug_fpga`: attended run, asks to unplug the FPGA after every lock and to plug it back in before every
    configuration (pll_setup.FpgaUnplug)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_test_vdd_{}_{}.csv".format(sample or "nosample",
                                                             datetime.now().strftime("%Y%m%d_%H%M%S"))
    spectra_path = csv_path.with_name(csv_path.stem + "_spectra.csv")
    lut = vco_lut.VcoLUT(sample=sample)
    supply = pll_setup.PllSupplyChannel(channel=SUPPLY_CHANNEL) if vdds is not None else None
    fpga = pll_setup.FpgaUnplug() if unplug_fpga else None
    try:
        for k, vdd in enumerate(vdds or (float("nan"),), 1):
            if supply is not None:
                supply.set(vdd, settle=SUPPLY_SETTLE)
            for point in points:
                logging.info("=== supply %d/%d: %s, %s ===", k, len(vdds or (None,)),
                             "battery" if supply is None else "%.3f V" % vdd, point["label"])
                try:
                    capture_spectra(point, supply, vdd, spectra_path, fpga=fpga)
                    measure_pll_vctrl(point["f_vco"], float("nan"), sample=sample, lut=lut, csv_path=csv_path,
                                      scope=None, vctrl_pad="off", supply=supply, codes=point["codes"],
                                      loop_filter=point["loop_filter"], phase_noise_mode=True, fpga=fpga)
                except pyvisa.VisaIOError:
                    raise  # instrument connection lost: stop (supply back to nominal below)
                except Exception:
                    logging.exception("%s at %.3f V failed, continuing", point["label"], vdd)
        if fpga is not None:
            fpga.plug()  # connected again for the core reset release at the end
    finally:
        if fpga is not None and fpga.unplugged:
            logging.warning("The FPGA is still unplugged: plug it back in")
        if supply is not None:
            supply.close()  # back to the starting voltage; CH1 and the outputs untouched
    logging.info("PLL supply sweep written to %s (spectra: %s)", csv_path, spectra_path.name)
    return csv_path


def open_loop_points(points=POINTS):
    """The settings of `points` (pll_spur_zoom.SPUR_POINTS entries) as open-loop points for vco_spectrum.vco_pnm_sweep:
    VCO codes, f_vco and the internal pad divider of the closed-loop measurement (loop_cfg); `factor` = the label,
    Vctrl starts in the middle of the SMU range (no hint)."""
    nan = float("nan")
    result = []
    for point in points:
        set_div_freq = pad_divider(point["f_vco"])
        _, total_div = calculate_div_factor(dict(VCO_CHARAC_CFG, pll_clk_o_en=1, set_div_freq=set_div_freq,
                                                 **point["codes"]))
        result.append(dict(factor=point["label"], pll_csv="", pll_match="", f_vco_target=point["f_vco"],
                           vctrl_hint=nan, vctrl_pll=nan, carrier_pll_dbm=nan, jitter_pll_ps=nan,
                           set_div_freq=set_div_freq, total_div=total_div, f_pad=point["f_vco"] / total_div,
                           **point["codes"]))
    return result


def vco_vdd_sweep(vdds=VDDS, points=POINTS, sample=None):
    """Open loop: per PLL supply voltage of `vdds` [V] (PllSupplyChannel CH SUPPLY_CHANNEL, SUPPLY_SETTLE s) the
    free-running VCO at every setting of `points` (open_loop_points), Vctrl from the SMU retuned to the setting's
    f_vco, spectra + Phase Noise mode (vco_spectrum.vco_pnm_sweep, vctrl_source "smu"; the SMU back to 0 V and off
    after every supply). The supply goes back to its starting voltage at the end, also on an error. Returns the CSV
    path (results/vco/vco_vdd_<sample>_<stamp>.csv)."""
    vco_lut.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = vco_lut.RESULTS_DIR / "vco_vdd_{}_{}.csv".format(sample or "nosample",
                                                                 datetime.now().strftime("%Y%m%d_%H%M%S"))
    supply = pll_setup.PllSupplyChannel(channel=SUPPLY_CHANNEL)
    try:
        for k, vdd in enumerate(vdds, 1):
            supply.set(vdd, settle=SUPPLY_SETTLE)
            logging.info("=== open loop, supply %d/%d: %.3f V ===", k, len(vdds), vdd)
            vco_pnm_sweep(open_loop_points(points), sample=sample, vctrl_source="smu", supply=supply, vdd_set=vdd,
                          csv_path=csv_path)
    finally:
        supply.close()  # back to the starting voltage; CH1 and the outputs untouched
    logging.info("Open-loop PLL supply sweep written to %s", csv_path)
    return csv_path


def start_log_file():
    """Also write the log to results/logs/pll_test_vdd_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_test_vdd_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():  # core in reset: no pollution
        # PLL supply on the E36312A CH2 (CH1 powers the board: untouched). Vctrl pad off. 9 supplies x 2 settings,
        # ~2-3 min each (~45 min), unattended
        # (done 2026-10-21 18:13, pll_test_vdd_S5_20261021_181301)
        # vdd_sweep(sample="S5")
        # Open loop: the SMU on the Vctrl pin header (potentiometer disconnected), retuned at every supply.
        # 9 supplies x 2 settings, ~3 min each (~1 h), unattended (run 2026-10-22, vco_vdd_S5_20261022_084755)
        # vco_vdd_sweep(sample="S5")
        # Reference current from a battery: both settings once at the nominal supply (~5 min), compare with the
        # 0.75 V rows of pll_test_vdd_S5_20261021_181301 (done 2026-10-22, pll_test_vdd_S5_20261022_131911)
        # vdd_sweep(vdds=(0.75,), sample="S5")
        # Reference current and PLL supply from batteries (E36312A not used): both settings once (~5 min)
        # (run 2026-10-26, pll_test_vdd_S5_20261026_121721 and _154253)
        # vdd_sweep(vdds=None, sample="S5")
        # The same with the FPGA unplugged during every measurement (attended: Enter after every (un)plug)
        # (run 2026-10-26, pll_test_vdd_S5_20261026_161259: 760 MHz 151 ps, within the spread of the runs with the
        # FPGA connected; 1 GHz lost its carrier after the unplug. Not pursued)
        # vdd_sweep(vdds=None, sample="S5", unplug_fpga=True)
        vdd_sweep(vdds=None, sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

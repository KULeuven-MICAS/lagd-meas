# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Open-loop VCO measurement bench: the Keithley 2450 SMU drives the Vctrl pad, the R&S RTB2000 scope measures
# the VCO divided down on the output pad, and the PLL configuration (VCO codes, divider) is loaded over the
# FPGA link (sw/lib/pll_setup.py). Contains the per-point measurement with the adaptive divider and the
# clock-quality checks, the equipment checks, single Vctrl sweeps and the full current-family sweep.
# The lookup table built on top of this is in sw/lib/vco_lut.py.

import csv
import logging
import math
import time
from datetime import datetime
from pathlib import Path

import pyvisa
import yaml

from sw.lib import pll_setup
from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keysight_fg_33600 import KeysightFG33600
from sw.lib.lab_instruments.drivers.keithley_smu_2450 import KeithleySMU2450
from sw.lib.lab_instruments.drivers.rs_scope_rtb2000 import RSScopeRTB2000
from sw.lib.pll_command_api import calculate_div_factor, pack_pll_cfg
from sw.lib.pll_settings import VCO_CHARAC_CFG
from sw.lib.vco_lut import CODES, HOLD_MAX, HOLD_MIN, LUT_FIELDS, RESULTS_DIR

logger = logging.getLogger(__name__)

INSTR_CFG_PATH = Path(__file__).resolve().parent / "lab_instruments" / "config" / "meas_setup.yaml"

# Columns of one measured VCO point (see measure_vco_point).
POINT_COLUMNS = ("vctrl_set", "vctrl_meas", "i_ctrl", "f_meas", "f_std", "n_valid", "f_vco", "clock",
                 "set_div_freq", "clk_div_val", "total_div")
# `clock` of a point; f_vco is only filled in for "ok" (f_meas/f_std/n_valid keep the raw scope values):
#   ok            stable clock, in range or confirmed by a divider change
#   no_clock      amplitude below MIN_VPP
#   unstable      fewer than half the readings valid, or spread above CLOCK_MAX_REL_STD
#   inconsistent  f_vco changed by more than DIVIDER_CHECK_TOL when the divider changed: the scope
#                 is not seeing the divided VCO (bursting or stopping oscillator)
#   unverified    out of range and the divider cannot move to confirm it
#   error         instrument error during the point (logged, scope recovered, sweep continues)
CLOCK_MAX_REL_STD = 0.10
DIVIDER_CHECK_TOL = 0.10
# The divided clock on the scope is kept in this range by adapting the divider (measure_vco).
# Low enough that the pad and probe still pass a square wave (above ~20 MHz it looks sinusoidal).
SCOPE_F_RANGE = (2e6, 10e6)
SCOPE_F_TARGET = 5e6
# Highest input frequency the external divider (clk_div_val) was seen to work at; faster
# VCOs are pre-divided inside the PLL with set_div_freq (2**n).
EXT_DIV_F_MAX = 1.25e9
# Divider every curve starts from: /32 inside the PLL, /20 outside (total /640). The fastest
# VCO seen (~12 GHz) reaches the external divider at 375 MHz and the scope at ~19 MHz.
START_DIVIDER = {"set_div_freq": 5, "clk_div_val": 9}
# Below this amplitude on the scope there is no clock (noise): the point is not a measurement.
MIN_VPP = 0.05


# ---------------------------------------------------------------------------------------------
# Instruments and PLL
# ---------------------------------------------------------------------------------------------
def load_instr_cfg():
    """Load the lab instrument descriptions from meas_setup.yaml."""
    with INSTR_CFG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def open_vco_instruments(vctrl, scope_ch=1, probe_att=10):
    """Open the SMU (output on at `vctrl`) and the scope (measurements on `scope_ch`)."""
    config = load_instr_cfg()
    smu = KeithleySMU2450(inst.BaseInstrumentData.from_mapping(config["smu_vctrl"]))
    scope = RSScopeRTB2000(inst.BaseInstrumentData.from_mapping(config["scope"]))
    smu.set_voltage(vctrl)
    smu.output_on()
    scope.set_probe_attenuation(scope_ch, probe_att)
    scope.autoscale()
    scope.set_measurement(1, scope_ch, "FREQ")
    scope.set_measurement(2, scope_ch, "PEAK")
    scope.set_measurement(3, scope_ch, "MEAN")
    scope.run()
    return smu, scope


def set_vctrl(smu, v, settle=0.3):
    """Step Vctrl, wait until the SMU is there, then give the VCO and scope `settle` [s]."""
    smu.set_voltage(v)
    smu.wait_settled(v)
    time.sleep(settle)


def load_vco(pll, cfg):
    """LOAD a config on already opened ports (see pll_setup.open_pll) and check the readback."""
    word = pack_pll_cfg(**cfg)
    pll.load(word)
    readback = pll.readback()
    if readback != word:
        raise RuntimeError(f"PLL readback {readback} does not match the loaded config 0x{word:012X}")


# ---------------------------------------------------------------------------------------------
# One measured point: adaptive divider and clock-quality checks
# ---------------------------------------------------------------------------------------------
def divider_for(cfg, f_vco, target=SCOPE_F_TARGET):
    """Divider settings {set_div_freq, clk_div_val} that bring `f_vco` closest to `target` on the pad.

    Output path used for the VCO characterization: pll_clk_o_en = 0 and clk_div_en = 1,
    so total division = 2**set_div_freq * 2 * (clk_div_val + 1) (calculate_div_factor).
    set_div_freq is the smallest pre-division that keeps the external divider input at or
    below EXT_DIV_F_MAX; clk_div_val then sets the scope frequency.
    """
    if cfg["pll_clk_o_en"] != 0 or cfg["clk_div_en"] != 1:
        raise ValueError("divider_for needs the external divider path (pll_clk_o_en=0, clk_div_en=1)")
    set_div_freq = next((n for n in range(8) if f_vco / 2 ** n <= EXT_DIV_F_MAX), 7)  # 3-bit field
    clk_div_val = round(f_vco / (target * 2 ** set_div_freq * 2)) - 1
    return {"set_div_freq": set_div_freq, "clk_div_val": min(max(clk_div_val, 0), 1023)}  # 10-bit field


def reset_divider(cfg):
    """Back to START_DIVIDER in `cfg` (not loaded). Used before a new curve or sweep: a divider
    adapted to a slow VCO puts a fast one beyond the scope (e.g. 1.2 GHz / 4)."""
    cfg.update(START_DIVIDER)


def measure_vco(pll, smu, scope, scope_ch, cfg, vctrl_set, settle=0.3, n_read=10, fit_passes=2, max_adjust=3):
    """Measure one point and keep the scope frequency within SCOPE_F_RANGE.

    When the divided clock falls outside the range, the divider in `cfg` is changed (and
    loaded) so it lands near SCOPE_F_TARGET, and the point is measured again; the new
    reading must give the same f_vco (a real clock scales with the divider). When there is
    no good clock (see `clock` in POINT_COLUMNS), the divider goes back to START_DIVIDER
    once (a too small divider can outrun the scope or the external divider). f_vco is always
    computed from the divider that was loaded for the returned measurement.
    """
    tried = []  # dividers used during this point
    f_before = None  # f_vco of the out-of-range reading that the current divider must confirm
    for attempt in range(max_adjust + 1):
        _, total_div = calculate_div_factor(cfg)
        current = {k: cfg[k] for k in START_DIVIDER}
        tried.append(current)
        try:
            point = measure_vco_point(smu, scope, scope_ch, total_div, vctrl_set, n_read=n_read,
                                      fit_passes=fit_passes)
        except (ValueError, pyvisa.errors.VisaIOError):
            logger.exception("Instrument error at Vctrl %.4f V: point not measured", vctrl_set)
            try:
                scope.recover()
            except Exception:
                logger.exception("Scope recovery failed, continuing")
            point = dict({k: math.nan for k in POINT_COLUMNS}, vctrl_set=vctrl_set, n_valid=0, clock="error")
        point.update(set_div_freq=cfg["set_div_freq"], clk_div_val=cfg["clk_div_val"], total_div=total_div)
        if point["clock"] == "error":
            return point
        confirmed = f_before is not None
        if point["clock"] == "ok" and confirmed and abs(point["f_vco"] - f_before) > DIVIDER_CHECK_TOL * f_before:
            logger.warning("f_vco %.2f MHz before the divider change, %.2f MHz after: not the divided VCO",
                           f_before / 1e6, point["f_vco"] / 1e6)
            point.update(clock="inconsistent", f_vco=math.nan)
        f_scope = point["f_meas"]
        last = attempt == max_adjust

        if point["clock"] != "ok":
            # Retry at the start divider: once coming from another divider, once more when the first
            # reading at the start divider was bad (the scope may still be settling after a new config).
            if tried.count(START_DIVIDER) >= 2 or last:
                return point  # still no good clock: record the point as not measured
            new, f_before = dict(START_DIVIDER), None
            logger.info("Clock %s: divider %s -> start divider %s", point["clock"], current, new)
        elif SCOPE_F_RANGE[0] <= f_scope <= SCOPE_F_RANGE[1]:
            return point
        else:
            new = divider_for(cfg, point["f_vco"])
            if new == current or new in tried or last:
                if confirmed:
                    return point  # out of range, but this reading agrees with the one before the change
                logger.warning("Scope at %.2f MHz, outside %s MHz, and the divider cannot move to confirm it",
                               f_scope / 1e6, [f / 1e6 for f in SCOPE_F_RANGE])
                point.update(clock="unverified", f_vco=math.nan)
                return point
            f_before = point["f_vco"]
            logger.info("Scope at %.2f MHz: divider %s -> %s", f_scope / 1e6, current, new)
        cfg.update(new)
        load_vco(pll, cfg)
        time.sleep(settle)
        fit_passes = 2  # the scope frequency jumped
    return point


def measure_vco_point(smu, scope, scope_ch, total_div, vctrl_set, n_read=10, fit_passes=2):
    """Fit the scope to the clock and measure one point; returns a dict with the measured
    POINT_COLUMNS (the divider columns are added by measure_vco).

    `fit_passes` scope fits (a second pass refines on the first; one is enough when the
    frequency moved little since the previous point), then `n_read` frequency readings.
    `clock` is "no_clock", "unstable" or "ok"; f_vco is NaN unless "ok".
    """
    for _ in range(fit_passes):
        if not scope.fit_to_signal(scope_ch, freq_slot=1, peak_slot=2, mean_slot=3, min_vpp=MIN_VPP):
            scope.autoscale()  # lost the signal (big frequency jump): search again
    vpp = scope.wait_valid(2)  # NaN right after an autoscale or while the trace is clipped
    if math.isnan(vpp) or vpp < MIN_VPP:
        logger.warning("No clock on the scope (%.3f Vpp): point not measured", vpp)
        f_mean, f_std, n, clock = math.nan, math.nan, 0, "no_clock"
    else:
        f_mean, f_std, n = scope.measure_stats(1, n=n_read)
        clock = "ok"
        if n < n_read // 2 + 1 or math.isnan(f_mean) or f_std > CLOCK_MAX_REL_STD * f_mean:
            logger.warning("Unstable clock: %d/%d valid readings, spread %.1f %%",
                           n, n_read, 100 * f_std / f_mean if n and f_mean else math.nan)
            clock = "unstable"
    v_meas, i_meas = smu.measure()
    logger.info("Vctrl %.4f V (%.2e A): f_vco %.2f MHz (std %.2e Hz, n=%d, %s)",
                v_meas, i_meas, f_mean * total_div / 1e6, f_std * total_div, n, clock)
    return dict(vctrl_set=vctrl_set, vctrl_meas=v_meas, i_ctrl=i_meas, f_meas=f_mean, f_std=f_std, n_valid=n,
                f_vco=f_mean * total_div if clock == "ok" else math.nan, clock=clock)


# ---------------------------------------------------------------------------------------------
# Equipment checks
# ---------------------------------------------------------------------------------------------
def test_function_generator(channel=1, freqs=(1e6, 10e6, 20e6), vpp=0.75, offset=0.375):
    """Equipment check: step the 33600A through a few square-wave frequencies.

    The settings are read back from the instrument; check the waveform on the
    scope (high-Z input, 0 -> 0.75 V square) at each step.
    """
    config = load_instr_cfg()
    fg = KeysightFG33600(inst.BaseInstrumentData.from_mapping(config["function_generator"]))
    fg.set_verbose(True)
    ok = True
    try:
        fg.status()
        fg.set_load(channel, "INF")
        fg.set_square(channel, freqs[0], vpp, offset)
        fg.output_on(channel)
        for freq in freqs:
            fg.set_frequency(channel, freq)
            f_rb, vpp_rb, off_rb = fg.get_frequency(channel), fg.get_amplitude(channel), fg.get_offset(channel)
            step_ok = abs(f_rb - freq) < 1e-6 * freq and abs(vpp_rb - vpp) < 1e-3 and abs(off_rb - offset) < 1e-3
            ok &= step_ok
            logger.info("%s: FG ch%d set %.3f MHz -> readback %.3f MHz, %.3f Vpp, offset %.3f V",
                        "PASS" if step_ok else "FAIL", channel, freq / 1e6, f_rb / 1e6, vpp_rb, off_rb)
            input("Check the scope, press Enter for the next step...")
    finally:
        fg.close()
    return ok


def test_fg_to_scope(fg_ch=1, scope_ch=1, freqs=(1e6, 10e6, 20e6), vpp=0.75, offset=0.375,
                     duty=50.0, f_tol=1e-3, vpp_tol=0.1, duty_tol=2.0):
    """Equipment check: FG square wave into the scope, the scope measures it back.

    FG channel `fg_ch` must be cabled to scope channel `scope_ch` (1 MOhm input).
    Each step passes when the measured frequency is within `f_tol` (relative) and
    the measured peak-to-peak within `vpp_tol` [V] and the duty cycle within
    `duty_tol` [%] of the programmed values.
    """
    config = load_instr_cfg()
    fg = KeysightFG33600(inst.BaseInstrumentData.from_mapping(config["function_generator"]))
    scope = RSScopeRTB2000(inst.BaseInstrumentData.from_mapping(config["scope"]))
    ok = True
    try:
        fg.status()
        scope.status()
        fg.set_load(fg_ch, "INF")
        fg.set_square(fg_ch, freqs[0], vpp, offset, duty)
        fg.output_on(fg_ch)

        scope.set_probe_attenuation(scope_ch, 1)  # direct BNC cable from the FG
        scope.autoscale()
        scope.set_measurement(1, scope_ch, "FREQ")
        scope.set_measurement(2, scope_ch, "PEAK")
        scope.set_measurement(3, scope_ch, "MEAN")
        scope.set_measurement(4, scope_ch, "PDCY")  # positive duty cycle [%]
        scope.run()

        for freq in freqs:
            fg.set_frequency(fg_ch, freq)
            time.sleep(1.0)  # let the acquisition and measurements settle
            for _ in range(2):  # second pass refines on the settings of the first
                scope.fit_to_signal(scope_ch, freq_slot=1, peak_slot=2, mean_slot=3)
            f_mean, f_std, n = scope.measure_stats(1)
            vpp_mean, _, _ = scope.measure_stats(2, n=3)
            duty_mean, duty_std, _ = scope.measure_stats(4)
            step_ok = (abs(f_mean - freq) < f_tol * freq and abs(vpp_mean - vpp) < vpp_tol
                       and abs(duty_mean - duty) < duty_tol)
            ok &= step_ok
            logger.info("%s: FG %.3f MHz -> scope %.6f MHz (std %.3e Hz, n=%d), %.3f Vpp, duty %.2f %% (std %.2f)",
                        "PASS" if step_ok else "FAIL", freq / 1e6, f_mean / 1e6, f_std, n, vpp_mean,
                        duty_mean, duty_std)
    finally:
        fg.close()
        scope.close()
    return ok


def test_smu(voltages=(0.0, 0.375, 0.75), settle=0.2, v_tol=2e-3, i_max=1e-6):
    """Equipment check: step the 2450 through a few Vctrl values and read V and I back.

    Vctrl is a gate, so the measured current should be ~0 (leakage only). Check
    the voltage at the pad with the scope or a DMM at each step.
    """
    config = load_instr_cfg()
    smu = KeithleySMU2450(inst.BaseInstrumentData.from_mapping(config["smu_vctrl"]))
    smu.set_verbose(True)
    ok = True
    try:
        smu.status()
        smu.output_on()
        for v_set in voltages:
            smu.set_voltage(v_set)
            time.sleep(settle)
            v_meas, i_meas = smu.measure()
            step_ok = abs(v_meas - v_set) < v_tol and abs(i_meas) < i_max and not smu.in_compliance()
            ok &= step_ok
            logger.info("%s: SMU set %.4f V -> measured %.4f V, %.3e A",
                        "PASS" if step_ok else "FAIL", v_set, v_meas, i_meas)
            input("Check the Vctrl pad, press Enter for the next step...")
    finally:
        smu.close()
    return ok


# ---------------------------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------------------------
def vctrl_sweep(vco_settings, vctrls=None, scope_ch=1, probe_att=10, settle=0.3, csv_path=None):
    """Open-loop VCO tuning curve: sweep Vctrl with the SMU, measure f on the scope.

    `vco_settings` is a dict with the LUT_FIELDS (other keys are ignored, so a
    config from pll_settings can be passed as-is). They are applied on top of
    VCO_CHARAC_CFG: phase detector off, Vctrl from the pad, output divided by
    calculate_div_factor (divider adapted per point, see measure_vco). Scope
    channel `scope_ch` must see that divided clock through a `probe_att`:1 probe.
    One CSV row per Vctrl point, written as it is measured.
    """
    if vctrls is None:
        vctrls = [round(0.025 * i, 4) for i in range(31)]  # 0 -> 0.75 V, 25 mV steps
    cfg = VCO_CHARAC_CFG.copy()
    cfg.update({k: vco_settings[k] for k in LUT_FIELDS})
    reset_divider(cfg)
    _, total_div = calculate_div_factor(cfg)
    if csv_path is None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = RESULTS_DIR / "vctrl_sweep_c{}_min{}_max{}_{}.csv".format(
            *(cfg[k] for k in LUT_FIELDS), stamp)

    pll = pll_setup.open_pll(cfg)
    logger.info("VCO %s, output divided by %d", {k: cfg[k] for k in LUT_FIELDS}, total_div)

    smu, scope = open_vco_instruments(vctrls[0], scope_ch, probe_att)
    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(LUT_FIELDS) + list(POINT_COLUMNS))
            writer.writeheader()
            for v in vctrls:
                set_vctrl(smu, v, settle)
                row = {k: cfg[k] for k in LUT_FIELDS}
                row.update(measure_vco(pll, smu, scope, scope_ch, cfg, v, settle))
                writer.writerow(row)
                f.flush()  # keep what was measured if the sweep is interrupted
    finally:
        smu.close()  # back to 0 V, output off
        scope.close()
    logger.info("Sweep written to %s", csv_path)
    return csv_path


def vco_current_families(coarse_codes=(6, 7, 8, 9), vctrls=None, hold_min=HOLD_MIN, hold_max=HOLD_MAX, scope_ch=1,
                         probe_att=10, settle=0.2, n_read=5):
    """Full Vctrl curves for every vco_current_max and every vco_current_min code (for plots).

    Per vco_tune_coarse in `coarse_codes`:
      - 16 curves sweeping vco_current_max 0..15, vco_current_min held at `hold_min`
        (15: least off-current, so the max setting is seen on its own);
      - 16 curves sweeping vco_current_min 0..15, vco_current_max held at `hold_max`
        (0: most current).
    Every curve is a Vctrl sweep (default 0 -> 0.75 V in 50 mV steps). All points go to one
    results/vco/vco_families_<stamp>.csv (column `swept` names the family), plotted in
    sw/tools/notebooks/calibrate_vco.ipynb.
    """
    if vctrls is None:
        vctrls = [round(0.05 * i, 4) for i in range(16)]  # 0 -> 0.75 V, 50 mV steps
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "vco_families_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))

    cfg = VCO_CHARAC_CFG.copy()
    cfg.update(vco_tune_coarse=coarse_codes[0], vco_current_min=hold_min, vco_current_max=hold_max)
    pll = pll_setup.open_pll(cfg)

    n_curves = len(coarse_codes) * 2 * len(CODES)
    smu, scope = open_vco_instruments(vctrls[0], scope_ch, probe_att)
    t_start, i_curve = time.time(), 0  # after the instrument setup, so the ETA counts curves only
    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["swept"] + list(LUT_FIELDS) + list(POINT_COLUMNS))
            writer.writeheader()
            for coarse in coarse_codes:
                for field, held in (("vco_current_max", {"vco_current_min": hold_min}),
                                    ("vco_current_min", {"vco_current_max": hold_max})):
                    for code in CODES:
                        cfg.update(held, vco_tune_coarse=coarse, **{field: code})
                        reset_divider(cfg)
                        set_vctrl(smu, vctrls[0], settle)
                        load_vco(pll, cfg)
                        i_curve += 1
                        logger.info("Curve %d/%d: %s", i_curve, n_curves, {k: cfg[k] for k in LUT_FIELDS})
                        for i, v in enumerate(vctrls):
                            set_vctrl(smu, v, settle)
                            row = {"swept": field}
                            row.update({k: cfg[k] for k in LUT_FIELDS})
                            # Two fits on the first point: the config change moves f a lot.
                            row.update(measure_vco(pll, smu, scope, scope_ch, cfg, v, settle, n_read=n_read,
                                                   fit_passes=2 if i == 0 else 1))
                            writer.writerow(row)
                        f.flush()  # keep what was measured if the run is interrupted
                        per_curve = (time.time() - t_start) / i_curve
                        logger.info("%.0f s per curve, ~%.0f min to go",
                                    per_curve, per_curve * (n_curves - i_curve) / 60)
    finally:
        smu.close()  # back to 0 V, output off
        scope.close()
    logger.info("Families written to %s", csv_path)
    return csv_path

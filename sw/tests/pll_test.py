# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

#
# The reusable PLL command layer lives in lib/pll_driver.py (PllDriver); this
# file is the top script for configuring the Pomelo PLL test structure.
#
# Interactive helpers (after `python -i tests/pll_test.py` from sw/):
#   open_ports()                       # open the ports -> module-global `pll`
#   pll.writeback()                    # liveness self-test (echoes 0xFF)
#   pll.load_cfg(pdown_PD=0, ...)      # build + LOAD a 47-bit config from fields
#   pll.verify_load(word)              # LOAD + echo the 6 bytes back (FPGA echo)
#   pll.readback()                     # scan the 47 bits back out of the PLL data_o
#   pll.verify(word)                   # LOAD then READBACK == word (silicon check)
#   pll.is_locked() / pll.wait_lock()  # read the PLL lock status (pll_lock_i)
#   pll.reset()                        # reset PLL registers to defaults
#   pll.clk_sel(0|1)                   # 0 = PLL drives SoC clock, 1 = reference
#   pll.bring_up(lock_timeout=..., ...) # configure -> wait for lock -> switch
#   pll.set_strb_hz(hz)                # retune the config strobe -> actual Hz
#
# Related to: fpga/src/verilog/pll_controller.sv and pll_command_api.sv

import csv
import math
import sys
import logging
import time
from datetime import datetime
from pathlib import Path

import pyvisa
import yaml

from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keysight_fg_33600 import KeysightFG33600
from sw.lib.lab_instruments.drivers.keithley_smu_2450 import KeithleySMU2450
from sw.lib.lab_instruments.drivers.rs_scope_rtb2000 import RSScopeRTB2000
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_driver import PllDriver
from sw.lib.pll_command_api import (
    calculate_div_factor,
    pack_pll_cfg,
    default_cfg_word,
    OP_WRITEBACK,
    STRB_HZ,
    CFG_BITS,
    header,
)

from sw.lib.pll_settings import *
from sw.lib import vco_calibration

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Device files for the PLL write/read ports (8-bit Xillybus stream).
WRITE_DEV = "/dev/xillybus_write_8"
READ_DEV = "/dev/xillybus_read_8"

INSTR_CFG_PATH = Path(__file__).resolve().parent.parent / "lib" / "lab_instruments" / "config" / "meas_setup.yaml"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "vco"  # results/ is gitignored
LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

VCO_FIELDS = ("vco_tune_coarse", "vco_current_min", "vco_current_max")
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

# Populated by open_ports(); declared here so the interactive helpers below
# (and `python -i tests/pll_test.py` sessions) can refer to it as a global.
pll: PllDriver


def open_ports():
    """Open the PLL ports, exposing them via the module-global `pll`."""
    global pll
    pll = PllDriver(WRITE_DEV, READ_DEV)
    pll.open()


def test_writeback():
    """Send one WRITEBACK command and check the 0xFF header loops back.

    This is the controller-liveness check: it proves the host->FPGA read/write
    path and the command decode are all working, without touching the PLL.
    """
    expected = header(OP_WRITEBACK)  # 0xFF
    received = pll.writeback()
    if received is None:
        logging.error("FAIL: writeback sent 0x%02X, received None", expected)
        return False
    if received == expected:
        logging.info("PASS: writeback echoed 0x%02X. The PLL controller is alive.", received)
        return True
    logging.error("FAIL [mismatch]: writeback sent 0x%02X, received 0x%02X", expected, received)
    return False


def test_strb_config(rates=(1_000, 10_000, 100_000, 1_000_000), reps=5):
    """Verify CONFIG_STRB actually changes the strobe rate.

    Uses LOAD_LOOPBACK: the controller echoes the 6 payload bytes only after all
    47 bits have been shifted and committed, so the round-trip time is dominated
    by the strobe rate. Timing it is what proves the divider moved -- a correct
    echo on its own would come back from a stuck divider too.

    Needs neither the chip nor the PLL: the strobes are driven on the pll_* pins
    whether or not anything is listening, and the echo comes from the FPGA. Use
    test_strb_config_silicon() for the version that reads the PLL back.
    """
    word = default_cfg_word()
    ok, elapsed = True, {}
    for hz in rates:
        actual = pll.set_strb_hz(hz)
        t0 = time.time()
        echoes_ok = all(pll.verify_load(word) == word for _ in range(reps))
        elapsed[hz] = time.time() - t0
        wire = reps * (CFG_BITS + 1) / actual
        ok &= echoes_ok
        logging.info(
            "%s: %8.0f Hz requested -> %10.2f Hz actual | %d echoes %s | wire %6.3f s, measured %6.3f s",
            "PASS" if echoes_ok else "FAIL",
            hz,
            actual,
            reps,
            "ok" if echoes_ok else "MISMATCH/TIMEOUT",
            wire,
            elapsed[hz],
        )

    # The rate really changed: the slowest sweep point must take far longer than
    # the fastest. A stuck divider (either direction) collapses this ratio.
    slow, fast = elapsed[min(rates)], elapsed[max(rates)]
    ratio_ok = slow > fast * 5
    ok &= ratio_ok
    logging.info(
        "%s: %.0f Hz took %.3f s vs %.3f s at %.0f Hz (%.1fx, need >5x)",
        "PASS" if ratio_ok else "FAIL",
        min(rates),
        slow,
        fast,
        max(rates),
        slow / fast if fast else float("inf"),
    )

    pll.set_strb_hz(STRB_HZ)  # back to the power-on rate
    return ok


def test_strb_config_silicon(rates=(1_000, 10_000, 100_000)):
    """Sweep the strobe rate and confirm the PLL silicon still captures the config.

    Unlike test_strb_config this DOES need the chip and pll_data_i wired (FMC
    LA06_N): each step LOADs a config and scans it back out of data_o. A rate the
    FMC wiring cannot sustain shows up as a mismatch, which is the point -- both
    strobes are gated clocks into the PLL, so this is where the practical ceiling
    is found.
    """
    ok = True
    word = default_cfg_word()
    for hz in rates:
        actual = pll.set_strb_hz(hz)
        pll.load(word)
        received = pll.readback()
        step_ok = received == word
        ok &= step_ok
        logging.info(
            "%s: %8.0f Hz requested -> %10.2f Hz actual, readback %s",
            "PASS" if step_ok else "FAIL",
            hz,
            actual,
            f"0x{received:012X}" if received is not None else "None (timeout)",
        )
    pll.set_strb_hz(STRB_HZ)  # back to the power-on rate
    return ok


def start_load_config(cfg):
    """Start loading a configuration into the PLL."""
    open_ports()

    if not test_writeback():
        return 1

    # Tune the strobe rate, 1kHz
    pll.set_strb_hz(STRB_HZ)

    # Put the PLL registers in a known state before configuring them.
    pll.reset()
    # Set the clock mux to the external reference
    pll.select_reference()

    # Build and load a config
    # word = default_cfg_word(set_clk_out=1, set_div_freq=0b000, pll_clk_o_en=1)
    word = pack_pll_cfg(**cfg)
    if pll.verify_load(word) == word:
        logging.info("config check OK: 0x%012X", word)
        logging.info("Division factor on chip clock: %d, total: %d", *calculate_div_factor(cfg))
    else:
        logging.error("config check FAILED: 0x%012X", word)
    # Per-field overrides instead of the packed word:
    #   word = pll.load_default(vco_tune_coarse=0xA)
    #   word = pll.load_cfg(pdown_PD=0, pdown_VCO=0)   # reset defaults elsewhere

    # READBACK the chip's shallow register out of the PLL's data_o (recirculating,
    # so it is non-destructive).
    readback = pll.readback()
    logging.info("readback = 0x%012X", readback)
    assert readback == word


def setup_pll_bypass():
    """Worked example of the PLL command set."""
    start_load_config(PLL_BYPASS_CFG)

    # Move the SoC onto the PLL
    locked = pll.wait_lock(timeout=3)
    if locked:
        pll.select_pll()
        logging.info("PLL lock = %s and selected as the SoC clock", pll.read_lock())
    else:
        logging.error("PLL did not lock; SoC left on the reference clock")

    # =====================================================================
    # Optional deeper checks -- none of these are required to use the script
    # =====================================================================
    # test_strb_config()           # sweep + time the strobe      (no chip needed)
    # test_strb_config_silicon()   # sweep verified against the PLL (needs chip)

    return 0


def charge_pump_sanity_check():
    """Power down phase detector, assert charge pump behavior in Vctrl node."""
    start_load_config(PD_OFF_CFG)


def debug_phase_detector():
    """Phase detector debug test.
    Set different or same clocks to both reference and feedback clock pads and check Vctrl node.
    Check 'locked pin for correct behavior.
    """
    start_load_config(PD_DEBUG_CFG)

    locked = pll.wait_lock(timeout=3)
    if locked:
        logging.info("PLL lock = %s and selected as the SoC clock", pll.read_lock())
    else:
        logging.error("PLL did not lock; SoC left on the reference clock")


def ctrl_voltage_transient():
    """Transient response of the control voltage node."""
    start_load_config(SAFE_LOOP_CFG)


def load_instr_cfg():
    """Load the lab instrument descriptions from meas_setup.yaml."""
    with INSTR_CFG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


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
            logging.info(
                "%s: FG ch%d set %.3f MHz -> readback %.3f MHz, %.3f Vpp, offset %.3f V",
                "PASS" if step_ok else "FAIL", channel, freq / 1e6, f_rb / 1e6, vpp_rb, off_rb,
            )
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
            logging.info(
                "%s: FG %.3f MHz -> scope %.6f MHz (std %.3e Hz, n=%d), %.3f Vpp, duty %.2f %% (std %.2f)",
                "PASS" if step_ok else "FAIL", freq / 1e6, f_mean / 1e6, f_std, n, vpp_mean,
                duty_mean, duty_std,
            )
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
            logging.info(
                "%s: SMU set %.4f V -> measured %.4f V, %.3e A",
                "PASS" if step_ok else "FAIL", v_set, v_meas, i_meas,
            )
            input("Check the Vctrl pad, press Enter for the next step...")
    finally:
        smu.close()
    return ok


def vctrl_sweep(vco_settings, vctrls=None, scope_ch=1, probe_att=10, settle=0.3, csv_path=None):
    """Open-loop VCO tuning curve: sweep Vctrl with the SMU, measure f on the scope.

    `vco_settings` is a dict with the VCO_FIELDS (other keys are ignored, so a
    config from pll_settings can be passed as-is). They are applied on top of
    VCO_CHARAC_CFG: phase detector off, Vctrl from the pad, output divided by
    calculate_div_factor (divider adapted per point, see measure_vco). Scope
    channel `scope_ch` must see that divided clock through a `probe_att`:1 probe.
    One CSV row per Vctrl point, written as it is measured.
    """
    if vctrls is None:
        vctrls = [round(0.025 * i, 4) for i in range(31)]  # 0 -> 0.75 V, 25 mV steps
    cfg = VCO_CHARAC_CFG.copy()
    cfg.update({k: vco_settings[k] for k in VCO_FIELDS})
    reset_divider(cfg)
    _, total_div = calculate_div_factor(cfg)
    if csv_path is None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = RESULTS_DIR / "vctrl_sweep_c{}_min{}_max{}_{}.csv".format(
            *(cfg[k] for k in VCO_FIELDS), stamp)

    if start_load_config(cfg):
        raise RuntimeError("PLL controller did not answer the writeback, VCO not configured")
    logging.info("VCO %s, output divided by %d", {k: cfg[k] for k in VCO_FIELDS}, total_div)

    smu, scope = open_vco_instruments(vctrls[0], scope_ch, probe_att)
    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(VCO_FIELDS) + list(POINT_COLUMNS))
            writer.writeheader()
            for v in vctrls:
                set_vctrl(smu, v, settle)
                row = {k: cfg[k] for k in VCO_FIELDS}
                row.update(measure_vco(smu, scope, scope_ch, cfg, v, settle))
                writer.writerow(row)
                f.flush()  # keep what was measured if the sweep is interrupted
    finally:
        smu.close()  # back to 0 V, output off
        scope.close()
    logging.info("Sweep written to %s", csv_path)
    return csv_path


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


def measure_vco(smu, scope, scope_ch, cfg, vctrl_set, settle=0.3, n_read=10, fit_passes=2, max_adjust=3):
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
            logging.exception("Instrument error at Vctrl %.4f V: point not measured", vctrl_set)
            try:
                scope.recover()
            except Exception:
                logging.exception("Scope recovery failed, continuing")
            point = dict({k: math.nan for k in POINT_COLUMNS}, vctrl_set=vctrl_set, n_valid=0, clock="error")
        point.update(set_div_freq=cfg["set_div_freq"], clk_div_val=cfg["clk_div_val"], total_div=total_div)
        if point["clock"] == "error":
            return point
        confirmed = f_before is not None
        if point["clock"] == "ok" and confirmed and abs(point["f_vco"] - f_before) > DIVIDER_CHECK_TOL * f_before:
            logging.warning("f_vco %.2f MHz before the divider change, %.2f MHz after: not the divided VCO",
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
            logging.info("Clock %s: divider %s -> start divider %s", point["clock"], current, new)
        elif SCOPE_F_RANGE[0] <= f_scope <= SCOPE_F_RANGE[1]:
            return point
        else:
            new = divider_for(cfg, point["f_vco"])
            if new == current or new in tried or last:
                if confirmed:
                    return point  # out of range, but this reading agrees with the one before the change
                logging.warning("Scope at %.2f MHz, outside %s MHz, and the divider cannot move to confirm it",
                                f_scope / 1e6, [f / 1e6 for f in SCOPE_F_RANGE])
                point.update(clock="unverified", f_vco=math.nan)
                return point
            f_before = point["f_vco"]
            logging.info("Scope at %.2f MHz: divider %s -> %s", f_scope / 1e6, current, new)
        cfg.update(new)
        load_vco(cfg)
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
        logging.warning("No clock on the scope (%.3f Vpp): point not measured", vpp)
        f_mean, f_std, n, clock = math.nan, math.nan, 0, "no_clock"
    else:
        f_mean, f_std, n = scope.measure_stats(1, n=n_read)
        clock = "ok"
        if n < n_read // 2 + 1 or math.isnan(f_mean) or f_std > CLOCK_MAX_REL_STD * f_mean:
            logging.warning("Unstable clock: %d/%d valid readings, spread %.1f %%",
                            n, n_read, 100 * f_std / f_mean if n and f_mean else math.nan)
            clock = "unstable"
    v_meas, i_meas = smu.measure()
    logging.info("Vctrl %.4f V (%.2e A): f_vco %.2f MHz (std %.2e Hz, n=%d, %s)",
                 v_meas, i_meas, f_mean * total_div / 1e6, f_std * total_div, n, clock)
    return dict(vctrl_set=vctrl_set, vctrl_meas=v_meas, i_ctrl=i_meas, f_meas=f_mean, f_std=f_std, n_valid=n,
                f_vco=f_mean * total_div if clock == "ok" else math.nan, clock=clock)


def load_vco(cfg):
    """LOAD a config on the already opened ports (see start_load_config) and check the readback."""
    word = pack_pll_cfg(**cfg)
    pll.load(word)
    readback = pll.readback()
    if readback != word:
        raise RuntimeError(f"PLL readback {readback} does not match the loaded config 0x{word:012X}")


def vco_current_families(coarse_codes=(6, 7, 8, 9), vctrls=None, hold_min=vco_calibration.HOLD_MIN,
                         hold_max=vco_calibration.HOLD_MAX, scope_ch=1,
                         probe_att=10, settle=0.2, n_read=5):
    """Full Vctrl curves for every vco_current_max and every vco_current_min code (for plots).

    Per vco_tune_coarse in `coarse_codes`:
      - 16 curves sweeping vco_current_max 0..15, vco_current_min held at `hold_min`
        (15: least off-current, so the max setting is seen on its own);
      - 16 curves sweeping vco_current_min 0..15, vco_current_max held at `hold_max`
        (0: most current).
    Every curve is a Vctrl sweep (default 0 -> 0.75 V in 50 mV steps). All points go to one
    results/vco/vco_families_<stamp>.csv (column `swept` names the family); the choice of
    currents is made afterwards in sw/tools/notebooks/calibrate_vco.ipynb.
    """
    if vctrls is None:
        vctrls = [round(0.05 * i, 4) for i in range(16)]  # 0 -> 0.75 V, 50 mV steps
    codes = range(16)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "vco_families_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))

    cfg = VCO_CHARAC_CFG.copy()
    cfg.update(vco_tune_coarse=coarse_codes[0], vco_current_min=hold_min, vco_current_max=hold_max)
    if start_load_config(cfg):
        raise RuntimeError("PLL controller did not answer the writeback, VCO not configured")

    n_curves = len(coarse_codes) * 2 * len(codes)
    smu, scope = open_vco_instruments(vctrls[0], scope_ch, probe_att)
    t_start, i_curve = time.time(), 0  # after the instrument setup, so the ETA counts curves only
    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["swept"] + list(VCO_FIELDS) + list(POINT_COLUMNS))
            writer.writeheader()
            for coarse in coarse_codes:
                for field, held in (("vco_current_max", {"vco_current_min": hold_min}),
                                    ("vco_current_min", {"vco_current_max": hold_max})):
                    for code in codes:
                        cfg.update(held, vco_tune_coarse=coarse, **{field: code})
                        reset_divider(cfg)
                        set_vctrl(smu, vctrls[0], settle)
                        load_vco(cfg)
                        i_curve += 1
                        logging.info("Curve %d/%d: %s", i_curve, n_curves, {k: cfg[k] for k in VCO_FIELDS})
                        for i, v in enumerate(vctrls):
                            set_vctrl(smu, v, settle)
                            row = {"swept": field}
                            row.update({k: cfg[k] for k in VCO_FIELDS})
                            # Two fits on the first point: the config change moves f a lot.
                            row.update(measure_vco(smu, scope, scope_ch, cfg, v, settle, n_read=n_read,
                                                   fit_passes=2 if i == 0 else 1))
                            writer.writerow(row)
                        f.flush()  # keep what was measured if the run is interrupted
                        per_curve = (time.time() - t_start) / i_curve
                        logging.info("%.0f s per curve, ~%.0f min to go",
                                     per_curve, per_curve * (n_curves - i_curve) / 60)
    finally:
        smu.close()  # back to 0 V, output off
        scope.close()
    logging.info("Families written to %s", csv_path)
    return csv_path


# Lookup-table grid (vco_lut_measure defaults): Vctrl coarse where the curves are flat (PMOS fully on), 50 mV
# where they are steep; min 0 as reference plus 8..15 (codes 0..7 nearly saturate the ring on their own); max
# every other code plus 15.
LUT_VCTRLS = (0.0, 0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)
LUT_MIN_CODES = (0, 8, 9, 10, 11, 12, 13, 14, 15)
LUT_MAX_CODES = (0, 2, 4, 6, 8, 10, 12, 14, 15)
# Drift references (coarse, min, max, Vctrl), measured at the start and after every coarse code:
# at 0 V the curve is flat (PMOS fully on), so only the VCO itself (temperature, supply) moves it; at 0.65 V
# it is steep, so drift of the current source / Vctrl shows up as well.
LUT_DRIFT_REFS = ((8, 8, 8, 0.0), (8, 8, 8, 0.65))


def vco_lut_measure(sample=None, coarse_codes=range(16), min_codes=LUT_MIN_CODES, max_codes=LUT_MAX_CODES,
                    vctrls=LUT_VCTRLS, drift_refs=LUT_DRIFT_REFS, vdd=None, scope_ch=1, probe_att=10, settle=0.2,
                    n_read=5):
    """Measure the VCO lookup table used by configure_vco (rules: sw/lib/vco_calibration.py, choose_vco).

    Per coarse code, so every finished coarse code has complete curves if the run stops early:
      1. At Vctrl = `vdd` (SMU v_max), where only the min branch conducts: every vco_current_min 0..15
         (max = HOLD_MAX). The point is written once per code in `max_codes`, so every setting in the table
         has its VDD row (rule: the ring must still oscillate there).
      2. Per code in `min_codes` that oscillated at VDD, per Vctrl in `vctrls`: every code in `max_codes`.
      3. The drift references `drift_refs` = ((coarse, min, max, Vctrl), ...), also measured once before the
         first coarse code (`swept` = "drift"; read_lut leaves these rows out).
    Every row has a `time` stamp. Writes results/vco/vco_lut_<sample>_<stamp>.csv, flushed per curve.
    """
    if vdd is None:
        vdd = load_instr_cfg()["smu_vctrl"]["args"]["v_max"]
    vctrls = [v for v in vctrls if v < vdd - 1e-6]  # VDD itself is step 1
    codes = vco_calibration.CODES
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "vco_lut_{}_{}.csv".format(sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))

    logging.info("VCO lookup table: coarse %s, min %s (those oscillating at VDD), max %s, Vctrl %s V + VDD %.2f V, "
                 "drift references %s -> %s", list(coarse_codes), list(min_codes), list(max_codes), list(vctrls),
                 vdd, list(drift_refs), csv_path.name)

    cfg = VCO_CHARAC_CFG.copy()
    cfg.update(vco_tune_coarse=coarse_codes[0], vco_current_min=vco_calibration.HOLD_MIN,
               vco_current_max=vco_calibration.HOLD_MAX)
    if start_load_config(cfg):
        raise RuntimeError("PLL controller did not answer the writeback, VCO not configured")

    smu, scope = open_vco_instruments(vdd, scope_ch, probe_att)
    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["sample", "swept", "time"] + list(VCO_FIELDS) + ["vctrl"]
                                    + list(POINT_COLUMNS))
            writer.writeheader()

            def measure(vctrl):
                load_vco(cfg)
                time.sleep(settle)
                return measure_vco(smu, scope, scope_ch, cfg, vctrl, settle, n_read=n_read)

            def write(point, swept, vctrl, **codes_override):
                row = dict(point, sample=sample, swept=swept, vctrl=vctrl,
                           time=datetime.now().isoformat(timespec="seconds"), **{k: cfg[k] for k in VCO_FIELDS})
                row.update(codes_override)
                writer.writerow(row)

            def drift():
                for c, m, mx, v in drift_refs:
                    cfg.update(vco_tune_coarse=c, vco_current_min=m, vco_current_max=mx)
                    reset_divider(cfg)
                    set_vctrl(smu, v, settle)
                    point = measure(v)
                    write(point, "drift", v)
                    logging.info("Drift reference coarse %d, min %d, max %d, Vctrl %.3f V: f_vco %.2f MHz (%s)",
                                 c, m, mx, v, point["f_vco"] / 1e6, point["clock"])
                f.flush()

            drift()
            for coarse in coarse_codes:
                # 1. Which min codes keep the ring oscillating at VDD.
                logging.info("VDD %.2f V, coarse %d: vco_current_min 0..15", vdd, coarse)
                set_vctrl(smu, vdd, settle)
                reset_divider(cfg)
                runs_at_vdd = {}
                for m in codes:
                    cfg.update(vco_tune_coarse=coarse, vco_current_min=m, vco_current_max=vco_calibration.HOLD_MAX)
                    point = measure(vdd)
                    runs_at_vdd[m] = point["clock"] == "ok"
                    for mx in max_codes:  # at VDD the max branch is off: the same point for every max code
                        write(point, "vdd", vdd, vco_current_max=mx)
                f.flush()
                logging.info("Coarse %d: min codes with a clock at VDD: %s", coarse,
                             [m for m in codes if runs_at_vdd[m]])

                # 2. The Vctrl points for every allowed min code and every max code.
                for m in min_codes:
                    if not runs_at_vdd.get(m):
                        continue
                    cfg.update(vco_tune_coarse=coarse, vco_current_min=m)
                    reset_divider(cfg)
                    for vctrl in vctrls:
                        logging.info("Coarse %d, min %d, Vctrl %.3f V: vco_current_max %s", coarse, m, vctrl,
                                     list(max_codes))
                        set_vctrl(smu, vctrl, settle)
                        for mx in max_codes:
                            cfg["vco_current_max"] = mx
                            write(measure(vctrl), "window", vctrl)
                        f.flush()  # keep what was measured if the run is interrupted
                logging.info("Coarse %d done", coarse)

                # 3. Drift reference.
                drift()
    finally:
        smu.close()  # back to 0 V, output off
        scope.close()
    logging.info("VCO lookup table written to %s", csv_path)
    return csv_path


def configure_vco(f_vco, kvco, cfg=None, sample=None, lut_csv=None, window=vco_calibration.VCTRL_WINDOW,
                  margin=0.02):
    """Set the VCO for `f_vco` [Hz] with |Kvco| as close as possible to `kvco` [Hz/V].

    The setting comes from vco_calibration.choose_vco on a lookup table (`lut_csv`, else the newest
    results/vco/vco_lut_<sample>_*.csv): the ring must oscillate at Vctrl = VDD and f_vco must be reached
    inside `window` (with `margin`); only then is Kvco matched. The three codes are applied on `cfg`
    (default VCO_CHARAC_CFG: open loop, Vctrl from the pad; pass the PLL's config for closed loop) and
    loaded. Returns the pick ({codes, vctrl, kvco}); raises when no setting reaches f_vco.
    """
    if lut_csv is None:
        found = sorted(RESULTS_DIR.glob("vco_lut_{}_*.csv".format(sample) if sample else "vco_lut_*.csv"),
                       key=lambda p: p.stat().st_mtime)
        if not found:
            raise FileNotFoundError(f"no VCO lookup table in {RESULTS_DIR}, run vco_lut_measure() first")
        lut_csv = found[-1]
    best, alternatives = vco_calibration.choose_vco(vco_calibration.read_lut(lut_csv), f_vco, kvco,
                                                    window=window, margin=margin)
    if best is None:
        raise ValueError(f"no VCO setting reaches {f_vco / 1e6:.1f} MHz inside Vctrl {window[0]}-{window[1]} V "
                         f"({lut_csv})")
    logging.info("  (lookup table %s)", Path(lut_csv).name)
    for alt in alternatives:
        logging.info("  alternative: coarse %d, min %d, max %d -> Vctrl %.3f V, |Kvco| %.0f MHz/V",
                     alt["vco_tune_coarse"], alt["vco_current_min"], alt["vco_current_max"], alt["vctrl"],
                     alt["kvco"] / 1e6)
    cfg = dict(VCO_CHARAC_CFG if cfg is None else cfg)
    cfg.update({k: best[k] for k in VCO_FIELDS})
    if start_load_config(cfg):
        raise RuntimeError("PLL controller did not answer the writeback, VCO not configured")
    return best


def start_pll(cfg):
    start_load_config(cfg)

    # Move the SoC onto the PLL
    locked = pll.wait_lock(timeout=3)
    if locked:
        pll.select_pll()
        logging.info("PLL lock = %s and selected as the SoC clock", pll.read_lock())
    else:
        logging.error("PLL did not lock; SoC left on the reference clock")

    return 0


def start_log_file():
    """Also write the log to results/logs/pll_test_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_test_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # Equipment checks for the VCO characterization
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # test_function_generator(freqs=(1e6,))  # 1 MHz, 0 -> 0.75 V square
        # test_fg_to_scope()
        # test_smu()

        # VCO tuning curve for the CFG_REF8 settings (locked at ~1 GHz with an 8 MHz ref)
        # vctrl_sweep(CFG_REF8)

        # Full: Vctrl curves for every current setting per coarse code, for the plots in
        # sw/tools/notebooks/calibrate_vco.ipynb (this sample only)
        # vco_current_families(coarse_codes=range(16))  # all coarse codes, overnight

        # Quick check of the lookup-table measurement: one coarse code, two min codes, three Vctrl points (+ VDD),
        # default max codes, drift reference before and after -> ~70 points, ~3 min; writes vco_lut_debug_*.csv
        # vco_lut_measure(sample="debug", coarse_codes=(8,), min_codes=(0, 8), vctrls=(0.0, 0.4, 0.7))

        # Lookup table (overnight), then set the VCO for a frequency and Kvco from it
        vco_lut_measure(sample="S5")  # LUT_VCTRLS / LUT_MIN_CODES / LUT_MAX_CODES: ~13 h at ~3.3 s per point
        # configure_vco(1.0e9, 1.0e9, sample="S5")  # 1 GHz, |Kvco| ~1 GHz/V

    # cfg = CFG_REF4_OUT128MHZ.copy()
    # # Safer default config
    # sys.exit(start_pll(cfg))


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

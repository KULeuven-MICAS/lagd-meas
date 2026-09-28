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

import sys
import logging
import time
from pathlib import Path

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Device files for the PLL write/read ports (8-bit Xillybus stream).
WRITE_DEV = "/dev/xillybus_write_8"
READ_DEV = "/dev/xillybus_read_8"

INSTR_CFG_PATH = Path(__file__).resolve().parent.parent / "lib" / "lab_instruments" / "config" / "meas_setup.yaml"

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


def vco_characterization():
    """VCO characterization placeholder."""
    start_load_config(VCO_CHARAC_CFG)


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


if __name__ == "__main__":
    # Equipment checks for the VCO characterization
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # test_function_generator(freqs=(1e6,))  # 1 MHz, 0 -> 0.75 V square
        test_fg_to_scope()
        # test_smu()

    # cfg = CFG_REF4_OUT128MHZ.copy()
    # # Safer default config
    # sys.exit(start_pll(cfg))

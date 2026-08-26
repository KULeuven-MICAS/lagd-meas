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

from sw.lib.pll_driver import PllDriver
from sw.lib.pll_command_api import (
    default_cfg_word, OP_WRITEBACK, STRB_HZ, CFG_BITS, header,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Device files for the PLL write/read ports (8-bit Xillybus stream).
WRITE_DEV = '/dev/xillybus_write_8'
READ_DEV = '/dev/xillybus_read_8'

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
    expected = header(OP_WRITEBACK)            # 0xFF
    received = pll.writeback()
    if received is None:
        logging.error('FAIL: writeback sent 0x%02X, received None', expected)
        return False
    if received == expected:
        logging.info('PASS: writeback echoed 0x%02X. The PLL controller is alive.', received)
        return True
    logging.error('FAIL [mismatch]: writeback sent 0x%02X, received 0x%02X', expected, received)
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
        logging.info('%s: %8.0f Hz requested -> %10.2f Hz actual | %d echoes %s | '
                     'wire %6.3f s, measured %6.3f s',
                     'PASS' if echoes_ok else 'FAIL', hz, actual, reps,
                     'ok' if echoes_ok else 'MISMATCH/TIMEOUT', wire, elapsed[hz])

    # The rate really changed: the slowest sweep point must take far longer than
    # the fastest. A stuck divider (either direction) collapses this ratio.
    slow, fast = elapsed[min(rates)], elapsed[max(rates)]
    ratio_ok = slow > fast * 5
    ok &= ratio_ok
    logging.info('%s: %.0f Hz took %.3f s vs %.3f s at %.0f Hz (%.1fx, need >5x)',
                 'PASS' if ratio_ok else 'FAIL', min(rates), slow, fast, max(rates),
                 slow / fast if fast else float('inf'))

    pll.set_strb_hz(STRB_HZ)   # back to the power-on rate
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
        step_ok = (received == word)
        ok &= step_ok
        logging.info('%s: %8.0f Hz requested -> %10.2f Hz actual, readback %s',
                     'PASS' if step_ok else 'FAIL', hz, actual,
                     f'0x{received:012X}' if received is not None else 'None (timeout)')
    pll.set_strb_hz(STRB_HZ)   # back to the power-on rate
    return ok


def main():
    """Worked example of the PLL command set."""
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
    word = default_cfg_word(set_clk_out=1, set_div_freq=0b000, pll_clk_o_en=1)
    if pll.verify_load(word) == word:
        logging.info('config check OK: 0x%012X', word)
    else:
        logging.error('config check FAILED: 0x%012X', word)
    # Per-field overrides instead of the packed word:
    #   word = pll.load_default(vco_tune_coarse=0xA)
    #   word = pll.load_cfg(pdown_PD=0, pdown_VCO=0)   # reset defaults elsewhere

    # READBACK the chip's shallow register out of the PLL's data_o (recirculating,
    # so it is non-destructive).
    readback = pll.readback()
    logging.info('readback = 0x%012X', readback)
    assert readback == word

    # Move the SoC onto the PLL
    locked = pll.wait_lock(timeout=3)
    if locked:
        pll.select_pll()
        logging.info('PLL lock = %s and selected as the SoC clock', pll.read_lock())
    else:
        logging.error('PLL did not lock; SoC left on the reference clock')

    # =====================================================================
    # Optional deeper checks -- none of these are required to use the script
    # =====================================================================
    # test_strb_config()           # sweep + time the strobe      (no chip needed)
    # test_strb_config_silicon()   # sweep verified against the PLL (needs chip)

    return 0


if __name__ == '__main__':
    sys.exit(main())

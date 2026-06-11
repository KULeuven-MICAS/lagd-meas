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
#
# Running this file directly executes the controller self-tests (see main()):
# writeback liveness + a LOAD_LOOPBACK config-path check. It does NOT switch the
# SoC clock onto the PLL -- do that deliberately via pll.bring_up()/select_pll()
# once you have confirmed lock on the scope (pll_lock_o is not wired to the FPGA).
#
# See: fpga/src/verilog/pll_controller.sv and pll_command_api.sv

import sys
import logging
import time
from pathlib import Path

# Allow running this file directly (`python tests/pll_test.py`): put sw/ on the
# path so `lib`/`tools` are importable. Harmless under `python -m tests.pll_test`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pll_driver import PllDriver  # noqa: E402
from lib.pll_command_api import default_cfg_word, OP_WRITEBACK, header  # noqa: E402

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


def test_verify_load(word=None):
    """LOAD_LOOPBACK a config word and check the echoed 47 bits match.

    Confirms the command path end-to-end: the controller assembled exactly these
    47 bits from the 6 little-endian payload bytes and committed them. Independent
    of any PLL behaviour (no analog readback is involved).
    """
    if word is None:
        word = default_cfg_word()   # the default operating config (chip reference test_cfg)
    received = pll.verify_load(word)
    if received is None:
        logging.error('FAIL: verify_load sent 0x%012X, received None (incomplete echo)', word)
        return False
    if received == word:
        logging.info('PASS: verify_load echoed 0x%012X (config path OK)', received)
        return True
    logging.error('FAIL [mismatch]: verify_load sent 0x%012X, received 0x%012X', word, received)
    return False


def test_readback(word=None):
    """LOAD a config, then READBACK its 47 bits from the PLL's data_o and compare.

    This is the strongest digital check: it reads what the PLL silicon actually
    captured in its shallow register (via the data_o scan-out), not just what the
    FPGA assembled. Requires the bitstream with pll_data_i wired (FMC LA06_N).
    """
    if word is None:
        word = default_cfg_word()   # the default operating config (chip reference test_cfg)
    pll.load(word)
    received = pll.readback()
    if received is None:
        logging.error('FAIL: readback sent 0x%012X, received None (incomplete scan)', word)
        return False
    if received == word:
        logging.info('PASS: readback scanned 0x%012X out of data_o (silicon OK)', received)
        return True
    logging.error('FAIL [mismatch]: readback sent 0x%012X, received 0x%012X', word, received)
    return False


def test_status():
    """Read and report the PLL lock status (pll_lock_i via the STATUS command).

    Informational, not pass/fail: lock depends on whether the PLL is configured and
    has settled. With no chip connected the pin is pulled low (reads not-locked).
    """
    lock = pll.read_lock()
    if lock is None:
        logging.error('FAIL: STATUS returned None (no byte came back)')
        return False
    logging.info('STATUS: PLL %s (lock bit = %d)', 'LOCKED' if lock else 'not locked', lock)
    return True


def example_bring_up():
    """Reference example: configure the PLL, wait for lock, switch the SoC onto it.

    Boot is on the reference clock (bitstream default clk_sel=1). This enables the
    PLL, polls STATUS until lock (pll_lock_i is wired back now), and only then
    switches clk_sel=0. Hold the core in reset across the switch (the clock mux is
    not glitchless).
    """
    with PllDriver(WRITE_DEV, READ_DEV) as p:
        # bring_up() loads the default operating config (DEFAULT_CFG); pass field
        # overrides here if you need to tweak it (e.g. vco_tune_coarse=0xA).
        locked = p.bring_up(lock_timeout=1.0, switch=True)
        if locked:
            logging.info('PLL locked and selected as the SoC clock')
        else:
            logging.error('PLL did not lock within the timeout; SoC left on reference')


def main():
    open_ports()
    # Reset the PLL registers to a known state first.
    pll.reset()
    # 1. liveness: the controller echoes the writeback header.
    test_writeback()
    # 2. config-path check: a real LOAD whose 47 bits are echoed back (FPGA echo).
    test_verify_load()
    # 3. silicon check: LOAD then scan the 47 bits back out of the PLL's data_o.
    test_readback()
    # 4. lock status: read the PLL lock bit (pll_lock_i).
    test_status()
    # NOTE: this script intentionally does NOT switch the SoC clock onto the PLL.
    # Use pll.bring_up() (configures, waits for STATUS lock, then switches) or a
    # manual pll.select_pll() when you want to move the SoC onto the PLL.
    time.sleep(1)


if __name__ == '__main__':
    sys.exit(main())

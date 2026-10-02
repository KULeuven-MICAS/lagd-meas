# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Connect to the PLL controller and load a configuration with a silicon readback check.
# Shared by sw/tests/pll_test.py and the VCO measurement code (sw/lib/vco_measure.py, sw/lib/vco_lut.py).

import logging

from sw.lib.pll_driver import PllDriver
from sw.lib.pll_command_api import OP_WRITEBACK, STRB_HZ, calculate_div_factor, header, pack_pll_cfg

logger = logging.getLogger(__name__)

# Device files for the PLL write/read ports (8-bit Xillybus stream).
WRITE_DEV = "/dev/xillybus_write_8"
READ_DEV = "/dev/xillybus_read_8"


def connect(write_dev=WRITE_DEV, read_dev=READ_DEV):
    """Open the PLL ports and check the controller answers a WRITEBACK; returns the PllDriver."""
    pll = PllDriver(write_dev, read_dev)
    pll.open()
    expected = header(OP_WRITEBACK)  # 0xFF
    received = pll.writeback()
    if received != expected:
        raise RuntimeError("PLL controller did not answer the writeback (sent 0x%02X, received %s)"
                           % (expected, "None" if received is None else "0x%02X" % received))
    logger.info("PASS: writeback echoed 0x%02X. The PLL controller is alive.", received)
    return pll


def load_config(pll, cfg):
    """Put the PLL registers in a known state and load `cfg` (field dict), on the reference clock.

    Sets the default strobe rate, resets the registers, selects the reference as the SoC clock, loads
    the config with the FPGA echo check and reads it back out of the silicon. Returns the config word.
    """
    pll.set_strb_hz(STRB_HZ)
    pll.reset()
    pll.select_reference()
    word = pack_pll_cfg(**cfg)
    if pll.verify_load(word) == word:
        logger.info("config check OK: 0x%012X", word)
        logger.info("Division factor on chip clock: %d, total: %d", *calculate_div_factor(cfg))
    else:
        logger.error("config check FAILED: 0x%012X", word)
    # READBACK the chip's shallow register out of the PLL's data_o (recirculating, so non-destructive).
    readback = pll.readback()
    logger.info("readback = 0x%012X", readback)
    assert readback == word
    return word

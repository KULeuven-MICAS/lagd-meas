# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Interactive session + writeback self-test for the chip ports.
#
# The reusable chip command layer lives in lib/chip_driver.py (ChipDriver);
# this file just wires it up and runs a writeback stress test.
#
# Interactive helpers (after `python -i chip_test.py`):
#   open_ports()                    # open the ports -> module-global `chip`
#   chip.init_spi()                 # enable Quad-SPI on the chip's SPI slave
#   chip.config_clk_rst(en, rstn)   # drive chip_clk_en / chip_rstn
#   chip.write_mem(addr, data)      # single or burst write (data: int or list)
#   chip.read_mem(addr, length)     # single or burst read -> list of ints
#   chip.verify_write_mem(addr, d)  # write + echo data back for verification
#   chip.writeback(payload)         # loopback self-test primitive
#
# Running this file directly executes the writeback stress test (see main()).
#
# See: fpga/src/verilog/chip_controller.sv and chip_command_api.sv

import sys
import random
import logging
# import time
import sw.tests.pll_test as pll_test

from sw.lib.chip_driver import ChipDriver
from sw.lib.chip_command_api import WRITEBACK_FIFO, make_command

logger = logging.getLogger(__name__)

# Device files for the chip write/read ports (cwp/crp).
WRITE_DEV = '/dev/xillybus_write_32'
READ_DEV = '/dev/xillybus_read_32'

# Populated by open_ports(); declared here so the interactive helpers below
# (and `python -i chip_test.py` sessions) can refer to it as a global.
chip: ChipDriver


def open_ports():
    """Open the chip ports, exposing them via the module-global `chip` driver."""
    global chip
    chip = ChipDriver(WRITE_DEV, READ_DEV)
    chip.open()


def test_writeback(payload=0xADBEE):
    """Send one WRITEBACK_FIFO command and check it loops back unchanged.

    The marker + opcode occupy the top 12 bits, so the payload that survives in
    the echoed word is the low 20 bits ([19:0]).
    """
    command = make_command(WRITEBACK_FIFO, payload)
    received = chip.writeback(payload)
    if received is None:
        logging.error('[FPGA FIFO Test] FAIL: Data sent: 0x%08X, Data received: None', command)
        return False

    if received == command:
        logging.info('[FPGA FIFO Test] PASS: Data sent: 0x%08X, Data received: 0x%08X', command, received)
        return True
    else:
        logging.error('[FPGA FIFO Test] FAIL [Data unmatch]: Data sent: 0x%08X, Data received: 0x%08X',
                      command, received)
        return False


def test_verify_write_mem(addr=0x200, data=None):
    """Loopback-write a burst and check every echoed word matches what was sent.

    Uses DATA_WRITE_LOOPBACK: the controller performs the real SPI write AND
    mirrors each data word into the read FIFO, so the returned list should equal
    the words sent. This confirms exactly what was streamed onto the Quad-SPI bus.
    """
    if data is None:
        data = [0xC0DE0000 + i for i in range(4)]
    received = chip.verify_write_mem(addr, data)
    if received == data:
        logging.info('[Chip mem test] PASS: verify_write_mem echoed %d words at 0x%08X', len(data), addr)
        logging.debug('      Sent: %s', [hex(d) for d in data])
        logging.debug('      Received: %s', [hex(r) for r in received])
        return True
    else:
        logging.error('[Chip mem test] FAIL: verify_write_mem at 0x%08X: sent %s, received %s',
                      addr, [hex(d) for d in data], [hex(r) for r in received])
        return False


def example_with_driver():
    """Reference example: drive the chip via ChipDriver as a context manager."""
    with ChipDriver(WRITE_DEV, READ_DEV) as chip:
        chip.init_spi()
        # Burst-write two words to address 0x0, then read them back.
        chip.write_mem(0x0, [0xDEAD, 0xBEEF])
        readback = chip.read_mem(0x0, length=2)
    # The ports are closed automatically on exiting the `with` block above.
    return readback


def setup_chip(setup_pll=True, mem_test=False):
    # Set up PLL
    if setup_pll:
        pll_test.setup_pll()

    # Set up the chip driver
    open_ports()

    # tune the chip clock and spi clock
    # SCK must stay at or below the chip clock: the slave's RX FIFO is 8 words
    # deep and cannot backpressure SPI, so an AXI side slower than the SPI silently drops words.
    # chip.set_chip_clk_hz(10e6) # 10 MHz (FPGA clock is not used for now. Use the on-PCB oscillator instead)
    chip.set_sck_hz(5e6) # 5 MHz

    # enable the chip clock and reset the chip
    chip.reset_chip(hold=0.5, chip_clk_en=1)

    # init quad-spi
    chip.init_spi()

    # run a memory test
    if mem_test:
        # smoke test: test writeback loop
        test_writeback()

        # loopback-write check: data is echoed back for verification
        SCRATCH_0 = 0x80000000
        length = 50
        data = [random.randint(0, 0xFFFFFFFF) for _ in range(length)]
        logger.debug(f"Writing data: {[hex(d) for d in data]}")
        test_verify_write_mem(SCRATCH_0, data)

        # read back check
        readback = chip.read_mem(SCRATCH_0, length=length)
        logger.info(f"Readback matches written data: {readback == data}")

if __name__ == '__main__':
    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)
    sys.exit(setup_chip())

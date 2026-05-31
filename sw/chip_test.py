# Copyright 2025 KU Leuven.
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
#   chip.writeback(payload)         # loopback self-test primitive
#
# Running this file directly executes the writeback stress test (see main()).
#
# See: fpga/src/verilog/chip_controller.sv and chip_command_api.sv

import sys
import random
import logging

from lib.chip_driver import ChipDriver
from lib.chip_command_api import WRITEBACK_FIFO, make_command

# Configure logging: include timestamp and level
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

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
        logging.error('FAIL: Data sent: 0x%08X, Data received: None', command)
        return False

    if received == command:
        logging.info('PASS: Data sent: 0x%08X, Data received: 0x%08X', command, received)
        return True
    else:
        logging.error('FAIL [Data unmatch]: Data sent: 0x%08X, Data received: 0x%08X', command, received)
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


def main():
    open_ports()
    # Run the writeback test automatically on startup. The echoable payload is
    # the low 20 bits ([19:0]) of the command word.
    payload_list = [random.randint(0, 0xFFFFF) for _ in range(100)]
    pass_cnt = 0
    fail_cnt = 0
    for payload in payload_list:
        passed = test_writeback(payload)
        if passed:
            pass_cnt += 1
        else:
            fail_cnt += 1
    logging.info('Test results - Passed: %d, Failed: %d', pass_cnt, fail_cnt)
    return 0 if fail_cnt == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

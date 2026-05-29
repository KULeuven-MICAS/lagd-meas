# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Interactive session for the Chip Write Port (cwp) and Chip Read Port (crp)
#
# This script also runs a self-contained WRITEBACK test: it sends a single
# 32-bit command word tagged with the WRITEBACK_FIFO opcode into the chip
# write FIFO. The chip_controller FSM loops that exact word straight back
# into the chip read FIFO, so reading the crp should return the same value.
#
# See: fpga/src/verilog/chip_controller.sv (WRITEBACK_FIFO / WRITEBACK_PUSH)

import sys
import time

from lib.WritePort import WritePort
from lib.ReadPort import ReadPort
from lib.chipc_ISA import WRITEBACK_FIFO, make_command

# Device files for the Chip Write Port (cwp) and Chip Read Port (crp).
write_filename = '/dev/xillybus_write_32'
read_filename = '/dev/xillybus_read_32'

# Populated by open_ports(); declared here so the interactive helpers below
# (and `python -i chip_test.py` sessions) can refer to them as globals.
cwp = None
crp = None


def open_ports():
    """Open the chip write and read ports, storing them as module globals."""
    global cwp, crp
    cwp = WritePort(write_filename, 32)
    cwp.openPort()
    crp = ReadPort(read_filename, 32)
    crp.openPort()


def read_word(timeout=2.0):
    """Poll the (non-blocking) read port until one 32-bit word arrives.

    Returns the word as an int, or None if nothing came back within timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        word = crp.readInt()
        if word is not None:
            return word
        time.sleep(0.01)
    return None


def test_writeback(payload=0xDEADBEE):
    """Send one WRITEBACK_FIFO command and check it loops back unchanged."""
    # Drain anything stale that might be sitting in the read FIFO.
    crp.flushBuffer()

    command = make_command(WRITEBACK_FIFO, payload)
    print('Sending writeback command : 0x%08X' % command)
    cwp.sendInt(command)

    received = read_word()
    if received is None:
        print('FAIL: no data returned from the chip read FIFO (timeout).')
        return False

    print('Received from read FIFO   : 0x%08X' % received)
    if received == command:
        print('PASS: writeback returned the expected word.')
        return True

    print('FAIL: returned word does not match the command sent.')
    return False


def main():
    open_ports()

    print('This script configured the following python variables:')
    print(' - cwp (chip write port) and crp (chip read port)')
    print('Available helpers:')
    print('  test_writeback()        # send one word, verify it loops back')
    print('  cwp.sendInt(make_command(WRITEBACK_FIFO, 0xDEADBEE))')
    print('  crp.readHex()')
    print()

    # Run the writeback test automatically on startup.
    passed = test_writeback()
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())

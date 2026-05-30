# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Interactive session + writeback self-test for the periphery (DAC) ports.
#
# The reusable periphery command layer lives in lib/perip_driver.py (PeripDriver);
# this file just wires it up and runs a writeback stress test.
#
# Interactive helpers (after `python -i perip_test.py`):
#   open_ports()                    # open the ports -> module-global `perip`
#   perip.dac_write(addr, data)     # write one DAC register (12-bit load)
#   perip.dac_reset()               # hold the DAC in reset (no SPI transfer)
#   perip.writeback(payload)        # loopback self-test primitive
#
# Running this file directly executes the writeback stress test (see main()).
#
# See: fpga/src/verilog/perip_controller.sv and perip_command_api.sv

import sys
import random

from lib.perip_driver import PeripDriver
from lib.perip_command_api import OP_WRITEBACK, make_command

# Device files for the periphery (DAC) write/read ports.
WRITE_DEV = '/dev/xillybus_write_32_2'
READ_DEV = '/dev/xillybus_read_32_2'

# Populated by open_ports(); declared here so the interactive helpers below
# (and `python -i perip_test.py` sessions) can refer to it as a global.
perip: PeripDriver


def open_ports():
    """Open the periphery ports, exposing them via the module-global `perip`."""
    global perip
    perip = PeripDriver(WRITE_DEV, READ_DEV)
    perip.open()


def test_writeback(payload=0xADBEE):
    """Send one writeback command and check it loops back unchanged.

    The marker + opcode occupy the top 12 bits, so the payload that survives in
    the echoed word is the low 20 bits ([19:0]).
    """
    command = make_command(OP_WRITEBACK, payload)
    received = perip.writeback(payload)
    if received is None:
        print('FAIL: Data sent: 0x%08X, Data received: None' % command)
        return False

    if received == command:
        print('PASS: Data sent: 0x%08X, Data received: 0x%08X' % (command, received))
        return True
    else:
        print('FAIL [Data unmatch]: Data sent: 0x%08X, Data received: 0x%08X' % (command, received))
        return False


def example_with_driver():
    """Reference example: drive the DAC via PeripDriver as a context manager."""
    with PeripDriver(WRITE_DEV, READ_DEV) as perip:
        perip.dac_reset()                  # bring the DAC out of/into reset as needed
        perip.dac_write(addr=0x1, data=0x80)
    # The ports are closed automatically on exiting the `with` block above.


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
    print(f'Test results - Passed: {pass_cnt}, Failed: {fail_cnt}')
    return 0 if fail_cnt == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

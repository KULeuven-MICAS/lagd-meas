# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

#
# The reusable periphery command layer lives in lib/perip_driver.py (PeripDriver);
# this file is the top script for DAC configuration.
#
# Interactive helpers (after `python -i perip_test.py`):
#   open_ports()                          # open the ports -> module-global `perip`
#   perip.set_voltage(ch, volts, VREF)    # set a channel by voltage (V_REF as arg)
#   perip.set_code(ch, code)              # set a channel by raw 8-bit code
#   perip.get_code(ch) / get_voltage(...) # last value written (host-side cache)
#   perip.midscale() / reset()            # all channels to 0x80 / hardware RS_N
#   perip.dac_write(addr, data)           # low-level register write (12-bit load)
#   perip.writeback(payload)              # loopback self-test primitive
#
# Running this file directly executes the writeback stress test (see main()).
#
# See: fpga/src/verilog/perip_controller.sv and perip_command_api.sv

import sys
import logging

from lib.perip_driver import PeripDriver
from lib.perip_command_api import OP_WRITEBACK, make_command

# Configure logging: include timestamp and level
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Device files for the periphery (DAC) write/read ports.
WRITE_DEV = '/dev/xillybus_write_32_2'
READ_DEV = '/dev/xillybus_read_32_2'

# DAC reference voltage (board-specific) used by the set_voltage example below.
VREF = 1.8

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
        logging.error('FAIL: Data sent: 0x%08X, Data received: None', command)
        return False

    if received == command:
        logging.info('PASS: Data sent: 0x%08X, Data received: 0x%08X', command, received)
        logging.info('The DAC controller is alive. Proceeding with the next ...')
        return True
    else:
        logging.error('FAIL [Data unmatch]: Data sent: 0x%08X, Data received: 0x%08X', command, received)
        return False


def example_with_driver():
    """Reference example: drive the AD8802 via PeripDriver as a context manager."""
    with PeripDriver(WRITE_DEV, READ_DEV) as perip:
        perip.midscale()                       # all 12 channels -> 0x80 (V_REF/2)

        # Set channel 1 to 0.6 V; set channel 2 by raw code.
        code = perip.set_voltage(channel=1, volts=0.6, vref=VREF)
        perip.set_code(channel=2, code=0x40)
        logging.info(f'ch1 -> code 0x{code:02X} ({perip.get_voltage(1, VREF):.3f} V), '
                 f'ch2 -> 0x{perip.get_code(2):02X} ({perip.get_voltage(2, VREF):.3f} V)')
    # The ports are closed automatically on exiting the `with` block above.


def main():
    open_ports()
    # reset first
    perip.reset()
    # test writeback of DAC controller to ensure it is alive
    test_writeback()
    # set all channels to a volt
    volt = 0.6
    perip.set_all_voltage(volt, VREF)
    # pdb.set_trace()  # drop into interactive mode for manual testing

if __name__ == '__main__':
    sys.exit(main())

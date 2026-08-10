# Copyright 2026 KU Leuven.
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
#   perip.verify_dac_write(addr, data)    # DAC write + echo command for verification
#   perip.writeback(payload)              # loopback self-test primitive
#   perip.set_dac_sck_hz(hz)              # retune the DAC SPI clock -> actual Hz
#   perip.set_s2p_sck_hz(hz)              # retune the HV9308 shift clock -> actual Hz
#
# Tuning the serial clocks -- the short version:
#   actual = perip.set_dac_sck_hz(1_000_000)
#
# Related to: fpga/src/verilog/perip_controller.sv and perip_command_api.sv

import sys
import logging
import time

from sw.lib.perip_driver import PeripDriver, DAC_XFER_BITS
from sw.lib.perip_command_api import (
    OP_WRITEBACK, SCK_HZ, make_command, cmd_dac_write_loopback,
)

logger = logging.getLogger(__name__)

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
        logger.error('FAIL: Data sent: 0x%08X, Data received: None', command)
        return False

    if received == command:
        logger.info('PASS: Data sent: 0x%08X, Data received: 0x%08X', command, received)
        logger.info('The DAC controller is alive. Proceeding with the next ...')
        return True
    else:
        logger.error('FAIL [Data unmatch]: Data sent: 0x%08X, Data received: 0x%08X', command, received)
        return False


def test_sck_config(rates=(1_000, 10_000, 100_000, 1_000_000), reps=20):
    """Verify CONFIG_DAC_SCK actually changes the DAC serial clock.

    Uses the DAC loopback: the controller echoes the command word only after the
    12-bit SPI transfer has finished, so the round-trip time is dominated by the
    serial clock. Timing it is what proves the divider moved -- a correct echo on
    its own would come back from a stuck divider too.

    Needs no DAC on the board: the transfer runs on the dac_* pins whether or not
    anything is listening, and the echo comes from the FPGA. That makes this a
    pure test of the new command, independent of what is wired to the FMC.
    """
    cmd = cmd_dac_write_loopback(3, 0x5A)[0]
    ok, elapsed = True, {}
    for hz in rates:
        actual = perip.set_dac_sck_hz(hz)
        t0 = time.time()
        echoes_ok = all(perip.verify_dac_write(3, 0x5A) == cmd for _ in range(reps))
        elapsed[hz] = time.time() - t0
        wire = reps * DAC_XFER_BITS / actual
        ok &= echoes_ok
        logger.info('%s: %8.0f Hz requested -> %10.2f Hz actual | %d echoes %s | '
                    'wire %6.3f s, measured %6.3f s',
                    'PASS' if echoes_ok else 'FAIL', hz, actual, reps,
                    'ok' if echoes_ok else 'MISMATCH/TIMEOUT', wire, elapsed[hz])

    # The rate really changed: the slowest sweep point must take far longer than
    # the fastest. A stuck divider (either direction) collapses this ratio.
    slow, fast = elapsed[min(rates)], elapsed[max(rates)]
    ratio_ok = slow > fast * 5
    ok &= ratio_ok
    logger.info('%s: %.0f Hz took %.3f s vs %.0f s at %.0f Hz (%.1fx, need >5x)',
                'PASS' if ratio_ok else 'FAIL', min(rates), slow, fast, max(rates),
                slow / fast if fast else float('inf'))

    perip.set_dac_sck_hz(SCK_HZ)   # back to the power-on rate
    return ok


def test_s2p_sck_config(rates=(1_000, 10_000, 100_000)):
    """Sweep the HV9308 shift clock and confirm it still captures a value.

    Unlike test_sck_config this DOES need the HV9308 wired (FMC LA11-13): the
    check is a recirculating readback of the device's own shift register. A rate
    the wiring cannot sustain shows up as a mismatch, which is the point -- this
    finds the ceiling of that path rather than assuming one.
    """
    ok = True
    perip.s2p_output_enable(True)
    for hz in rates:
        actual = perip.set_s2p_sck_hz(hz)
        step_ok = perip.s2p_verify(0xA5A5_5A5A)
        ok &= step_ok
        logger.info('%s: %8.0f Hz requested -> %10.2f Hz actual, readback %s',
                    'PASS' if step_ok else 'FAIL', hz, actual,
                    'ok' if step_ok else 'MISMATCH')
    perip.set_s2p_sck_hz(SCK_HZ)   # back to the power-on rate
    return ok


def main():
    """Worked example of the periphery command set. Run it top to bottom.

    Steps 1-2 need nothing but the Zedboard and the bitstream. Steps 3-4 talk to
    real devices on the FMC and are commented out -- uncomment what your board
    actually has. Nothing here changes a chip-critical setting, so it is safe to
    run as-is.
    """
    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)
    open_ports()

    # 1. Is the Zedboard controller alive?
    if not test_writeback():
        return 1

    # 2. Tune the serial clocks (the two devices are independent)
    perip.set_dac_sck_hz(SCK_HZ)
    perip.set_s2p_sck_hz(SCK_HZ)

    # 3. Drive the DAC (AD8802)     [needs the DAC on the FMC]
    # perip.reset()                                    # hardware RS_N -> all 0x80
    # perip.midscale()                                 # or set them in software
    # code = perip.set_voltage(channel=1, volts=0.6, vref=VREF)
    # perip.set_code(channel=2, code=0x40)             # or by raw 8-bit code
    # logger.info('ch1 -> 0x%02X (%.3f V), ch2 -> 0x%02X (%.3f V)',
    #             code, perip.get_voltage(1, VREF),
    #             perip.get_code(2), perip.get_voltage(2, VREF))
    # The AD8802 has no readback, so get_* returns a host-side cache of what was
    # written. To verify the command really reached the controller, use the echo:
    #     assert perip.verify_dac_write(3, 0x5A) == cmd_dac_write_loopback(3, 0x5A)[0]

    # 4. Drive the HV9308 S2P       [needs the HV9308 wired, FMC LA11-13]
    # perip.s2p_output_enable(True)                    # outputs power up blanked
    # perip.s2p_write(0xA5A5_5A5A)                     # shift 32 bits + latch
    # assert perip.s2p_readback() == 0xA5A5_5A5A       # what the silicon holds
    # perip.s2p_reconfigure(0x1234_5678)               # blank -> write -> re-enable

    # Optional deeper checks -- none of these are required to use the script
    # test_sck_config()        # sweep + time the DAC clock   (no hardware needed)
    # test_s2p_sck_config()    # sweep the S2P clock          (needs the HV9308)
    # Soak the command path:
    # for i in range(10_000):
    #     assert perip.verify_dac_write(3, 0x5A) == cmd_dac_write_loopback(3, 0x5A)[0]

    return 0


if __name__ == '__main__':
    sys.exit(main())

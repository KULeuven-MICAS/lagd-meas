#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Host UART loopback test -- NO chip involved.
#
# With a TX<->RX jumper on the UART port, whatever the host sends comes straight back.
# This verifies the host serial path (USB-to-UART converter, /dev/ttyUSB*, cabling) and
# the port configuration (115200 8N1) BEFORE the chip is blamed for anything.
#
# It reuses send_uart.py's open_port/write_all/read_exact, so it validates the exact
# serial setup the real loader (send_uart.py) uses.
#
#   ./loopback.py --device /dev/ttyUSB10
#
# NOTE: flow control is OFF by default; a plain TX<->RX jumper does not loop RTS/CTS.
# Only pass --rtscts if you have also jumpered RTS<->CTS.

import argparse
import importlib.util
import os
import sys
import termios

HERE = os.path.dirname(os.path.abspath(__file__))
SEND_UART = os.path.normpath(os.path.join(HERE, "..", "..", "..", "sw", "uart", "send_uart.py"))


def load_send_uart():
    if not os.path.isfile(SEND_UART):
        sys.exit("ERROR: cannot find send_uart.py at %s" % SEND_UART)
    spec = importlib.util.spec_from_file_location("send_uart", SEND_UART)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser(
        description="Host UART loopback test (TX<->RX jumper, no chip).")
    ap.add_argument("-d", "--device", default="/dev/ttyUSB10",
                    help="serial device -- the FT4232H UART channel, same as send_uart.py "
                         "(default: /dev/ttyUSB10)")
    ap.add_argument("-b", "--baud", type=int, default=115200,
                    help="baud rate (default: 115200, matching the chip)")
    ap.add_argument("--rtscts", action="store_true",
                    help="enable HW flow control (only if RTS<->CTS is also jumpered)")
    ap.add_argument("-n", "--bytes", type=int, default=256,
                    help="number of test bytes (default: 256)")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="seconds to wait for the echo (default: 2)")
    args = ap.parse_args()

    su = load_send_uart()

    # Deterministic test pattern (0..255 repeating).
    pattern = bytes((i & 0xFF) for i in range(args.bytes))

    print("Loopback: %s @ %d 8N1, RTS/CTS=%s, %d bytes"
          % (args.device, args.baud, "on" if args.rtscts else "off", args.bytes))
    print("Requires a TX<->RX jumper on the port. No chip involved.")

    try:
        fd = su.open_port(args.device, args.baud, args.rtscts)
    except Exception as e:  # noqa: BLE001 -- report any open failure cleanly
        print("FAIL: could not open %s: %s" % (args.device, e))
        print("  -> wrong device, no permission, or the converter is not present.")
        return 1

    try:
        termios.tcflush(fd, termios.TCIOFLUSH)
        su.write_all(fd, pattern)
        try:
            got = su.read_exact(fd, len(pattern), args.timeout)
        except su.ProtoError as e:
            print("FAIL: did not receive the echo: %s" % e)
            print("  -> no loopback. Check the TX<->RX jumper, the device, and converter power.")
            return 1
    finally:
        os.close(fd)

    if got == pattern:
        print("PASS: %d/%d bytes echoed back correctly. Host serial path is good."
              % (len(got), len(pattern)))
        return 0

    idx = next(i for i in range(len(pattern)) if got[i] != pattern[i])
    print("FAIL: data mismatch at byte %d (sent 0x%02x, got 0x%02x)."
          % (idx, pattern[idx], got[idx]))
    print("  -> likely wrong baud, line noise, or a flow-control mismatch.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

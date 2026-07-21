#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

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
#   source ../../../env.sh             # repo root on PYTHONPATH; needed once per shell
#   ./loopback.py --device /dev/ttyUSB2
#
# NOTE: flow control is OFF by default; a plain TX<->RX jumper does not loop RTS/CTS.
# Only pass --rtscts if you have also jumpered RTS<->CTS.

import argparse
import logging
import os
import sys
import termios

from sw.uart.send_uart import ProtoError, open_port, read_exact, write_all

logger = logging.getLogger(__name__)


def main():
    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)
    ap = argparse.ArgumentParser(
        description="Host UART loopback test (TX<->RX jumper, no chip).")
    ap.add_argument("-d", "--device", default="/dev/ttyUSB2",
                    help="serial device -- the FT4232H UART channel, same as send_uart.py "
                         "(default: /dev/ttyUSB2)")
    ap.add_argument("-b", "--baud", type=int, default=115200,
                    help="baud rate (default: 115200, matching the chip)")
    ap.add_argument("--rtscts", action="store_true",
                    help="enable HW flow control (only if RTS<->CTS is also jumpered)")
    ap.add_argument("-n", "--bytes", type=int, default=256,
                    help="number of test bytes (default: 256)")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="seconds to wait for the echo (default: 2)")
    args = ap.parse_args()

    # Deterministic test pattern (0..255 repeating).
    pattern = bytes((i & 0xFF) for i in range(args.bytes))

    logger.info("Loopback: %s @ %d 8N1, RTS/CTS=%s, %d bytes",
                args.device, args.baud, "on" if args.rtscts else "off", args.bytes)
    logger.info("Requires a TX<->RX jumper on the port. No chip involved.")

    try:
        fd = open_port(args.device, args.baud, args.rtscts)
    except Exception as e:  # noqa: BLE001 -- report any open failure cleanly
        logger.error("FAIL: could not open %s: %s", args.device, e)
        logger.error("  -> wrong device, no permission, or the converter is not present.")
        return 1

    try:
        termios.tcflush(fd, termios.TCIOFLUSH)
        write_all(fd, pattern)
        try:
            got = read_exact(fd, len(pattern), args.timeout)
        except ProtoError as e:
            logger.error("FAIL: did not receive the echo: %s", e)
            logger.error("  -> no loopback. Check the TX<->RX jumper, the device, and converter power.")
            return 1
    finally:
        os.close(fd)

    if got == pattern:
        logger.info("PASS: %d/%d bytes echoed back correctly. Host serial path is good.",
                    len(got), len(pattern))
        return 0

    idx = next(i for i in range(len(pattern)) if got[i] != pattern[i])
    logger.error("FAIL: data mismatch at byte %d (sent 0x%02x, got 0x%02x).",
                 idx, pattern[idx], got[idx])
    logger.error("  -> likely wrong baud, line noise, or a flow-control mismatch.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Probe the LAGD Cheshire bootrom over UART: does it answer the debug handshake?
#
# WHAT THIS TELLS YOU
# -------------------
# The bootrom prints NOTHING - there is no banner anywhere in hw/bootrom. In
# passive boot (boot_mode = 00) it calls uart_debug_init() (115200 8N1) and then
# silently polls for a single byte 0x06 (ACK); on receiving it, it replies 0x06
# and enters uart_debug_serve(). So a blank terminal is expected in BOTH the
# healthy and the hung case, and this handshake is the only way to tell them
# apart:
#
#   reply 0x06  -> clint_get_core_freq() returned, i.e. the RTC IS ticking and
#                  the bootrom is sitting in passive boot, ready to be loaded.
#   no reply    -> either the SoC is stuck in clint_get_core_freq() waiting for
#                  an rtc_i edge (the usual cause: no driver board / no on-FPGA
#                  RTC), or this is the wrong serial port or wrong baud.
#
# Note the LEDs cannot distinguish these: with no RTC the board still shows
# led_clk_locked_o solid and led_heartbeat_o blinking, because soc_clk is fine
# and the SoC is out of reset. The hang is purely in software.
#
# ##### IMPORTANT: THIS PROBE IS ONE-SHOT #####
#
# A SUCCESSFUL ping leaves the bootrom inside uart_debug_serve(), waiting for a
# command opcode (0x11 READ / 0x12 WRITE / 0x13 EXEC). Any other byte hits the
# `default: return 1` arm, which exits the server and falls through to _exit -
# and 0x06 itself is NOT a valid opcode. So a second ping, or a subsequent
# loader run that starts with its own handshake, will KILL the session.
#
# After a successful ping, press CPU_RESET (AM13) to restart the bootrom before
# you load anything. Equally: do not point an interactive terminal (screen,
# minicom) at this port while loading - stray keystrokes typed BEFORE the
# handshake are harmless (uart_debug_check reads and discards them), but after
# it they terminate the debug server.
#
# USAGE
# -----
#   ./portsweep.py --scan                 # try every serial port, report which answers
#   ./portsweep.py /dev/ttyUSB2           # probe one port
#   ./portsweep.py /dev/ttyUSB2 -t 5      # longer timeout
#
# Note when imeplementing the LAGD on ZCU102:
# The ZCU102's USB-UART (J83) is a CP2108 QUAD bridge: one physical cable
# enumerates as four ports. The LAGD console is the PL-UART channel (uart2_pl,
# fabric pins F13/E13); a different channel is the PS UART0 (the PYNQ Linux
# console). --scan finds the right one for you.

import argparse
import logging
import sys

logger = logging.getLogger(__name__)

# Imported lazily so that --help still works on a machine without pyserial (this
# script runs on the laptop wired to J83, not on the Vivado build server).
serial = None
list_ports = None


def _need_serial():
    global serial, list_ports
    if serial is None:
        try:
            import serial as _serial
            from serial.tools import list_ports as _list_ports
        except ImportError:
            sys.exit("error: pyserial is not installed. Install it with: pip install pyserial")
        serial, list_ports = _serial, _list_ports


ACK = 0x06
PROBE = 0x55  # arbitrary NON-opcode byte, used to unmask a looped-back port
DEFAULT_BAUD = 115200  # __BOOT_BAUDRATE in cheshire sw/include/params.h


def ping(port, baud, timeout):
    """Two-phase probe: unmask echo first, then try the real handshake.

    A port whose TX is looped back to RX returns whatever you send it, so a
    naive "write 0x06, read 0x06" check reports it as a live bootrom. Since the
    SoC has exactly one UART, more than one such "hit" in a scan is proof the
    check is being fooled.

    Phase 1 sends a byte the bootrom is REQUIRED to ignore: uart_debug_check()
    reads the RBR and only acts if the byte is 0x06, discarding anything else
    (see cheshire sw/lib/hal/uart_debug.c). So a real bootrom stays silent here,
    while a loopback hands the byte straight back. This is safe - the discarded
    byte does not disturb the bootrom's polling loop.

    Returns (status, detail) with status one of:
      'bootrom'    - replied 0x06 to the handshake, and did NOT echo
      'echo'       - port looped the probe byte back; NOT a bootrom
      'silent'     - no reply to either byte
      'unexpected' - replied something else
      None         - port could not be opened
    """
    try:
        with serial.Serial(port, baud, timeout=timeout) as s:
            # Drop anything stale so we do not mistake old bytes for a reply.
            s.reset_input_buffer()
            s.reset_output_buffer()

            # Phase 1: echo detection.
            s.write(bytes([PROBE]))
            s.flush()
            if s.read(1) == bytes([PROBE]):
                return "echo", f"echoed 0x{PROBE:02x} back (TX looped to RX)"

            # Phase 2: the real handshake.
            s.reset_input_buffer()
            s.write(bytes([ACK]))
            s.flush()
            resp = s.read(1)
    except (serial.SerialException, OSError) as e:
        return None, str(e)

    if resp == bytes([ACK]):
        return "bootrom", "replied ACK"
    if not resp:
        return "silent", "no response"
    return "unexpected", f"unexpected byte 0x{resp[0]:02x}"


def scan(baud, timeout):
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if not ports:
        sys.exit("error: no serial ports found. Is the ZCU102 USB-UART (J83) plugged in?")

    logger.info("Scanning %d serial port(s) at %d baud, %ss timeout",
                len(ports), baud, timeout)
    hits, echoes = [], []
    for p in ports:
        status, detail = ping(p.device, baud, timeout)
        if status is None:
            label = f"skipped  ({detail})"
        elif status == "bootrom":
            label = "BOOTROM  (ACK, no echo)"
            hits.append(p.device)
        elif status == "echo":
            label = f"echo     ({detail}) - NOT a bootrom"
            echoes.append(p.device)
        else:
            label = f"silent   ({detail})"
        logger.info("  %-20s %s", p.device, label)
        if p.description and p.description != "n/a":
            logger.info("  %-20s %s", "", p.description)

    if echoes:
        logger.info("Loopback port(s) ignored: %s", ", ".join(echoes))
        logger.info("These return whatever is sent to them, so a plain 0x06 test would")
        logger.info("wrongly report them as a live bootrom.")

    if not hits:
        logger.error("No port answered the handshake. Either the SoC is stuck waiting on")
        logger.error("rtc_i, or none of these ports is the PL UART. See the notes at the")
        logger.error("top of this script.")
        return 1

    if len(hits) > 1:
        logger.warning("%d ports answered: %s", len(hits), ", ".join(hits))
        logger.warning("The SoC has exactly ONE UART, so this cannot be right - suspect a")
        logger.warning("loopback that also passes the echo test, or crossed wiring. Do not")
        logger.warning("trust this result; investigate before loading.")
        return 1

    logger.info("Bootrom answered on: %s", hits[0])
    logger.info("That is your PL-UART channel. NOTE: the session is now in")
    logger.info("uart_debug_serve() - press CPU_RESET (AM13) before loading a program.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Probe the LAGD Cheshire bootrom UART debug handshake (0x06).",
        epilog="A successful ping is one-shot: press CPU_RESET before loading. "
               "See the header of this file for details.",
    )
    ap.add_argument("port", nargs="?", help="serial port, e.g. /dev/ttyUSB1 (omit with --scan)")
    ap.add_argument("--scan", action="store_true", help="probe every available serial port")
    ap.add_argument("-b", "--baud", type=int, default=DEFAULT_BAUD,
                    help=f"baud rate (default {DEFAULT_BAUD}, = __BOOT_BAUDRATE)")
    ap.add_argument("-t", "--timeout", type=float, default=2.0,
                    help="seconds to wait for the reply (default 2.0)")
    args = ap.parse_args()

    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)

    _need_serial()

    if args.scan:
        return scan(args.baud, args.timeout)

    if not args.port:
        ap.error("give a port, or use --scan to probe all of them")

    status, detail = ping(args.port, args.baud, args.timeout)

    if status is None:
        logger.error("FAIL  %s: could not open port (%s)", args.port, detail)
        return 2

    if status == "bootrom":
        logger.info("PASS  %s: bootrom replied ACK (0x06), and did not echo", args.port)
        logger.info("The RTC is ticking, clint_get_core_freq() returned, and the bootrom")
        logger.info("is in passive boot ready to load.")
        logger.info("The session is now inside uart_debug_serve(): press CPU_RESET (AM13)")
        logger.info("to restart the bootrom before running a loader.")
        return 0

    if status == "echo":
        logger.error("FAIL  %s: %s", args.port, detail)
        logger.error("This port hands back whatever is sent to it, so it is a loopback,")
        logger.error("not the SoC. A naive 0x06-only test would have called this a PASS.")
        logger.error("Try the other CP2108 channels with --scan.")
        return 1

    logger.error("FAIL  %s: %s", args.port, detail)
    logger.error("Most likely one of:")
    logger.error("  * rtc_i is not toggling -> the SoC is stuck in clint_get_core_freq()")
    logger.error("    before the UART is ever initialised. Connect the driver board, or")
    logger.error("    build with the on-FPGA RTC (Standalone=1).")
    logger.error("  * wrong CP2108 channel  -> try --scan; the PL UART is not the same")
    logger.error("    port as the PS/PYNQ Linux console.")
    logger.error("  * wrong baud            -> the bootrom uses %d 8N1.", DEFAULT_BAUD)
    logger.error("  * the bootrom already exited (passive boot is one-shot). Press")
    logger.error("    CPU_RESET (AM13) and try again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

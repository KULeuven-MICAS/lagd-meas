# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

import argparse
import os
import select
import sys
import subprocess
import time

from sw.uart.send_uart import open_port
from openising import TOP_MEAS, default_device, default_uart_baud, default_uart_timeout


UART_POLL_INTERVAL = 0.1
UART_DRAIN_TIMEOUT = 0.25


def _print_uart_data(data, line):
    """Print raw UART data as console lines while preserving partial lines."""
    for byte in bytearray(data):
        if byte == 0x0A:  # \n
            sys.stdout.write("[chip] " + line.decode("latin1") + "\n")
            sys.stdout.flush()
            line.clear()
        elif byte != 0x0D:  # ignore \r
            line.append(byte)


def _stream_uart_while_loader_runs(fd, process, drain_timeout=UART_DRAIN_TIMEOUT):
    """Stream UART text until the external loader exits and UART becomes quiet."""
    line = bytearray()
    drain_deadline = None

    while True:
        if process.poll() is None:
            wait = UART_POLL_INTERVAL
        else:
            now = time.monotonic()
            if drain_deadline is None:
                drain_deadline = now + drain_timeout
            remaining = drain_deadline - now
            if remaining <= 0:
                break
            wait = min(UART_POLL_INTERVAL, remaining)

        readable, _, _ = select.select([fd], [], [], wait)
        if not readable:
            continue

        data = os.read(fd, 4096)
        if not data:
            continue
        _print_uart_data(data, line)

        # Once the loader has exited, keep draining until the UART has been
        # quiet for a short interval. This catches bytes still in flight.
        if drain_deadline is not None:
            drain_deadline = time.monotonic() + drain_timeout

    if line:
        sys.stdout.write("[chip] " + line.decode("latin1") + "\n")
        sys.stdout.flush()

    return process.wait()

def build_parser():
    parser = argparse.ArgumentParser(
            description="Open the UART port and wait for data to print out")
    parser.add_argument("-interface", help="Other interface with which to send all the data.", type=str)
    parser.add_argument("-elf", help="Elf file to send to chip", type=str)
    parser.add_argument(
            "--device", default=default_device,
            help=f"UART device on the measurement host (default: {default_device})",
        )
    parser.add_argument("-b", "--baud", type=int, default=default_uart_baud,
                        help=f"baud rate (default: {default_uart_baud} -- must match the chip)")
    parser.add_argument(
            "--rtscts", action="store_true",
            help="keep hardware flow control (by default --no-rtscts is passed to send_uart)",
        )
    parser.add_argument("--timeout", type=float, default=default_uart_timeout,
                        help="program timeout in seconds; passed to the SPI loader as "
                             f"--run-timeout (default: {default_uart_timeout})")
    return parser

def main(argv=None):
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    timeout = args.timeout
    fd = open_port(args.device, args.baud, args.rtscts)
    interface = args.interface
    elf_file = args.elf
    try:
        if interface == "spi":
            command = [
                sys.executable,
                str(TOP_MEAS / "sw/tests/chip_load_spi.py"),
                elf_file,
                "--run-timeout",
                str(timeout),
                "--sck",
                "12500000",  # 12.5 MHz
            ]
        elif interface == "jtag":
            command = [
                str(TOP_MEAS / "sw/jtag/run_elf.sh"),
                elf_file,
                "-c",
                "set ADAPTER_KHZ 20000", # 20 MHz
            ]
        else:
            raise ValueError(f"interface {interface} is not supported.")

        process = subprocess.Popen(command, stderr=subprocess.STDOUT)
        return_code = _stream_uart_while_loader_runs(fd, process)
        if return_code:
            raise subprocess.CalledProcessError(return_code, command)
        return return_code
    finally:
        os.close(fd)

if __name__ == "__main__":
    sys.exit(main())

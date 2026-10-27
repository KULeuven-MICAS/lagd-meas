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
import tempfile
import threading
import time
from pathlib import Path

from sw.uart.send_uart import open_port
from openising import TOP_MEAS, default_device, default_uart_baud, default_uart_timeout


UART_POLL_INTERVAL = 0.1
UART_DRAIN_TIMEOUT = 0.25
BATCH_START_MARKER = "[batch] RUN_START"
BATCH_END_MARKER = "[batch] RUN_END"
BATCH_ERROR_MARKER = "[batch] RUN_ERROR"


class _ThreadProcess:
    """Small poll/wait adapter for running a loader in this process."""

    def __init__(self, target, args=(), kwargs=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._returncode = None
        self._error = None
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        try:
            result = self._target(*self._args, **self._kwargs)
            self._returncode = 0 if result is None else result
        except Exception as error:
            self._error = error
            self._returncode = 1

    def poll(self):
        if self._thread.is_alive():
            return None
        return self._returncode

    def wait(self):
        self._thread.join()
        if self._error is not None:
            raise self._error
        return self._returncode


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


def _print_batch_marker(marker, run_index, elf_file, return_code=None, elapsed=None):
    fields = [marker, str(run_index), elf_file]
    if return_code is not None:
        fields.append(str(return_code))
    if elapsed is not None:
        fields.append(f"{elapsed:.6f}")
    sys.stdout.write(" ".join(fields) + "\n")
    sys.stdout.flush()


def _run_spi_batch(fd, elf_files, timeout):
    """Run multiple SPI ELFs with one Python, UART, and Xillybus session."""
    # Keep SPI-only imports lazy so the legacy JTAG wrapper stays lightweight.
    from sw.tests.chip_load_spi import (  # noqa: PLC0415
        ChipDriver,
        READ_DEV,
        WRITE_DEV,
        run_elf_with_chip,
    )

    with ChipDriver(WRITE_DEV, READ_DEV) as chip:
        for run_index, elf_file in enumerate(elf_files):
            _print_batch_marker(BATCH_START_MARKER, run_index, elf_file)
            started = time.monotonic()
            # The FPGA-side SCK setting survives a chip reset, so configure it
            # only on the first run. run_elf_with_chip still resets the chip and
            # re-enables its Quad-SPI slave before every ELF.
            sck_hz = 12_500_000 if run_index == 0 else None
            process = _ThreadProcess(
                run_elf_with_chip,
                args=(chip, elf_file),
                kwargs={"sck_hz": sck_hz, "run_timeout": timeout},
            )
            try:
                return_code = _stream_uart_while_loader_runs(fd, process)
            except Exception:
                _print_batch_marker(
                    BATCH_ERROR_MARKER,
                    run_index,
                    elf_file,
                    1,
                    time.monotonic() - started,
                )
                raise
            if return_code:
                _print_batch_marker(
                    BATCH_ERROR_MARKER,
                    run_index,
                    elf_file,
                    return_code,
                    time.monotonic() - started,
                )
                return return_code
            _print_batch_marker(
                BATCH_END_MARKER,
                run_index,
                elf_file,
                return_code,
                time.monotonic() - started,
            )
    return 0


def _run_uart_batch(fd, elf_files, timeout):
    """Run multiple UART ELFs with one Python, UART, and Xillybus session."""
    from sw.lib.chip_driver import ChipDriver  # noqa: PLC0415
    from sw.uart.send_uart import ProtoError, run_elf_with_fd  # noqa: PLC0415

    write_device = "/dev/xillybus_write_32"
    read_device = "/dev/xillybus_read_32"
    with ChipDriver(write_device, read_device) as chip:
        for run_index, elf_file in enumerate(elf_files):
            _print_batch_marker(BATCH_START_MARKER, run_index, elf_file)
            started = time.monotonic()
            try:
                # Every ELF needs a fresh passive-boot UART server.  The outer
                # chip_test setup (when requested) configures the PLL once; this
                # transport-local reset only returns the chip to its boot ROM.
                chip.reset_chip(hold=0.01, chip_clk_en=1)
                application_code = run_elf_with_fd(
                    fd,
                    elf_file,
                    timeout=timeout,
                )
            except (OSError, ProtoError, RuntimeError):
                _print_batch_marker(
                    BATCH_ERROR_MARKER,
                    run_index,
                    elf_file,
                    1,
                    time.monotonic() - started,
                )
                raise

            if application_code:
                _print_batch_marker(
                    BATCH_ERROR_MARKER,
                    run_index,
                    elf_file,
                    2,
                    time.monotonic() - started,
                )
                return 2
            _print_batch_marker(
                BATCH_END_MARKER,
                run_index,
                elf_file,
                0,
                time.monotonic() - started,
            )
    return 0


def _run_jtag_batch(fd, elf_files):
    """Run multiple JTAG ELFs with one OpenOCD and UART-console session."""
    manifest_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix="lagd-jtag-elfs-",
            delete=False,
        ) as manifest:
            manifest_path = manifest.name
            for elf_file in elf_files:
                manifest.write(str(Path(elf_file).resolve()) + "\n")

        command = [
            "openocd",
            "-c",
            "set ELF_LIST_FILE " + manifest_path,
            "-c",
            "set ADAPTER_KHZ 20000",
            "-f",
            str(TOP_MEAS / "sw/jtag/openocd.run_batch.tcl"),
        ]
        process = subprocess.Popen(command, stderr=subprocess.STDOUT)
        return _stream_uart_while_loader_runs(fd, process)
    finally:
        if manifest_path is not None:
            try:
                Path(manifest_path).unlink()
            except OSError:
                pass


def build_parser():
    parser = argparse.ArgumentParser(
            description="Open the UART port and wait for data to print out")
    parser.add_argument("-interface", help="Other interface with which to send all the data.", type=str)
    parser.add_argument(
            "-elf", help="Elf file to send to chip; repeat for batch mode",
            type=str, action="append", required=True)
    parser.add_argument(
            "--batch", action="store_true",
            help="run all repeated -elf arguments in one persistent transport session")
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
                        help="timeout in seconds; used as the SPI run timeout and "
                             "UART command timeout "
                             f"(default: {default_uart_timeout})")
    return parser

def main(argv=None):
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    timeout = args.timeout
    fd = open_port(args.device, args.baud, args.rtscts)
    interface = args.interface
    elf_files = args.elf
    try:
        if args.batch:
            if interface == "spi":
                return _run_spi_batch(fd, elf_files, timeout)
            if interface == "uart":
                return _run_uart_batch(fd, elf_files, timeout)
            if interface == "jtag":
                return _run_jtag_batch(fd, elf_files)
            parser.error("--batch supports only spi, uart, and jtag")

        elf_file = elf_files[0]
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

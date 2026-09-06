#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Run chip_test.py to reset the chip, then forward arguments to send_uart.py.

Usage:
    source env.sh
    python sw/uart/reset_plus_uart.py sw/inputs/my_program.elf --verify

Reset uses the settings in chip_test.py's __main__ block. All command-line
arguments belong to send_uart.py; --help and an empty command line skip reset.
Relative ELF paths are resolved from the caller's working directory.
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    if not os.environ.get("TOP_MEAS"):
        sys.exit("TOP_MEAS is not set; source env.sh first.")
    top_meas = Path(os.environ["TOP_MEAS"])
    uart_command = [sys.executable, str(top_meas / "sw/uart/send_uart.py"), *sys.argv[1:]]

    # Show the loader's help or missing-argument error without touching hardware.
    if not sys.argv[1:] or "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        return subprocess.run(uart_command, check=False).returncode

    print("Resetting chip via sw/tests/chip_test.py ...", flush=True)
    reset = subprocess.run(
        [sys.executable, str(top_meas / "sw/tests/chip_test.py")],
        check=False,
    )
    if reset.returncode != 0:
        print("Chip reset failed; UART loading skipped.", file=sys.stderr)
        return reset.returncode

    print("Starting UART loader ...", flush=True)
    return subprocess.run(uart_command, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

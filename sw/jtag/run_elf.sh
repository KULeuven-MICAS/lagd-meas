#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Load and run an ELF on the LAGD / Cheshire chip over JTAG (FT4232H), and report the
# program's return code. Thin wrapper around openocd.run.tcl -- the JTAG counterpart of
# uart/send_uart.py.
#
# Usage:
#   ./run_elf.sh <file.elf> [extra openocd -c options]
#
# Examples:
#   ./run_elf.sh ../inputs/helloworld.spm.elf
#   ./run_elf.sh app.spm.elf -c "set RUN_TIMEOUT 60"
#   ./run_elf.sh app.spm.elf -c "set ADAPTER_KHZ 4000"   # faster JTAG clock

set -e

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <file.elf> [extra openocd -c options]"
    exit 1
fi

ELF="$(readlink -f "$1")"; shift
if [ ! -f "$ELF" ]; then
    echo "[ERROR] ELF not found: $ELF"
    exit 1
fi

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

# -c "set ELF ..." must come BEFORE -f so the variable exists when the script runs.
# Any user-supplied "$@" (further -c overrides) also goes before -f.
exec openocd -c "set ELF ${ELF}" "$@" -f "${SCRIPT_DIR}/openocd.run.tcl"

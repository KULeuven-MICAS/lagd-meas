#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Example / regression check: use the sw/jtag JTAG run flow to load and run
# helloworld on the chip. PASS = the program finishes with return code 0.
#
# This testcase is intentionally a thin wrapper: the actual flow lives in
# lagd-meas/sw/jtag/ (run_elf.sh -> openocd.run.tcl), which is the reusable tool.
#
#   ./run.sh              # runs the default helloworld.spm.elf
#   ./run.sh -c "set RUN_TIMEOUT 60"   # extra options pass through to OpenOCD

set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
JTAG_DIR="${SCRIPT_DIR}/../../../sw/jtag"
ELF="${SCRIPT_DIR}/../../../sw/inputs/helloworld.spm.elf"

exec "${JTAG_DIR}/run_elf.sh" "$ELF" "$@"

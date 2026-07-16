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

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../../.." && pwd)"
ELF="${REPO_ROOT}/sw/inputs/helloworld.spm.elf"

exec "${REPO_ROOT}/sw/jtag/run_elf.sh" "$ELF" "$@"

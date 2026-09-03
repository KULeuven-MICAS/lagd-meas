#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# JTAG memory integrity + volume test: write several patterns over a memory region via
# the debug system bus and read them back to verify. Thin wrapper around
# sw/jtag/openocd.memtest.tcl.
#
#   ./run.sh                                     # default 8 Kb at 0x80000000
#   ./run.sh -c "set MEM_WORDS 16384"            # 64 Kb (more volume stress)
#   ./run.sh -c "set ADAPTER_KHZ 4000"           # faster JTAG clock (after 01_idcode)
#   ./run.sh -c "set DEBUG_LEVEL 3"              # trace every access (see below)
#
# NOTE: at the 100 kHz bring-up clock this is slow; raise ADAPTER_KHZ once 01_idcode
# has established a reliable speed.
#
# Memory is reached over the debug system bus (SBA), NOT through the CPU -- the script
# sets MEM_ACCESS to `sysbus` with no progbuf fallback, and prints an "SBA probe" line
# reading sbcs from the debug module. To confirm empirically which OpenOCD path ran:
#
#   ./run.sh -c "set DEBUG_LEVEL 3" 2>&1 | grep -oE '(read|write)_memory_[a-z0-9_]+' | sort | uniq -c
#
# Expect only *_bus_v1 (system bus). Any *_progbuf / *_abstract means the CPU did the
# access, and the result is not a valid memory test -- see the script header for why.

set -e

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../../.." && pwd)"

# User -c overrides must precede -f so the variables exist when the script runs.
exec openocd "$@" -f "${REPO_ROOT}/sw/jtag/openocd.memtest.tcl"

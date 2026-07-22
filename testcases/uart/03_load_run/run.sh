#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Example / regression check: use the UART loader to load & run helloworld on the chip.
# PASS = the program finishes with return code 0.
#
# Thin wrapper: the actual loader lives in lagd-meas/sw/uart/send_uart.py.
#
#   ./run.sh                       # load & run helloworld.spm.elf
#   ./run.sh --verify              # also read each segment back and compare
#   ./run.sh --no-exec --verify    # memory check only: load + verify, do not run
#   ./run.sh --device /dev/ttyUSB2 # options pass through to send_uart.py

set -e

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../../.." && pwd)"
source "${REPO_ROOT}/env.sh" >/dev/null

ELF="${REPO_ROOT}/sw/inputs/helloworld.spm.elf"

exec python3 -m sw.uart.send_uart "$ELF" "$@"

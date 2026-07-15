#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# UART memory integrity + volume test: write several patterns over a memory region and
# read them back to verify. Thin wrapper around 'send_uart.py --memtest'.
#
#   ./run.sh                                # default 8 Kb at 0x80000000
#   ./run.sh --mem-size 0x10000             # 64 Kb (more flow-control / volume stress)
#   ./run.sh --mem-base 0x80000000 --mem-size 0x2000
#   ./run.sh --device /dev/ttyUSB2 --no-rtscts

set -e

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../../.." && pwd)"
source "${REPO_ROOT}/env.sh" >/dev/null

exec python3 -m sw.uart.send_uart --memtest "$@"

#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Reach the chip's bootrom UART debug server via the ACK handshake -- no ELF loaded.
# A thin wrapper around 'send_uart.py --ping' (the reusable tool in sw/uart/).
#
#   ./run.sh                          # default device /dev/ttyUSB10
#   ./run.sh --device /dev/ttyUSB2    # extra options pass through to send_uart.py
#   ./run.sh --no-rtscts

set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SEND_UART="${SCRIPT_DIR}/../../../sw/uart/send_uart.py"

exec python3 "$SEND_UART" --ping "$@"

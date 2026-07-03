#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Soak runner: run a testcase command N times and tally pass/fail. Intermittent link
# problems (flaky level shifter, marginal flow control, occasional desync) only show up
# over many iterations -- a single run can't catch them.
#
# Works with any testcase runner (UART or JTAG). Extra args pass through to the command.
#
# Usage:
#   ./soak.sh <count> <command> [args...]
#
# Examples (run from this directory):
#   ./soak.sh 100 uart/03_load_run/run.sh
#   ./soak.sh 50  jtag/03_load_run/run.sh
#   ./soak.sh 20  uart/04_memtest/run.sh --mem-size 0x8000
#   ./soak.sh 30  jtag/04_memtest/run.sh -c "set ADAPTER_KHZ 12000"

set -u

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <count> <command> [args...]"
    exit 2
fi

N="$1"; shift

LOGDIR="$(mktemp -d)"
pass=0
fail=0
failed_iters=""

echo "Soak: ${N} iterations of: $*"
echo "Logs: ${LOGDIR}"

i=1
while [ "${i}" -le "${N}" ]; do
    log="${LOGDIR}/iter_${i}.log"
    if "$@" >"${log}" 2>&1; then
        pass=$((pass + 1)); printf "."
    else
        fail=$((fail + 1)); failed_iters="${failed_iters} ${i}"; printf "F"
    fi
    if [ $((i % 50)) -eq 0 ]; then printf "  %d/%d\n" "${i}" "${N}"; fi
    i=$((i + 1))
done
echo

echo "Result: ${pass}/${N} passed, ${fail} failed."
if [ "${fail}" -gt 0 ]; then
    echo "Failed iterations:${failed_iters}"
    echo "See per-iteration logs in ${LOGDIR}"
    exit 1
fi
echo "All ${N} iterations passed."
exit 0

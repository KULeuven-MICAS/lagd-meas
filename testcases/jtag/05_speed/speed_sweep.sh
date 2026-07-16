#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# JTAG speed sweep: find the highest reliable JTAG clock (TCK) for this board.
#
# For each speed it runs a per-speed check and records PASS/FAIL, then reports the
# highest passing speed. Two check modes:
#   MODE=memtest (default) : init + halt + small memtest  -> highest usable DEBUG speed
#                            (needs the core clock; run after 02_halt passes)
#   MODE=idcode            : read IDCODE only              -> highest ELECTRICAL speed
#                            (pure TCK; works even before the clock/debug are up)
#
# Usage:
#   ./speed_sweep.sh
#   MODE=idcode ./speed_sweep.sh
#   SPEEDS="100 1000 4000 10000" MEM_WORDS=512 ./speed_sweep.sh

set -u

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
JTAG_DIR="${REPO_ROOT}/sw/jtag"
SCAN_TCL="${SCRIPT_DIR}/../01_idcode/openocd.scan.tcl"   # sibling testcase, stays local
IDCODE="0x1c5e5db3"

SPEEDS="${SPEEDS:-100 500 1000 2000 4000 8000 12000 16000 20000 30000}"   # kHz
MODE="${MODE:-memtest}"
MEM_WORDS="${MEM_WORDS:-256}"

LOGDIR="$(mktemp -d)"
best=""

echo "JTAG speed sweep  (mode=${MODE})"
echo "Logs: ${LOGDIR}"
printf "%-10s %s\n" "SPEED/kHz" "RESULT"

for s in ${SPEEDS}; do
    log="${LOGDIR}/speed_${s}.log"
    if [ "${MODE}" = "idcode" ]; then
        openocd -c "set ADAPTER_KHZ ${s}" -f "${SCAN_TCL}" >"${log}" 2>&1
        if grep -qi "${IDCODE}" "${log}"; then ok=1; else ok=0; fi
    else
        if openocd -c "set ADAPTER_KHZ ${s}; set MEM_WORDS ${MEM_WORDS}" \
                   -f "${JTAG_DIR}/openocd.memtest.tcl" >"${log}" 2>&1; then
            ok=1; else ok=0; fi
    fi

    if [ "${ok}" -eq 1 ]; then
        printf "%-10s PASS\n" "${s}"; best="${s}"
    else
        printf "%-10s FAIL   (%s)\n" "${s}" "${log}"
    fi
done

echo
if [ -n "${best}" ]; then
    echo "Highest reliable JTAG speed: ${best} kHz"
    echo "Use it via:  openocd -c \"set ADAPTER_KHZ ${best}\" -f <script>"
    echo "(For margin, operate a step below the first FAIL.)"
    exit 0
else
    echo "No speed passed. Check 01_idcode (electrical) and, for MODE=memtest, 02_halt (clock)."
    exit 1
fi

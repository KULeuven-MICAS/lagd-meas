#!/bin/bash
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Self-test runner on UART: execute all UART tests in a single run, and report pass/fail. This is useful for checking the UART link on a new chip.

# The UART device is fixed by the FT4232H board wiring.  Keep it in one place so
# every rung below uses the same port.
DEVICE=/dev/ttyUSB2
REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"

source "${REPO_ROOT}/env.sh" >/dev/null


reset_chip() {
    # Do this in a short-lived Python process: setup_chip() configures the PLL,
    # resets/enables the chip clock, and initializes the SPI control path that
    # drives the reset.  A fresh reset also restores the one-shot bootrom UART
    # server before each UART check.
    python3 -c 'from sw.tests.chip_test import setup_chip; setup_chip()'
}


run_test() {
    local name="$1"
    shift

    printf '\n%s ... running\n' "${name}"
    if ! reset_chip; then
        printf '%s ...... FAIL (chip reset/setup failed)\n' "${name}"
        exit 1
    fi

    if "$@"; then
        printf '%s ...... PASS\n' "${name}"
    else
        printf '%s ...... FAIL\n' "${name}"
        exit 1
    fi
}


run_dcompute_test() {
    local name='UART IsingCore ELF test'
    local log_file
    local loader_status

    printf '\n%s ... running\n' "${name}"
    if ! reset_chip; then
        printf '%s ...... FAIL (chip reset/setup failed)\n' "${name}"
        exit 1
    fi

    log_file="$(mktemp)" || {
        printf '%s ...... FAIL (could not create temporary log)\n' "${name}"
        exit 1
    }

    # lagd_dcompute intentionally prints "FAIL" from its C payload.  Preserve
    # the loader's output in the terminal, then use that chip-originated line
    # as this test's success criterion instead of interpreting the word FAIL as
    # a transport failure.
    set +o pipefail
    python3 -m sw.uart.send_uart "${REPO_ROOT}/sw/inputs/lagd_dcompute.spm.elf" \
        --device "${DEVICE}" --verify 2>&1 | tee "${log_file}"
    loader_status=${PIPESTATUS[0]}
    set -o pipefail

    if grep -Eq '^\[chip\].*FAIL' "${log_file}"; then
        rm -f "${log_file}"
        printf '%s ...... PASS (expected chip output: FAIL)\n' "${name}"
        return
    fi

    rm -f "${log_file}"
    if [ "${loader_status}" -ne 0 ]; then
        printf '%s ...... FAIL\n' "${name}"
    else
        printf '%s ...... FAIL (expected chip output was not received)\n' "${name}"
    fi
    exit 1
}


run_test 'UART Handshake test' \
    "${REPO_ROOT}/testcases/uart/02_handshake/run.sh" --device "${DEVICE}"

run_test 'UART HelloWorld memory-check test' \
    "${REPO_ROOT}/testcases/uart/03_load_run/run.sh" \
    --device "${DEVICE}" --no-exec --verify

run_test 'UART HelloWorld load/run test' \
    "${REPO_ROOT}/testcases/uart/03_load_run/run.sh" --device "${DEVICE}" --verify

run_test 'UART Memory test (0x10000000, 0x3fc8)' \
    "${REPO_ROOT}/testcases/uart/04_memtest/run.sh" \
    --device "${DEVICE}" --mem-base 0x10000000 --mem-size 0x3fc8

run_test 'UART Memory test (0x80000000, 0x10000)' \
    "${REPO_ROOT}/testcases/uart/04_memtest/run.sh" \
    --device "${DEVICE}" --mem-base 0x80000000 --mem-size 0x10000

run_test 'UART Memory test (0x90000000, 0x10000)' \
    "${REPO_ROOT}/testcases/uart/04_memtest/run.sh" \
    --device "${DEVICE}" --mem-base 0x90000000 --mem-size 0x10000

run_test 'UART Memory test (0x90010000, 0x10000)' \
    "${REPO_ROOT}/testcases/uart/04_memtest/run.sh" \
    --device "${DEVICE}" --mem-base 0x90010000 --mem-size 0x10000

run_test 'UART IsingCore register test' \
    python3 -m sw.uart.send_uart "${REPO_ROOT}/sw/inputs/lagd_reg.spm.elf" \
    --device "${DEVICE}" --verify

run_dcompute_test

printf '\nUART self-diagnosis ...... PASS\n'

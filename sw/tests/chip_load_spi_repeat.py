# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Repeatedly load and run one ELF in a single persistent Python process.
#
# The Xillybus ports stay open and the SPI clock is configured once. Every run
# still resets the chip and re-enables the chip-side Quad-SPI slave before loading
# the ELF, launching it, and waiting for end-of-computation.

# Run from the repository root after sourcing env.sh:

#     python sw/tests/chip_load_spi_repeat.py
#     python sw/tests/chip_load_spi_repeat.py --runs 10 --sck 12500000
#     python sw/tests/chip_load_spi_repeat.py --eoc-initial-delay 0.5


import argparse
import logging
import statistics
import sys
import time
from pathlib import Path

from sw.lib.chip_driver import ChipDriver
from sw.tools.spi_program_loader import (
    DEFAULT_EOC_INITIAL_DELAY,
    DEFAULT_EOC_TIMEOUT,
    EocTimeoutError,
    SpiProgramLoader,
)

WRITE_DEV = "/dev/xillybus_write_32"
READ_DEV = "/dev/xillybus_read_32"

DEFAULT_ELF = str(
    Path(__file__).resolve().parent.parent / "inputs" / "lagd_dcompute.spm.elf"
)
DEFAULT_RUNS = 10
DEFAULT_SCK_HZ = 12_500_000
DEFAULT_RESET_HOLD = 0.001

logger = logging.getLogger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Load and run one ELF repeatedly over SPI in one Python process."
    )
    parser.add_argument(
        "elf",
        nargs="?",
        default=DEFAULT_ELF,
        help="ELF to load repeatedly (default: %(default)s)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help="number of reset/load/run cycles (default: %(default)s)",
    )
    parser.add_argument(
        "--sck",
        type=float,
        default=DEFAULT_SCK_HZ,
        metavar="HZ",
        help="target SPI clock frequency in Hz (default: %(default)s)",
    )
    parser.add_argument(
        "--reset-hold",
        type=float,
        default=DEFAULT_RESET_HOLD,
        metavar="SECONDS",
        help="chip reset assertion time before every run (default: %(default)s)",
    )
    parser.add_argument(
        "--run-timeout",
        type=float,
        default=DEFAULT_EOC_TIMEOUT,
        metavar="SECONDS",
        help="EOC wait limit for each run; 0 waits forever (default: %(default)s)",
    )
    parser.add_argument(
        "--eoc-initial-delay",
        type=float,
        default=DEFAULT_EOC_INITIAL_DELAY,
        metavar="SECONDS",
        help="keep SPI idle this long after launch before polling EOC "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="read back and verify every ELF segment before each launch",
    )
    args = parser.parse_args(argv)

    if not Path(args.elf).is_file():
        parser.error(f"ELF not found: {args.elf}")
    if args.runs <= 0:
        parser.error("--runs must be positive")
    if args.sck <= 0:
        parser.error("--sck must be positive")
    if args.reset_hold < 0:
        parser.error("--reset-hold must be non-negative")
    if args.run_timeout < 0:
        parser.error("--run-timeout must be non-negative")
    if args.eoc_initial_delay < 0:
        parser.error("--eoc-initial-delay must be non-negative")
    return args


def run_repeated(
    elf,
    runs=DEFAULT_RUNS,
    sck_hz=DEFAULT_SCK_HZ,
    reset_hold=DEFAULT_RESET_HOLD,
    verify=False,
    run_timeout=DEFAULT_EOC_TIMEOUT,
    eoc_initial_delay=DEFAULT_EOC_INITIAL_DELAY,
):
    """Run ``elf`` repeatedly while keeping Python and Xillybus ports open."""
    elapsed_runs = []

    with ChipDriver(WRITE_DEV, READ_DEV) as chip:
        actual_sck_hz = chip.set_sck_hz(sck_hz)
        loader = SpiProgramLoader(chip)
        logger.info(
            "[spi-repeat] persistent session ready: %d runs at %.6g MHz",
            runs,
            actual_sck_hz / 1e6,
        )

        for run_index in range(1, runs + 1):
            logger.info("[spi-repeat] run %d/%d starting", run_index, runs)
            started = time.monotonic()

            # The FPGA-side SCK setting persists, but the chip and its SPI slave
            # must start from a clean state before every program launch.
            chip.reset_chip(hold=reset_hold, chip_clk_en=1)
            loader.load_and_run(
                elf,
                init_spi=True,
                verify=verify,
                wait=True,
                eoc_timeout=run_timeout,
                eoc_initial_delay=eoc_initial_delay,
            )

            elapsed = time.monotonic() - started
            elapsed_runs.append(elapsed)
            logger.info(
                "[spi-repeat] run %d/%d complete in %.3f s",
                run_index,
                runs,
                elapsed,
            )

    logger.info(
        "[spi-repeat] summary: %d runs, min %.3f s, median %.3f s, "
        "mean %.3f s, max %.3f s",
        len(elapsed_runs),
        min(elapsed_runs),
        statistics.median(elapsed_runs),
        statistics.mean(elapsed_runs),
        max(elapsed_runs),
    )
    return elapsed_runs


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    args = parse_args(argv)
    try:
        run_repeated(
            args.elf,
            runs=args.runs,
            sck_hz=args.sck,
            reset_hold=args.reset_hold,
            verify=args.verify,
            run_timeout=args.run_timeout,
            eoc_initial_delay=args.eoc_initial_delay,
        )
    except EocTimeoutError as error:
        logger.error("[spi-repeat] aborted: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Example: load a program ELF onto the chip over SPI and launch it.
#
# Run from the sw/ directory so the lib.* / tools.* imports resolve, e.g.:
#   python3 tests/chip_load_spi.py
#
# This wires the reusable pieces together for the full flow:
#   lib/chip_driver.py          -> ChipDriver (SPI transport via the FPGA)
#   tools/elf_loader.py         -> parse the ELF into segments + entry
#   tools/spi_program_loader.py -> write segments + scratch-register launch
#
# On startup it runs a SMOKE TEST first (a harmless SPI round-trip, no launch);
# main() only runs if the smoke test passes. What main() does, end to end:
#   1. open the chip write/read ports
#   2. release the core (chip_clk_en=1, chip_rstn=1) so the Cheshire bootrom
#      runs and spins in boot_passive() waiting on SCRATCH_2
#   3. enable Quad-SPI on the chip's SPI slave (init_spi)
#   4. write every PT_LOAD segment of the ELF to its load address
#   5. (verify) read each segment back and compare
#   6. write the entry point to SCRATCH_0/1 and set SCRATCH_2 bit 1 -> the
#      bootrom jumps to the entry, i.e. the program starts
#   7. (wait) poll SCRATCH_2 for the program-exit flag + exit code
#
# Prerequisite (hardware, NOT done here): boot_mode pins strapped to 0
# (passive boot). See doc/spi_program_loading.md for the full background.
#
# Interactive use (after `python -i tests/chip_load_spi.py`):
#   open_ports()                       # -> module-global `chip`, `loader`
#   loader.load_and_run(ELF_PATH, ...) # rerun the flow with different options
#   chip.read_mem(0x80000000, 4)       # peek at loaded memory

import sys
import logging
from pathlib import Path

# Allow running this file directly (`python tests/chip_load_spi.py`): put sw/ on
# the path so `lib`/`tools` are importable. Harmless under `python -m ...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.chip_driver import ChipDriver  # noqa: E402
from tools.spi_program_loader import SpiProgramLoader, SCRATCH_0  # noqa: E402

# Configure logging: include timestamp and level (matches chip_test.py).
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Device files for the chip write/read ports (cwp/crp).
WRITE_DEV = '/dev/xillybus_write_32'
READ_DEV = '/dev/xillybus_read_32'

# Program to load. Prebuilt ELFs live under inputs/ (copied from the lagd-im SW
# build). helloworld prints "Hello World!" over the chip UART when it runs.
ELF_PATH = 'inputs/helloworld.spm.elf'

# Smoke-test pattern: an arbitrary, easily-recognizable 32-bit value. A clean
# round-trip of this word proves the path works and the byte order is correct.
SMOKE_VALUE = 0xCAFEF00D

# Populated by open_ports(); declared here so the interactive helpers below
# (and `python -i tests/chip_load_spi.py` sessions) can refer to them as globals.
chip: ChipDriver
loader: SpiProgramLoader


def open_ports():
    """Open the chip ports and build the loader, exposed as module globals."""
    global chip, loader
    chip = ChipDriver(WRITE_DEV, READ_DEV)
    chip.open()
    loader = SpiProgramLoader(chip)


def smoke_test():
    """SPI round-trip sanity check -- write a known word to a scratch register
    and read it back. Returns True on an exact match, False otherwise.

    This exercises the whole path (ChipDriver -> xillybus -> FPGA chip_controller
    -> Quad-SPI -> chip's AXI SPI slave -> SCRATCH register) and confirms byte
    order, WITHOUT launching any program. It only touches SCRATCH_0 (overwritten
    by main()'s entry-point write anyway) and never sets the SCRATCH_2 go bit, so
    it cannot start the core. Run it once on fresh hardware before trusting a
    full load.

    Self-contained: opens its own ports and releases the core, so it leaves the
    chip in a clean state (closing the ports resets the FPGA controller).
    """
    logging.info("smoke test: SPI round-trip to SCRATCH_0 (0x%08X)", SCRATCH_0)
    with ChipDriver(WRITE_DEV, READ_DEV) as chip:
        # Release the core and enable Quad-SPI so write_mem/read_mem reach the bus.
        chip.config_clk_rst(chip_clk_en=1, chip_rstn=1)
        chip.init_spi()
        chip.write_mem(SCRATCH_0, SMOKE_VALUE)
        got = chip.read_mem(SCRATCH_0, length=1)

    if not got:
        logging.error("smoke test FAILED: nothing read back (None/timeout) -- "
                      "check clk/reset, CS/SCK wiring, or device files")
        return False
    if got[0] != SMOKE_VALUE:
        logging.error("smoke test FAILED: wrote 0x%08X, read 0x%08X "
                      "(byte-swap => endianness; partial => quad-lane/timing)",
                      SMOKE_VALUE, got[0])
        return False
    logging.info("smoke test PASSED: 0x%08X round-tripped intact", SMOKE_VALUE)
    return True


def main():
    # Open the ports (caller owns the lifecycle; the loader never opens/closes).
    chip = ChipDriver(WRITE_DEV, READ_DEV)
    with chip:
        # Release the core so the bootrom runs and polls SCRATCH_2 for the
        # launch signal. (boot_mode pins must already be strapped to 0.)
        chip.config_clk_rst(chip_clk_en=1, chip_rstn=1)

        loader = SpiProgramLoader(chip)
        # init_spi: enable Quad-SPI ; verify: read-back check ; wait: poll EOC.
        loader.load_and_run(ELF_PATH, init_spi=True, verify=True, wait=True)

    return 0


if __name__ == '__main__':
    # Run the smoke test first; only proceed to the full load+launch if it passes.
    if not smoke_test():
        logging.error("aborting: smoke test did not pass, not loading the program")
        sys.exit(1)
    sys.exit(main())

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# SPI program loader for the LAGD (Cheshire) RISC-V SoC.
#
# Loads an ELF onto the chip over the SPI path (FPGA chip_controller / Quad-SPI
# master -> chip's axi_spi_slave -> AXI bus) and launches it via the Cheshire
# bootrom passive-boot handshake. The ELF parsing is transport-agnostic
# (elf_loader.py); only the write + launch steps here are SPI-specific, so a
# JTAG or UART loader would reuse elf_loader and replace this module.
#
# Prerequisites on the chip side (NOT done here):
#   - boot_mode pins strapped to 0 (passive boot)
#   - core clock enabled and reset released, so the bootrom is running and
#     spinning in boot_passive() polling SCRATCH_2 bit 1.  Drive these with
#     ChipDriver.config_clk_rst(chip_clk_en=1, chip_rstn=1) before loading.
#
# Sequence (see docs/spi_program_loading.md):
#   1. chip.init_spi()                       enable Quad-SPI on the slave
#   2. write each PT_LOAD segment to its load address (auto-incrementing burst)
#   3. write entry -> SCRATCH_0 (+ high half -> SCRATCH_1)
#   4. write 2 -> SCRATCH_2  (set bit 1: "go")  -> bootrom jumps to entry
#   5. (optional) poll SCRATCH_2 bit 0 for end-of-computation + exit code
#
# Targets Python 3.6 (locked Zedboard runtime): typing module, no 3.10 syntax.


import argparse
import logging
import sys
import time

from sw.tools.elf_loader import parse_elf, bytes_to_words

logger = logging.getLogger(__name__)

# Cheshire register block base and SCRATCH offsets.
# __base_regs = 0x0300_0000 (lagd-im sw/link/common.ldh); SCRATCH_n at +4*n
# (cheshire sw/include/regs/cheshire.h). Reachable from the SPI master via the
# cheshire AXI xbar (full connectivity).
BASE_REGS = 0x03000000
SCRATCH_0 = BASE_REGS + 0x0   # entry[31:0]
SCRATCH_1 = BASE_REGS + 0x4   # entry[63:32]
SCRATCH_2 = BASE_REGS + 0x8   # [1]=go signal (bootrom polls), [0]=done flag

# boot_passive() polls `scratch[2] & 2`, i.e. bit 1, as the launch signal.
SCRATCH2_GO_BIT = 1 << 1
# On program exit the bootrom writes (retval << 1) | 1 to SCRATCH_2.
SCRATCH2_DONE_BIT = 1 << 0

# The SPI slave / chip_controller burst length field is 16 bits (max 65535
# words per frame). Larger segments are split across frames.
MAX_BURST_WORDS = 0xFFFF


class SpiProgramLoader:
    """Load + launch an ELF over SPI using a ChipDriver.

    `chip` is an already-open lib.chip_driver.ChipDriver (or anything exposing
    write_mem(addr, words) / read_mem(addr, length)). This class does not open
    or close it; the caller owns the port lifecycle.
    """

    def __init__(self, chip, verbose=True):
        self.chip = chip
        self.verbose = verbose

    def _log(self, msg):
        if self.verbose:
            logger.info("[spi-load] %s", msg)

    def write_segment(self, addr, words):
        """Write a list of 32-bit words to consecutive addresses from `addr`.

        Splits into MAX_BURST_WORDS-sized chunks; each chunk is one chip_controller
        DATA_WRITE frame (CS held low, address auto-increments by 4 per word).
        """
        off = 0
        n = len(words)
        while off < n:
            chunk = words[off:off + MAX_BURST_WORDS]
            self.chip.write_mem((addr + off * 4) & 0xFFFFFFFF, chunk)
            off += len(chunk)

    def load_image(self, img):
        """Write every PT_LOAD segment of a parsed ELF image to the chip."""
        for seg in img.segments:
            words = bytes_to_words(seg.data)
            self._log(f"segment -> 0x{seg.addr & 0xFFFFFFFF:08X}  {len(seg.data)} bytes ({len(words)} words)")
            self.write_segment(seg.addr & 0xFFFFFFFF, words)

    def verify_image(self, img):
        """Read back every segment and compare. Returns True if all match.

        Useful as the bring-up smoke test; reads are slower so this is opt-in.
        """
        ok = True
        for seg in img.segments:
            expected = bytes_to_words(seg.data)
            got = self.chip.read_mem(seg.addr & 0xFFFFFFFF, length=len(expected))
            if got != expected:
                ok = False
                first = _first_mismatch(expected, got)
                self._log(f"VERIFY FAIL @0x{seg.addr & 0xFFFFFFFF:08X}: {first}")
            else:
                self._log(f"verify OK -> 0x{seg.addr & 0xFFFFFFFF:08X} ({len(expected)} words)")
        return ok

    def set_entry(self, entry):
        """Write the 64-bit entry point into SCRATCH_0/SCRATCH_1."""
        self.chip.write_mem(SCRATCH_0, entry & 0xFFFFFFFF)
        self.chip.write_mem(SCRATCH_1, (entry >> 32) & 0xFFFFFFFF)

    def launch(self):
        """Set SCRATCH_2 bit 1; the bootrom jumps to SCRATCH_1:SCRATCH_0."""
        self.chip.write_mem(SCRATCH_2, SCRATCH2_GO_BIT)

    def wait_for_eoc(self, timeout=5.0, poll_interval=0.05):
        """Poll SCRATCH_2 for the program-exit flag; return the exit code.

        Returns the exit code (>=0) once SCRATCH_2 bit 0 is set, or None on
        timeout. The bootrom's _exit writes (retval << 1) | 1, so the exit code
        is value >> 1.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            vals = self.chip.read_mem(SCRATCH_2, length=1)
            if vals and (vals[0] & SCRATCH2_DONE_BIT):
                return vals[0] >> 1
            time.sleep(poll_interval)
        return None

    def load_and_run(self, elf_path, init_spi=True, verify=False, wait=False):
        """Full flow: parse -> (init_spi) -> load -> (verify) -> set entry -> go.

        Returns the parsed ElfImage. If `wait`, also polls for end-of-computation
        and prints the exit code.
        """
        img = parse_elf(elf_path)
        self._log(f"{elf_path}: entry 0x{img.entry:08X}, {len(img.segments)} segment(s), {img.total_bytes} bytes")

        if init_spi:
            self._log("enabling Quad-SPI on the chip's SPI slave")
            self.chip.init_spi()

        self.load_image(img)

        if verify and not self.verify_image(img):
            raise RuntimeError("readback verification failed; not launching")

        self._log(f"setting entry 0x{img.entry:08X} and launching")
        self.set_entry(img.entry)
        self.launch()

        if wait:
            code = self.wait_for_eoc()
            if code is None:
                self._log("timed out waiting for end-of-computation")
            else:
                self._log(f"program finished, exit code = {code}")
        return img


def _first_mismatch(expected, got):
    """Human-readable description of the first differing word (for verify)."""
    if len(got) != len(expected):
        return f"length {len(got)} != expected {len(expected)}"
    for i, (e, g) in enumerate(zip(expected, got)):
        if e != g:
            return f"word {i}: got 0x{g:08X}, expected 0x{e:08X}"
    return "no mismatch"


def _main():
    """CLI: load (and optionally verify/run) an ELF onto the chip over SPI."""
    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)

    ap = argparse.ArgumentParser(description="Load an ELF onto the LAGD chip over SPI")
    ap.add_argument("elf", help="path to the .elf to load")
    ap.add_argument("--write-dev", default="/dev/xillybus_write_32")
    ap.add_argument("--read-dev", default="/dev/xillybus_read_32")
    ap.add_argument("--no-init-spi", action="store_true",
                    help="skip enabling Quad-SPI (already enabled this session)")
    ap.add_argument("--no-clk-rst", action="store_true",
                    help="skip driving chip_clk_en/rstn (already running)")
    ap.add_argument("--verify", action="store_true",
                    help="read back each segment and compare before launching")
    ap.add_argument("--wait", action="store_true",
                    help="poll for end-of-computation and print the exit code")
    args = ap.parse_args()

    # Imported lazily (not at module top) so importing this module -- e.g. from
    # the hardware-free stub tests -- doesn't pull in chip_driver's hardware/port
    # dependencies, unlike the pure-stdlib elf_loader.
    from lib.chip_driver import ChipDriver  # noqa: PLC0415

    with ChipDriver(args.write_dev, args.read_dev) as chip:
        if not args.no_clk_rst:
            # Release the core so the bootrom runs and polls SCRATCH_2.
            chip.config_clk_rst(chip_clk_en=1, chip_rstn=1)
        loader = SpiProgramLoader(chip)
        loader.load_and_run(
            args.elf,
            init_spi=not args.no_init_spi,
            verify=args.verify,
            wait=args.wait,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

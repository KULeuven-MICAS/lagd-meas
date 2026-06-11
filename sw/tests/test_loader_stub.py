# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Hardware-free unit tests for the SPI program loader (elf_loader +
# spi_program_loader). They run the full Python logic against a StubChip that
# records write_mem/read_mem into a flat memory dict -- no Zedboard, no FPGA,
# no chip. This catches regressions in ELF parsing, segment addressing, byte
# order, the SCRATCH entry/launch handshake, burst chunking, and verify gating.
#
# What it does NOT cover (needs hardware): the FPGA RTL, SPI wiring/timing, and
# the physical chip. For the RTL path use the fpga/ chip_controller sim; for the
# live software->FPGA path the writeback loopback in chip_test.py.
#
# Run from the sw/ directory (so lib.* / tools.* import), with stdlib unittest:
#   python3 -m unittest tests.test_loader_stub
#   python3 tests/test_loader_stub.py            # also works (adds sw/ to path)
#
# Targets Python 3.6 (locked Zedboard runtime).

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Allow running the file directly from anywhere: ensure sw/ is importable so
# `tools.*` resolves. (Harmless when run via `python3 -m unittest` from sw/.)
_SW_DIR = str(Path(__file__).resolve().parent.parent)
if _SW_DIR not in sys.path:
    sys.path.insert(0, _SW_DIR)

# Imported after the sys.path fix above so `tools.*` resolves when run directly.
from tools.elf_loader import parse_elf, bytes_to_words, ElfImage, Segment  # noqa: E402
from tools.spi_program_loader import (  # noqa: E402
    SpiProgramLoader,
    SCRATCH_0, SCRATCH_1, SCRATCH_2,
    SCRATCH2_GO_BIT, SCRATCH2_DONE_BIT,
    MAX_BURST_WORDS,
)

# Prebuilt ELF copied from the lagd-im SW build (helloworld). Resolved relative
# to this file so the test passes regardless of the current directory.
ELF_PATH = str(Path(_SW_DIR) / "inputs" / "helloworld.spm.elf")

# Known facts about helloworld.spm.elf (cross-checked against objdump / .dump):
HELLO_ENTRY = 0x80000000
HELLO_SEG_ADDR = 0x80000000
HELLO_FIRST_WORD = 0x30057073  # csrci mstatus,10  (proves byte order is right)


class StubChip:
    """Fake ChipDriver: records writes/reads into a flat {word_addr: value} dict.

    Mimics the subset of ChipDriver the loader uses. read_mem returns whatever
    was written (so verify passes), unless an override is registered for an
    address (used to fake the bootrom's SCRATCH_2 done flag, or a fault).
    """

    def __init__(self):
        self.mem = {}                 # word address -> 32-bit value
        self.writes = []              # list of (addr, n_words) for burst checks
        self.read_overrides = {}      # addr -> list of values to return
        self.spi_inited = False
        self.clk_rst = None           # (chip_clk_en, chip_rstn)

    def init_spi(self):
        self.spi_inited = True

    def config_clk_rst(self, chip_clk_en, chip_rstn):
        self.clk_rst = (chip_clk_en, chip_rstn)

    def write_mem(self, addr, data_words):
        if isinstance(data_words, int):
            data_words = [data_words]
        self.writes.append((addr & 0xFFFFFFFF, len(data_words)))
        for i, v in enumerate(data_words):
            self.mem[(addr + i * 4) & 0xFFFFFFFF] = v & 0xFFFFFFFF

    def read_mem(self, addr, length=1, timeout=0.5):
        addr &= 0xFFFFFFFF
        if addr in self.read_overrides:
            return self.read_overrides[addr]
        return [self.mem.get((addr + i * 4) & 0xFFFFFFFF, 0) for i in range(length)]


class TestElfLoader(unittest.TestCase):
    """The transport-agnostic ELF reader."""

    def test_parse_helloworld(self):
        img: ElfImage = parse_elf(ELF_PATH)
        self.assertTrue(img.is_64bit)
        self.assertEqual(img.entry, HELLO_ENTRY)
        self.assertEqual(len(img.segments), 1)
        seg = img.segments[0]
        self.assertEqual(seg.addr, HELLO_SEG_ADDR)
        self.assertEqual(img.total_bytes, len(seg.data))

    def test_first_word_byte_order(self):
        # The first loaded word must be the first instruction, little-endian.
        img = parse_elf(ELF_PATH)
        words = bytes_to_words(img.segments[0].data)
        self.assertEqual(words[0], HELLO_FIRST_WORD)

    def test_bytes_to_words_little_endian(self):
        self.assertEqual(bytes_to_words(b"\x0d\xf0\xfe\xca"), [0xCAFEF00D])

    def test_bytes_to_words_pads_to_word(self):
        # 5 bytes -> 2 words, tail zero-padded.
        self.assertEqual(bytes_to_words(b"\x01\x00\x00\x00\xff"), [0x1, 0xFF])

    def test_bad_magic_rejected(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, b"NOTELF" + b"\x00" * 64)
            os.close(fd)
            self.assertRaises(ValueError, parse_elf, path)
        finally:
            Path(path).unlink()


class TestSpiProgramLoader(unittest.TestCase):
    """The SPI-specific load + scratch-launch logic."""

    def setUp(self):
        self.chip = StubChip()
        self.loader = SpiProgramLoader(self.chip, verbose=False)

    def test_set_entry_splits_64bit(self):
        self.loader.set_entry(0x1_8000_0000)  # > 32 bits, exercises both halves
        self.assertEqual(self.chip.mem[SCRATCH_0], 0x80000000)
        self.assertEqual(self.chip.mem[SCRATCH_1], 0x1)

    def test_launch_sets_go_bit(self):
        self.loader.launch()
        self.assertEqual(self.chip.mem[SCRATCH_2], SCRATCH2_GO_BIT)

    def test_load_image_places_bytes(self):
        img = parse_elf(ELF_PATH)
        self.loader.load_image(img)
        words = bytes_to_words(img.segments[0].data)
        for i, w in enumerate(words):
            self.assertEqual(self.chip.mem[(HELLO_SEG_ADDR + i * 4) & 0xFFFFFFFF], w)

    def test_load_and_run_full_sequence(self):
        img = self.loader.load_and_run(ELF_PATH, init_spi=True, verify=True)
        # init_spi happened, program bytes landed, entry + go-bit set.
        self.assertTrue(self.chip.spi_inited)
        self.assertEqual(self.chip.mem[HELLO_SEG_ADDR], HELLO_FIRST_WORD)
        self.assertEqual(self.chip.mem[SCRATCH_0], img.entry & 0xFFFFFFFF)
        self.assertEqual(self.chip.mem[SCRATCH_1], (img.entry >> 32) & 0xFFFFFFFF)
        self.assertEqual(self.chip.mem[SCRATCH_2], SCRATCH2_GO_BIT)

    def test_verify_failure_aborts_before_launch(self):
        # Corrupt one segment word in the stub right after it's written, by
        # overriding the readback of the segment's first word.
        self.chip.read_overrides[HELLO_SEG_ADDR] = [0xDEADBEEF]  # length-1 read
        # load_and_run reads the whole segment at once; emulate a mismatch by
        # making that read return a wrong-length / wrong-value list.
        img = parse_elf(ELF_PATH)
        nwords = len(bytes_to_words(img.segments[0].data))
        self.chip.read_overrides[HELLO_SEG_ADDR] = [0] * nwords  # all-zero != real
        self.assertRaises(RuntimeError, self.loader.load_and_run,
                          ELF_PATH, True, True)  # elf, init_spi, verify
        # The go bit must NOT have been set (launch never reached).
        self.assertNotIn(SCRATCH_2, self.chip.mem)

    def test_verify_image_pass(self):
        img = parse_elf(ELF_PATH)
        self.loader.load_image(img)
        self.assertTrue(self.loader.verify_image(img))

    def test_wait_for_eoc_decodes_exit_code(self):
        # Bootrom writes (retval << 1) | 1; exit code 7 -> 0xF.
        self.chip.read_overrides[SCRATCH_2] = [(7 << 1) | SCRATCH2_DONE_BIT]
        self.assertEqual(self.loader.wait_for_eoc(timeout=0.1), 7)

    def test_wait_for_eoc_timeout_returns_none(self):
        self.chip.read_overrides[SCRATCH_2] = [0]  # done bit never set
        self.assertIsNone(self.loader.wait_for_eoc(timeout=0.05, poll_interval=0.01))


class TestBurstChunking(unittest.TestCase):
    """write_segment must split > MAX_BURST_WORDS into multiple frames with
    correctly advanced addresses (the SPI burst-length field is 16 bits)."""

    def test_single_frame_when_small(self):
        chip = StubChip()
        SpiProgramLoader(chip, verbose=False).write_segment(0x80000000, [1, 2, 3])
        self.assertEqual(chip.writes, [(0x80000000, 3)])

    def test_split_when_over_max(self):
        chip = StubChip()
        n = MAX_BURST_WORDS + 10           # one full frame + a small remainder
        words = list(range(n))
        SpiProgramLoader(chip, verbose=False).write_segment(0x80000000, words)
        # Expect two frames: [MAX_BURST_WORDS] then [10], addresses contiguous.
        self.assertEqual(len(chip.writes), 2)
        self.assertEqual(chip.writes[0], (0x80000000, MAX_BURST_WORDS))
        second_addr = (0x80000000 + MAX_BURST_WORDS * 4) & 0xFFFFFFFF
        self.assertEqual(chip.writes[1], (second_addr, 10))
        # And every word must be readable at its correct byte address.
        self.assertEqual(chip.mem[0x80000000], 0)
        self.assertEqual(chip.mem[second_addr], MAX_BURST_WORDS)


class TestMultiSegment(unittest.TestCase):
    """A synthetic multi-segment image (like the real compute kernels that
    scatter across L2 0x8000_0000 and Ising L1 0x9000_0000)."""

    def test_each_segment_to_its_own_address(self):
        img = ElfImage(
            entry=0x80000000,
            is_64bit=True,
            segments=[
                Segment(0x80000000, b"\xAA\xBB\xCC\xDD"),
                Segment(0x90000000, b"\x11\x22\x33\x44\x55\x66\x77\x88"),
            ],
        )
        chip = StubChip()
        SpiProgramLoader(chip, verbose=False).load_image(img)
        self.assertEqual(chip.mem[0x80000000], 0xDDCCBBAA)   # little-endian
        self.assertEqual(chip.mem[0x90000000], 0x44332211)
        self.assertEqual(chip.mem[0x90000004], 0x88776655)


if __name__ == "__main__":
    # The individual test_* methods are never called explicitly. unittest finds
    # them by reflection: it scans this module for unittest.TestCase subclasses,
    # then within each runs every method whose name starts with "test" (creating
    # a fresh instance and calling setUp() before each one). unittest.main()
    # below is what triggers that scan
    unittest.main(verbosity=2)

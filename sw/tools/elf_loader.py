# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Created by Claude on 2025-06-01

# Transport-agnostic ELF reader for the LAGD (Cheshire) RISC-V SoC.
#
# This module ONLY parses an already-built ELF (produced by riscv-gcc in the
# lagd-im SW build) into loadable segments + the entry point. It knows nothing
# about how the bytes reach the chip -- the same output feeds the SPI loader
# today and could feed a JTAG or UART loader later. The only transport-specific
# part of "loading a program" is who writes the bytes and how the core is
# launched; that lives in the per-transport backend (e.g. spi_program_loader.py),
# not here.
#
# Pure standard library (struct only): no pyelftools dependency, so it runs on
# the locked Zedboard Python (3.6.15, numpy-only) as well as a dev machine.
#
# It mirrors what the simulation's elfloader.cpp does (read_elf / get_section /
# get_entry): iterate PT_LOAD program headers, take each one's PHYSICAL load
# address (p_paddr) and bytes, and report e_entry.
#
# Targets Python 3.6 (the locked Zedboard runtime): no 3.7+ `from __future__
# import annotations`, no 3.10+ `X | Y` annotations -- uses the typing module.

import argparse
import struct
from pathlib import Path
from typing import List, NamedTuple

# ELF identification
_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFCLASS64 = 2
_ELFDATA2LSB = 1  # little-endian

# Program-header type
_PT_LOAD = 1


class Segment(NamedTuple):
    """One loadable chunk: place `data` at physical address `addr`.

    `data` is already zero-padded from p_filesz up to p_memsz, so writing all of
    it also clears the segment's .bss tail (matching a normal program loader).
    """

    addr: int
    data: bytes


class ElfImage(NamedTuple):
    entry: int
    is_64bit: bool
    segments: List[Segment]

    @property
    def total_bytes(self) -> int:
        return sum(len(s.data) for s in self.segments)


def parse_elf(path: str) -> ElfImage:
    """Parse an ELF file into (entry, PT_LOAD segments).

    Supports little-endian ELF32 and ELF64 (the LAGD toolchain emits
    elf64-littleriscv). Raises ValueError on anything unexpected.
    """
    with Path(path).open("rb") as f:
        blob = f.read()

    if blob[:4] != _ELF_MAGIC:
        raise ValueError(f"{path}: not an ELF file (bad magic)")

    ei_class = blob[4]
    ei_data = blob[5]
    if ei_data != _ELFDATA2LSB:
        raise ValueError(f"{path}: only little-endian ELF is supported")

    if ei_class == _ELFCLASS64:
        # ELF64 header field offsets
        (e_entry,) = struct.unpack_from("<Q", blob, 0x18)
        (e_phoff,) = struct.unpack_from("<Q", blob, 0x20)
        (e_phentsize,) = struct.unpack_from("<H", blob, 0x36)
        (e_phnum,) = struct.unpack_from("<H", blob, 0x38)
        is_64 = True
    elif ei_class == _ELFCLASS32:
        (e_entry,) = struct.unpack_from("<I", blob, 0x18)
        (e_phoff,) = struct.unpack_from("<I", blob, 0x1C)
        (e_phentsize,) = struct.unpack_from("<H", blob, 0x2A)
        (e_phnum,) = struct.unpack_from("<H", blob, 0x2C)
        is_64 = False
    else:
        raise ValueError(f"{path}: unknown ELF class {ei_class}")

    segments: List[Segment] = []
    for i in range(e_phnum):
        ph = e_phoff + i * e_phentsize
        (p_type,) = struct.unpack_from("<I", blob, ph)
        if p_type != _PT_LOAD:
            continue

        if is_64:
            # ELF64 program header: type(4) flags(4) offset(8) vaddr(8)
            # paddr(8) filesz(8) memsz(8) align(8)
            (p_offset,) = struct.unpack_from("<Q", blob, ph + 0x08)
            (p_paddr,) = struct.unpack_from("<Q", blob, ph + 0x18)
            (p_filesz,) = struct.unpack_from("<Q", blob, ph + 0x20)
            (p_memsz,) = struct.unpack_from("<Q", blob, ph + 0x28)
        else:
            # ELF32 program header: type(4) offset(4) vaddr(4) paddr(4)
            # filesz(4) memsz(4) flags(4) align(4)
            (p_offset,) = struct.unpack_from("<I", blob, ph + 0x04)
            (p_paddr,) = struct.unpack_from("<I", blob, ph + 0x0C)
            (p_filesz,) = struct.unpack_from("<I", blob, ph + 0x10)
            (p_memsz,) = struct.unpack_from("<I", blob, ph + 0x14)

        if p_memsz == 0:
            continue

        data = blob[p_offset:p_offset + p_filesz]
        if p_memsz > p_filesz:
            # .bss tail: zero-fill so loading the segment also clears it.
            data = data + b"\x00" * (p_memsz - p_filesz)
        segments.append(Segment(p_paddr & 0xFFFFFFFF if not is_64 else p_paddr, data))

    if not segments:
        raise ValueError(f"{path}: no PT_LOAD segments found")

    return ElfImage(entry=e_entry, is_64bit=is_64, segments=segments)


def bytes_to_words(data: bytes) -> List[int]:
    """Convert a byte string into a list of 32-bit little-endian words.

    Pads with zero bytes up to a 4-byte boundary. Little-endian matches the
    RISC-V ISA, the AXI bus, and the value-preserving SPI path, so no byte
    swapping is needed end to end.
    """
    if len(data) % 4:
        data = data + b"\x00" * (4 - len(data) % 4)
    return list(struct.unpack(f"<{len(data) // 4}I", data))


def _main() -> int:
    """Offline self-test: print the segment table + entry for an ELF.

    Needs no hardware -- useful to sanity-check parsing against the .dump file.
    """
    ap = argparse.ArgumentParser(description="Inspect an ELF's loadable segments")
    ap.add_argument("elf", help="path to the .elf file")
    args = ap.parse_args()

    img = parse_elf(args.elf)
    print(f"ELF{'64' if img.is_64bit else '32'}, entry = 0x{img.entry:08X}")
    print(f"{'load_addr':<18} {'bytes':<12} words")
    for seg in img.segments:
        print(f"0x{seg.addr:016X} {len(seg.data):<12} {len(bytes_to_words(seg.data))}")
    print(f"total: {img.total_bytes} bytes across {len(img.segments)} segment(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

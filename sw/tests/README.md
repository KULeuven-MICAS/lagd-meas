# sw/tests

Top-level scripts and tests. Run them **from the `sw/` directory** so the
`lib.*` and `tools.*` imports resolve, e.g. `python3 tests/chip_load_spi.py`.

This README covers the program-loading and test files. (`chip_test.py`,
`perip_test.py`, and `pll_test.py` are the chip / periphery / PLL interactive +
writeback test scripts; they are documented separately.)

## chip_load_spi.py

End-to-end example that loads a program ELF onto the chip over SPI and launches
it. Wires together `lib/chip_driver.py` (the SPI transport), `tools/elf_loader.py`
(ELF parsing) and `tools/spi_program_loader.py` (segment writes + launch).

On startup it runs `smoke_test()` first; `main()` only proceeds if that passes.

- `smoke_test()` — a harmless SPI round-trip: writes a known word to SCRATCH_0
  and reads it back, with no program launch. Confirms the whole path
  (ChipDriver -> xillybus -> FPGA chip_controller -> Quad-SPI -> chip's AXI SPI
  slave -> SCRATCH register) and the byte order. Run it once on fresh hardware
  before trusting a full load. Diagnoses failures: byte-swap => endianness;
  partial => quad-lane/timing; nothing read => clk/reset, wiring, or device files.
- `main()` — the full flow: release the core (`config_clk_rst`), enable Quad-SPI
  (`init_spi`), write every PT_LOAD segment, read-back verify, write the entry
  point to SCRATCH_0/1, set the SCRATCH_2 go bit (the core jumps to the entry),
  and poll SCRATCH_2 for the exit code.

Pass the ELF as an argument to load a different program; it defaults to
`sw/inputs/helloworld.spm.elf`. **Prerequisite (hardware): boot_mode pins
strapped to 0** (passive boot).

Run (after `source env.sh` at the repo root):
```
python3 sw/tests/chip_load_spi.py                    # smoke test, then load + launch
python3 sw/tests/chip_load_spi.py path/to/other.elf  # a different program
python3 -i sw/tests/chip_load_spi.py                 # interactive: open_ports(); loader.load_and_run(...)
```

See `doc/spi_program_loading.md` for the full background (boot handshake, address
map, SPI protocol, endianness).

## test_loader_stub.py

Hardware-free unit tests (stdlib `unittest`, no pytest) for the SPI program
loader. They run the full Python logic against a `StubChip` that records
`write_mem`/`read_mem` into a flat memory dict -- no Zedboard, FPGA, or chip
needed. This is the repeatable regression net for the loader logic.

Covers: ELF parsing + entry/segment addresses, little-endian byte order, the
SCRATCH entry/launch handshake, burst chunking (splitting > 65535-word
segments), multi-segment images, and -- importantly -- that a failed read-back
verify aborts **before** the go bit is set (a corrupt load can never launch).

Does **not** cover (needs hardware): the FPGA RTL, SPI wiring/timing, the
physical chip. For the RTL path use the `fpga/` chip_controller sim; for the
live software->FPGA path use the writeback loopback in `chip_test.py`.

Run:
```
python3 -m unittest tests.test_loader_stub      # from sw/
python3 tests/test_loader_stub.py               # also works (adds sw/ to path)
```

## __init__.py

Marks `tests/` as a Python package so `python3 -m unittest tests.test_loader_stub`
resolves the module. No code.

## Related (not in this folder)

- `inputs/` — prebuilt ELFs (e.g. `helloworld.spm.elf`) copied from the lagd-im
  SW build, with `.dump` disassembly for reference. Loaded by the scripts above.
- `tools/elf_loader.py` — transport-agnostic ELF reader (PT_LOAD segments +
  entry). Reusable by SPI/JTAG/UART loaders. Standalone:
  `python3 tools/elf_loader.py inputs/helloworld.spm.elf`.
- `tools/spi_program_loader.py` — the `SpiProgramLoader` class: writes segments
  over SPI and performs the SCRATCH-register launch. Also a CLI:
  `python3 tools/spi_program_loader.py inputs/helloworld.spm.elf [--verify] [--wait]`.

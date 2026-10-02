# sw/tests

Top-level scripts and tests. Run them **from the lagd-meas root**, e.g. `python3 sw/tests/chip_load_spi.py`.

This README covers the program-loading and test files. (`chip_diag.py`,
`perip_test.py`, and `pll_test.py` are the chip / periphery / PLL interactive +
writeback test scripts; they are documented separately.)

## chip_load_spi.py

End-to-end example that loads a program ELF onto the chip over SPI and launches
it. Wires together `lib/chip_driver.py` (the SPI transport), `tools/elf_loader.py`
(ELF parsing) and `tools/spi_program_loader.py` (segment writes + launch).

`--smoke-test` runs `smoke_test()` first; `main()` only proceeds if that passes.

- `smoke_test()` — a harmless SPI round-trip: writes a known word to SCRATCH_0
  and reads it back, with no program launch. Confirms the whole path
  (ChipDriver -> xillybus -> FPGA chip_controller -> Quad-SPI -> chip's AXI SPI
  slave -> SCRATCH register) and the byte order. Run it once on fresh hardware
  before trusting a full load. Diagnoses failures: byte-swap => endianness;
  partial => quad-lane/timing; nothing read => clk/reset, wiring, or device files.
- `main()` — the full flow: release the core (`config_clk_rst`), enable Quad-SPI
  (`init_spi`), write every PT_LOAD segment in packed Xillybus transfers,
  optionally read-back verify with `--verify`, write the entry point to
  SCRATCH_0/1, set the SCRATCH_2 go bit (the core jumps to the entry), and poll
  SCRATCH_2 for the exit code. `--run-timeout 0` waits indefinitely while keeping
  the Xillybus ports and FPGA-provided chip clock open.

Pass the ELF as an argument to load a different program; it defaults to
`sw/inputs/helloworld.spm.elf`. **Prerequisite (hardware): boot_mode pins
strapped to 0** (passive boot).

Run (after `source env.sh` at the repo root):
```
python3 sw/tests/chip_load_spi.py                    # raw load + launch; wait up to 60 s
python3 sw/tests/chip_load_spi.py path/to/other.elf  # a different program
python3 sw/tests/chip_load_spi.py path/to/other.elf --smoke-test --verify
python3 sw/tests/chip_load_spi.py path/to/other.elf --run-timeout 0  # wait forever
python3 -i sw/tests/chip_load_spi.py                 # interactive: open_ports(); loader.load_and_run(...)
```

See `doc/spi_program_loading.md` for the full background (boot handshake, address
map, SPI protocol, endianness).

## chip_load_spi_repeat.py

Runs the same ELF repeatedly in one persistent Python process. It opens the
Xillybus ports and configures SCK once, then performs a fresh chip reset,
Quad-SPI initialization, load, launch, and EOC wait for every run. The default
is ten runs of `lagd_dcompute.spm.elf` at 12.5 MHz with a 1 ms reset hold.

Run:
```
python sw/tests/chip_load_spi_repeat.py
python sw/tests/chip_load_spi_repeat.py --runs 10 --sck 12500000
```

The final summary reports the minimum, median, mean, and maximum per-run time.
Python startup, port opening, and the one-time SCK configuration are excluded
from those per-run measurements.

## test_loader_stub.py

Hardware-free unit tests (stdlib `unittest`, no pytest) for the SPI program
loader. They run the full Python logic against a `StubChip` that records
`write_mem`/`read_mem` into a flat memory dict -- no Zedboard, FPGA, or chip
needed. This is the repeatable regression net for the loader logic.

Covers: ELF parsing + entry/segment addresses, little-endian byte order, packed
and partial Xillybus writes, CLI options, the SCRATCH entry/launch handshake,
burst chunking (splitting > 65535-word segments), EOC timeout behavior,
multi-segment images, and -- importantly -- that a failed read-back verify
aborts **before** the go bit is set (a corrupt load can never launch).

Does **not** cover (needs hardware): the FPGA RTL, SPI wiring/timing, the
physical chip. For the RTL path use the `fpga/` chip_controller sim; for the
live software->FPGA path use the writeback loopback in `chip_test.py`.

Run:
```
python3 sw/tests/test_loader_stub.py
```

## Related (not in this folder)

- `inputs/` — prebuilt ELFs (e.g. `helloworld.spm.elf`) copied from the lagd-im
  SW build, with `.dump` disassembly for reference. Loaded by the scripts above.
- `tools/elf_loader.py` — transport-agnostic ELF reader (PT_LOAD segments +
  entry). Reusable by SPI/JTAG/UART loaders. Standalone:
  `python3 tools/elf_loader.py inputs/helloworld.spm.elf`.
- `tools/spi_program_loader.py` — the `SpiProgramLoader` class: writes segments
  over SPI and performs the SCRATCH-register launch. Also a CLI:
  `python3 sw/tools/spi_program_loader.py sw/inputs/helloworld.spm.elf
  [--verify] [--wait] [--run-timeout SECONDS]`.

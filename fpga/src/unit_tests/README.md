# Unit testbenches

Self-checking SystemVerilog testbenches for the FPGA controllers, run with the
**Xilinx Vivado simulator (`xsim`)**. Each testbench drives its DUT with stimulus
and asserts the results in-simulation, printing a console `PASS` / `FAIL` summary
and exiting non-zero on failure (so they work in CI and `make`).

| Testbench | DUT | What it covers |
|-----------|-----|----------------|
| [`chip_controller/`](chip_controller/) | [`chip_controller.sv`](../verilog/chip_controller.sv) | command decode, config clk/rst, Quad-SPI enable, single/burst write & read, write/read loopback, output-FIFO backpressure, marker drop |
| [`perip_controller/`](perip_controller/) | [`perip_controller.sv`](../verilog/perip_controller.sv) | DAC (AD8802) single-port SPI command path |

These are **simulation only** — they do not need the board, a bitstream, or JTAG.
For in-system debugging of the running FPGA, use an ILA instead.

## Prerequisites

`xsim` / `xvlog` / `xelab` must be on your `PATH`. Source your Vivado settings
first, e.g.:

```bash
source /path/to/Vivado/settings64.sh
```

The `make sim` target checks for this and prints a clear error if `xvlog` is
missing.

## Running a testbench

There are two equivalent ways.

### 1. From the testbench folder

```bash
cd chip_controller        # or perip_controller
make sim                  # compile + run, console PASS/FAIL
make sim DUMP=1           # ... and also write a VCD into vivado-runs/
make wave                 # shortcut for `make sim DUMP=1`
make clean                # remove the generated vivado-runs/ directory
```

### 2. From the `fpga/` top-level Makefile

The top Makefile forwards to a testbench via the `TB=<name>` variable
(default `TB=chip_controller`):

```bash
cd ../..                          # fpga/
make sim TB=chip_controller       # run the chip_controller suite
make sim TB=perip_controller      # run the perip_controller suite
make sim TB=chip_controller DUMP=1   # ... with a VCD
make sim-clean TB=chip_controller    # clean that testbench's run dir
```

## Output

All run artifacts (xvlog/xelab/xsim logs, the compiled snapshot, and the optional
VCD) are written to `vivado-runs/` inside the testbench folder. This directory is
git-ignored ([.gitignore](.gitignore)). The VCD (when `DUMP=1`) is named
`tb_<name>.vcd` and can be opened in any waveform viewer (GTKWave, Vivado, etc.).

## How it works

Each testbench folder has its own small `Makefile` that sets two variables and
includes the shared [`common.mk`](common.mk):

- `SIM_TOP` — the top testbench module name.
- `SIM_SRCS` — the source list, **command-API file first**. The `*_command_api.sv`
  file holds the shared `$unit`-scope typedefs/enums; the bitstream flow marks it
  `IS_GLOBAL_INCLUDE`, and listing it first keeps it in the same compilation unit
  for a single `xvlog` invocation.

`common.mk` provides the `sim` / `wave` / `clean` targets and runs the standard
`xvlog -sv` → `xelab` → `xsim -runall` flow.

## Adding a new testbench

1. Create `fpga/src/unit_tests/<my_dut>/`.
2. Add `tb_<my_dut>.sv` (plus any models it needs).
3. Add a `Makefile` modeled on [`chip_controller/Makefile`](chip_controller/Makefile):
   set `SIM_TOP` and `SIM_SRCS` (command-API file first), then
   `include ../common.mk`.
4. Run it with `make sim` from the folder, or `make sim TB=<my_dut>` from `fpga/`.

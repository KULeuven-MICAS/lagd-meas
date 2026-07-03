# JTAG bring-up testcases

Step-by-step bring-up ladder for the JTAG link to the LAGD / Cheshire chip, via the
on-board **FT4232H** (channel A / ADBUS) and **OpenOCD**. Run the rungs **in order** —
each proves a new layer and is a prerequisite for the next, so a failure tells you
exactly where to look.

| # | Test | Proves | On failure, suspect |
|---|------|--------|---------------------|
| 1 | [`01_idcode/`](01_idcode/) | JTAG electrical link — reads IDCODE `0x1c5e5db3` | wiring, level-shifter DIR straps, TRST, IO voltage, speed |
| 2 | [`02_halt/`](02_halt/) | Debug module works **and core clock runs** — halts the hart, reads CSRs | core clock / PLL not running (not wiring) |
| 3 | [`03_load_run/`](03_load_run/) | Full debug data path — loads an ELF, runs it, checks return code | payload, or SBA/memory access |

Each folder has its own README with expected output and failure modes.

## Quick run

```bash
cd 01_idcode   && openocd -f openocd.scan.tcl     # IDCODE
cd ../02_halt  && openocd -f openocd.halt.tcl     # halt + CSRs
cd ../03_load_run && ./run.sh                     # load & run helloworld
```

All run at 100 kHz (safe for bring-up) and exit on their own with a non-zero status on
FAIL.

## Diagnostics vs. tool

- **`01_idcode` and `02_halt` are self-contained diagnostics** — their logic *is* the
  test, so each carries its own OpenOCD script.
- **`03_load_run` is a thin example** of the reusable JTAG run flow, which lives in
  [`../../sw/jtag/`](../../sw/jtag/) (`run_elf.sh` → `openocd.run.tcl`). That's the tool
  you'll use routinely to run programs on the chip once bring-up passes; `sw/jtag` also
  provides `openocd.server.tcl` for interactive GDB.

## Common prerequisites (all rungs)

- OpenOCD with `ftdi` + `riscv` support; board powered; FT4232H connected.
- Linux: release `ftdi_sio` from **interface 0** so OpenOCD can claim the JTAG channel
  (details in [`01_idcode/README.md`](01_idcode/)). The UART channel (interface 2) stays
  as `/dev/ttyUSB*` for [`../../uart/send_uart.py`](../../uart/).
- From rung 2 on, the chip's **core clock must be running** (external clk pad / PLL,
  `clk_sel`).

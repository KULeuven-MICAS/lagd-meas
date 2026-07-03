# Chip testcases

Bench bring-up tests for the LAGD / Cheshire chip, grouped by interface. Each group is a
step-by-step ladder — run the rungs in order; a failure tells you which layer broke.

| Group | Ladder | Reusable tool |
|-------|--------|---------------|
| [`jtag/`](jtag/) | `01_idcode` → `02_halt` → `03_load_run` | [`../sw/jtag/`](../sw/jtag/) (`run_elf.sh`, OpenOCD scripts) |
| [`uart/`](uart/) | `01_loopback` → `02_handshake` → `03_load_run` | [`../sw/uart/`](../sw/uart/) (`send_uart.py`) |

See each group's `README.md` for the ladder details.

## TODO / deferred

1. **`00_clock` — clock/PLL enable (SPI/PLL, not JTAG/UART).**
   `jtag/02_halt` and `uart/02_handshake` both assume the chip's **core clock is
   running**. On this chip the clock/PLL is brought up over the **SPI/PLL config
   interface** (the sim fixture's "switch the clocks on" SPI write), which is neither a
   JTAG nor a UART operation. If those rungs fail on a dead clock on the bench, add a
   clock-enable step as its own group (e.g. `testcases/spi/` or `testcases/clock/`) that
   runs *before* the JTAG/UART ladders. Not built yet because it may be unnecessary if
   the board supplies a free-running clock on the clock pad.

2. **OpenOCD `read_memory` vs `mem2array`.**
   `sw/jtag/openocd.run.tcl` polls the EOC scratch with `read_memory` (modern OpenOCD
   API). If the bench OpenOCD is older and errors on `read_memory`, swap it for the
   legacy `mem2array` (a one-line change). Confirm the installed OpenOCD version on first
   bench use.

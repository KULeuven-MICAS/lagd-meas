# JTAG halt / debug-module check

Second bring-up test for the JTAG link to the LAGD / Cheshire chip. Run this **after
`01_idcode` passes**.

## Purpose

Prove that the **debug module works and the hart can be halted** — not just that the
JTAG TAP is alive. Concretely it:

1. examines the debug module (`init`),
2. halts hart 0 (`halt`),
3. confirms the target state is `halted`,
4. reads `mhartid`, `misa`, `pc` to prove **abstract/register access** works.

Unlike `01_idcode` (which is pure JTAG/TCK domain), this test exercises things that
live in the **core clock domain**. So it verifies two new things at once:

> The **debug module (DMI)** is functional **and the chip's core clock is running.**

This is the rung where a "clock not enabled" problem shows up.

## Prerequisites

- **`01_idcode` passes** (IDCODE = `0x1c5e5db3`). If it doesn't, fix that first — this
  test also asserts the IDCODE and will fail on the same wiring issues.
- **The chip has a running clock.** Examine/halt happen in the core clock domain, so a
  clock must be present: an external clock on the chip's clock pad and/or the PLL
  configured, with `clk_sel` set. In simulation the clock is provided directly (and the
  fixture even "switches the clocks on" over SPI); on real silicon you must ensure a
  clock is live before halting.
- OpenOCD with `ftdi` + `riscv` support; board powered; `ftdi_sio` released from
  interface 0 (see `01_idcode/README.md`).

## How to run

```bash
cd lagd-meas/testcases/jtag/02_halt
openocd -f openocd.halt.tcl
```

Runs at 100 kHz and exits on its own (it does not stay up as a server).

## Expected output — PASS

```
==================================================================
PASS: hart halted (debug module reachable, core clock running).
--- register readout (proves debug abstract/register access) ---
mhartid (...): 0x0000000000000000
misa    (...): 0x800000000014112d
pc      (...): 0x00000000020....
==================================================================
```

What to check:
- **`mhartid` = 0** — hart 0.
- **`misa`** — a large value with the top bits set (**MXL = 64-bit**) and the
  `I M A F D C` extension bits present (CVA6 is RV64GC). The exact value isn't critical;
  a non-zero RV64 value proves CSR reads work.
- **`pc`** — wherever the core was when halted (typically in the bootrom region
  `0x0200_....` if it came out of reset into the ROM).

If you get here, the debug module and core clock are good — proceed to the load/run
test.

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `FAIL (init/examine)` or `FAIL (halt)` with a timeout | **Core clock not running** — the #1 cause once `01_idcode` passes. Provide a clock (ext clk pad / PLL / `clk_sel`). |
| `unexpected target state: running` (won't stay halted) | Something is releasing the core (spurious reset, watchdog) — check reset wiring / straps. |
| IDCODE mismatch error at `init` | Not a halt issue — a JTAG regression; re-run `01_idcode`. |
| Register reads fail but halt succeeded | Abstract-command/access issue — try toggling `riscv set_prefer_sba on/off`. |

Because the JTAG electrical path is already proven by `01_idcode`, **a failure here
points at the debug module or (most often) the clock, not the wiring.**

## Note on the clock

Enabling the chip clock/PLL is **not** a JTAG operation — on this design it's done over
the SPI/PLL configuration interface (the sim fixture writes it over SPI). If this test
fails on the clock, that clock/PLL bring-up is the real prerequisite and may deserve its
own earlier testcase (e.g. a `00_clock` step) before JTAG debug can do anything useful.

## Where this sits in the bring-up ladder

1. **`lagd-meas/testcases/jtag/01_idcode/openocd.scan.tcl`** → IDCODE `0x1c5e5db3`. *(JTAG electrical OK)*
2. **`lagd-meas/testcases/jtag/02_halt/openocd.halt.tcl`** (this test) → hart halts, CSRs read. *(debug module + clock OK)*
3. Load & run an ELF (telnet/tcl or GDB): `load_image`, set `pc = 0x80000000`,
   `resume`, then poll the EOC scratch at `0x03000008` (bit0 = done, code = value >> 1).

# JTAG tools (LAGD / Cheshire chip, FT4232H + OpenOCD)

Reusable OpenOCD scripts for driving the chip over JTAG via the on-board **FT4232H**
(channel A / ADBUS). This is the "production" JTAG flow used **after bring-up**; the
step-by-step bring-up diagnostics live in `lagd-meas/testcases/jtag/`.

## Files

| File | Role |
|------|------|
| `openocd.ft4232.tcl` | **Adapter** config only (FTDI driver, pins, speed). No target. |
| `openocd.common.tcl` | **Tap + target** definitions + riscv settings. No actions. |
| `openocd.run.tcl` | **Load-and-run flow**: halt → load ELF → resume → poll EOC → report. |
| `openocd.server.tcl` | **Interactive GDB server**: halt and wait for GDB/telnet/tcl. |
| `run_elf.sh` | Shell wrapper around `openocd.run.tcl` (the easy entry point). |

`openocd.run.tcl` and `openocd.server.tcl` both `source` the adapter + common scripts,
so the pin mapping, IDCODE, and target definition live in exactly one place.

## Load & run a program (the common case)

```bash
cd lagd-meas/sw/jtag
./run_elf.sh ../inputs/helloworld.spm.elf
```

PASS prints `PASS: program finished, return code 0.` and exits 0. See
`testcases/jtag/03_load_run/` for this used as an example/regression check.

Options (passed through to OpenOCD):
```bash
./run_elf.sh app.spm.elf -c "set RUN_TIMEOUT 60"     # longer wait for EOC
./run_elf.sh app.spm.elf -c "set ADAPTER_KHZ 4000"   # faster JTAG clock
./run_elf.sh app.spm.elf -c "set ENTRY 0x80000000"   # non-default entry
```

How completion is detected: when the program's `main` returns, `crt0.S` `_exit` writes
`(return_code << 1) | 1` to **SCRATCH_2 at `0x03000008`**. The flow polls that word —
bit0 = done, `value >> 1` = return code.

## Interactive debugging (GDB)

```bash
cd lagd-meas/sw/jtag
openocd -f openocd.server.tcl        # GDB :3333, telnet :4444, tcl :6666
# in another terminal:
riscv64-unknown-elf-gdb your.elf -ex "target extended-remote :3333"
```

## Notes

- **Speed**: defaults to 100 kHz (safe). Raise via `-c "set ADAPTER_KHZ <kHz>"` once the
  link is proven (see `testcases/jtag/01_idcode`).
- **Memory access**: `openocd.run.tcl` sets `riscv set_prefer_sba on` so it can poll the
  EOC register while the core runs. If SBA misbehaves, set it `off` (progbuf).
- **Prerequisite**: the chip's **core clock must be running** (external clk pad / PLL,
  `clk_sel`). If `init`/`halt` fails, see `testcases/jtag/02_halt`.
- **Linux**: release `ftdi_sio` from interface 0 so OpenOCD can claim the JTAG channel;
  the UART channel (interface 2) stays as `/dev/ttyUSB*` for `uart/send_uart.py`.

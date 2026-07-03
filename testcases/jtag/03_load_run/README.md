# JTAG load & run (example)

Third bring-up test: load an ELF over JTAG, run it, and check its return code — the
**JTAG mirror of the UART loader** (`send_uart.py`). Run it **after `02_halt` passes**.

Unlike `01_idcode` / `02_halt` (self-contained diagnostics), this testcase is a **thin
example** of the reusable JTAG run flow. The actual flow lives in
`lagd-meas/sw/jtag/` — because loading and running a program is what you'll do
routinely once the chip is up, so it belongs with the tools, not inside a test. This
folder just calls it on a known ELF and checks the result.

## How to run

```bash
cd lagd-meas/testcases/jtag/03_load_run
./run.sh
```

`run.sh` invokes `lagd-meas/sw/jtag/run_elf.sh` on
`lagd-meas/sw/inputs/helloworld.spm.elf`. Extra OpenOCD options pass through, e.g.:
```bash
./run.sh -c "set RUN_TIMEOUT 60"     # longer wait for EOC
./run.sh -c "set ADAPTER_KHZ 4000"   # faster JTAG clock
```

## What it does (in `sw/jtag/openocd.run.tcl`)

1. `halt` the hart,
2. `load_image` — write the ELF's segments into chip memory (over the debug system bus),
3. clear the EOC scratch, then `resume` at the entry (`0x80000000`),
4. **poll the EOC scratch** until completion, and read the return code.

Passing proves **memory write (load), execution, and memory read (result)** all work
over JTAG — the full debug data path.

**Completion / EOC:** when the program's `main` returns, `crt0.S` `_exit` writes
`(return_code << 1) | 1` to **SCRATCH_2 at `0x03000008`**. The flow polls that word:
bit0 = done, `value >> 1` = return code. (Identical to the sim's `jtag_wait_for_eoc`.)

## Expected output — PASS

```
Loading ELF : /.../lagd-meas/sw/inputs/helloworld.spm.elf
Entry point : 0x80000000
Resuming    : at 0x80000000
Waiting     : poll 0x03000008 (timeout 30s) ...
==================================================================
PASS: program finished, return code 0.
==================================================================
```

## Prerequisites

- **`02_halt` passes** — debug module reachable and the **core clock running**.
- OpenOCD with `ftdi` + `riscv`; board powered; `ftdi_sio` released from interface 0
  (see `01_idcode/README.md`).

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `FAIL (init/examine)` or `FAIL (halt)` | Core clock / debug module — go back to `02_halt`. |
| `FAIL (load_image)` | ELF path wrong, or memory not writable at those addresses (SBA/crossbar). |
| `FAIL: timed out ... waiting for EOC` | Program trapped before `_exit`, wrong `ENTRY`, ELF misplaced, or SBA reads not working. |
| `FAIL: program returned non-zero code N` | The **load/run mechanism worked**, but the program itself reported failure (code N). |

A non-zero return code means JTAG is fine — it's the *payload* that failed. Only the
timeout or the load/halt errors indicate a JTAG/debug problem. (See
`lagd-meas/sw/jtag/README.md` for the SBA-vs-progbuf note and other options.)

## Relationship to the UART loader

Same end goal as `lagd-meas/uart/send_uart.py`, different transport:

| | UART (`send_uart.py`) | JTAG (`sw/jtag/run_elf.sh`) |
|---|---|---|
| Load | bootrom UART debug `WRITE` commands | `load_image` over debug system bus |
| Launch | `EXEC` (bootrom jumps to entry) | `resume` at entry |
| Completion | bootrom sends `EOC` byte + code | poll `0x03000008` (SCRATCH_2) |
| Needs bootrom? | yes (passive boot) | no (debugger drives the core directly) |
| Speed | serial, slow | much faster |

## Where this sits in the bring-up ladder

1. **`lagd-meas/testcases/jtag/01_idcode/openocd.scan.tcl`** → IDCODE `0x1c5e5db3`. *(JTAG electrical OK)*
2. **`lagd-meas/testcases/jtag/02_halt/openocd.halt.tcl`** → hart halts, CSRs read. *(debug module + clock OK)*
3. **`lagd-meas/testcases/jtag/03_load_run/run.sh`** (this test) → calls `sw/jtag` flow; load ELF, run, return code 0. *(full debug data path OK)*

# UART load & run (example)

Third UART bring-up test: load an ELF over UART, run it, and check the return code. Run
it **after `02_handshake` passes**.

Like JTAG `03_load_run`, this is a **thin example** of the reusable loader — the actual
flow lives in `lagd-meas/sw/uart/send_uart.py`. This folder just calls it on a known ELF
and checks the result.

## How to run

```bash
cd lagd-meas/testcases/uart/03_load_run
./run.sh
```

`run.sh` invokes `sw/uart/send_uart.py` on `sw/inputs/helloworld.spm.elf`. Options pass
through, e.g.:

```bash
./run.sh --verify               # read each segment back over UART and compare
./run.sh --no-exec --verify     # MEMORY CHECK ONLY: load + verify, don't run
./run.sh --device /dev/ttyUSB2  # pick the UART channel device
./run.sh --no-rtscts            # if RTS/CTS aren't wired
```

## What it does (in `sw/uart/send_uart.py`)

1. ACK handshake with the bootrom (as in `02_handshake`),
2. parse the ELF and **WRITE** each PT_LOAD segment into chip memory,
3. **EXEC** at the entry point (the bootrom jumps there),
4. stream any console output and wait for **EOC**, then read the 32-bit return code.

Passing proves the **full UART data path**: memory write, execution, and result
read-back — all through the bootrom's UART debug protocol.

## Memory check (the merged `memcheck`)

There's no separate `memcheck` rung — it's an option here. To exercise just the memory
path (bootrom `WRITE` + `READ` verify) **without running code**:

```bash
./run.sh --no-exec --verify
```

This isolates "can I move data to/from the chip over UART" from "can the program run",
which is handy when a full run fails and you want to know which half broke.

## Expected output — PASS

```
ELF      : /.../sw/inputs/helloworld.spm.elf
Entry    : 0x0000000080000000
Segments : 1, 847 bytes total
  0x0000000080000000  847 bytes
Port     : /dev/ttyUSB10 @ 115200 8N1, RTS/CTS=on
Handshake: sending ACK challenge ...
Handshake: chip responded, debug server is up.
Loaded   : 0x0000000080000000 (847 bytes)
Exec     : jumped to 0x0000000080000000
[chip] Hello World!
EOC      : return code 0
```

Exits 0 on PASS, non-zero on FAIL.

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `ERROR: no ACK from chip` | Handshake failed — go back to `02_handshake` (boot mode / clock / bootrom). |
| Fails during `WRITE`/`Loaded` | Memory not writable at those addresses, or a protocol desync (try `--no-rtscts`, lower nothing—baud is fixed). |
| `verify FAILED` (with `--verify`) | Data corruption on the link — flow control, or baud drift from a wrong clock/RTC. |
| Timeout waiting for `EOC` | Program trapped before `_exit`, or the EXEC'd entry is wrong. |
| `EOC : return code N` (non-zero) | The **load/run mechanism worked**; the program itself reported failure. |

A non-zero return code means UART is fine — it's the *payload* that failed.

## Relationship to the JTAG loader

Same end goal as `testcases/jtag/03_load_run` (`sw/jtag/run_elf.sh`), different transport:

| | UART (`send_uart.py`) | JTAG (`sw/jtag/run_elf.sh`) |
|---|---|---|
| Load | bootrom UART debug `WRITE` commands | `load_image` over debug system bus |
| Launch | `EXEC` (bootrom jumps to entry) | `resume` at entry |
| Completion | bootrom sends `EOC` byte + code | poll `0x03000008` (SCRATCH_2) |
| Needs bootrom? | yes (passive boot) | no (debugger drives the core directly) |
| Speed | serial, slow | much faster |

## Where this sits in the UART ladder

0. `lagd-meas/testcases/uart/00_loopback/loopback.py` → host serial path OK. *(optional, no chip)*
1. `lagd-meas/testcases/uart/01_portsweep/portsweep.py` → chip's UART found, bootrom answers. *(chip powered, clocked, passive boot)*
2. `lagd-meas/testcases/uart/02_handshake/run.sh` → bootrom reachable via the real loader (ACK↔ACK).
3. **`lagd-meas/testcases/uart/03_load_run/run.sh`** (this test) → load & run helloworld; also `--no-exec --verify` for a memory check. *(full UART data path)*

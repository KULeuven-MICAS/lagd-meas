# UART memory test (integrity + volume)

Fourth UART test: write several patterns over a memory region and read them back to
verify. Run it **after `03_load_run` passes**. Thin wrapper around
`send_uart.py --memtest` (the tool in `sw/uart/`).

## Purpose

Two things in one test:

- **Integrity** — each pattern is written over the *whole* region, so every memory cell
  sees every value. Catches **stuck bits** and, via the `addr-as-data` pattern,
  **address aliasing** on the UART data path (bootrom `WRITE`/`READ`).
- **Volume / sustained transfer** — a large region pushes a big block through the link,
  which is what actually stresses **RTS/CTS flow control**, the FIFO, and throughput.
  helloworld (847 B) never does this; a real large binary or dataset does. This test is
  the proxy for "can I reliably load a big blob over UART."

No code runs — it's the pure loader transport (like `--no-exec`, but a dedicated,
larger, patterned check).

## Patterns

`0x00`, `0xFF`, `0x55/0xAA`, `addr-as-data` (each word = its own address), and a
**seeded** pseudo-random fill (reproducible, so any failure repeats).

## How to run

```bash
cd lagd-meas/testcases/uart/04_memtest
./run.sh                          # default 8 KiB at 0x80000000 (L2 SPM)
./run.sh --mem-size 0x10000       # 64 KiB -- more flow-control / volume stress
./run.sh --mem-base 0x80000000 --mem-size 0x2000
./run.sh --device /dev/ttyUSB2 --no-rtscts
```

Bigger `--mem-size` = more stress but longer (8 KiB × 5 patterns ≈ a few seconds at
115200; scales linearly). Keep the region inside writable memory (L2 SPM is 64 KiB).

## Test commands (add `--no-rtscts` when mapping the chip on FPGA):

```bash
./testcases/uart/04_memtest/run.sh --no-rtscts --mem-base 0x10000000 --mem-size 0x4000 # check stack memory
./testcases/uart/04_memtest/run.sh --no-rtscts --mem-base 0x80000000 --mem-size 0x10000 # check l2 spm
./testcases/uart/04_memtest/run.sh --no-rtscts --mem-base 0x90000000 --mem-size 0x10000 # check l1_j_spm_c0 and l1_f_spm_c0
./testcases/uart/04_memtest/run.sh --no-rtscts --mem-base 0x90010000 --mem-size 0x10000 # check l1_j_spm_c1 and l1_f_spm_c1
```

## Expected output — PASS

```
Port     : /dev/ttyUSB10 @ 115200 8N1, RTS/CTS=on
Memtest  : 0x80000000 .. 0x80002000  (8192 bytes)
Handshake: sending ACK challenge ...
Handshake: chip responded, debug server is up.
  [0x00        ] OK  (8192 bytes)
  [0xFF        ] OK  (8192 bytes)
  [0x55/0xAA   ] OK  (8192 bytes)
  [addr-as-data] OK  (8192 bytes)
  [random      ] OK  (8192 bytes)
PASS: memtest OK over 8192 bytes at 0x80000000.
```

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `FAIL: memtest '0x00'/'0xFF' MISMATCH ...` | **Stuck bit** at that address, or memory not backed there. |
| `FAIL: memtest 'addr-as-data' MISMATCH ...` | **Addressing error** — bytes landing at the wrong address. |
| `FAIL: memtest 'random' MISMATCH ...` | Link corruption — **flow control** (try `--no-rtscts` or wire RTS/CTS), or baud drift from a wrong clock/RTC. |
| Mismatches appear only at **large** `--mem-size` | Sustained-transfer / FIFO / flow-control problem — the small `03_load_run` wouldn't have shown it. |

The reported address + expected/actual byte tells you exactly which cell and which bits
diverged.

## Where this sits in the UART ladder

0. `00_loopback/` → host serial path OK. *(optional, no chip)*
1. `01_portsweep/` → chip's UART found, bootrom answers. *(chip powered, clocked, passive boot)*
2. `02_handshake/` → bootrom reachable via the real loader.
3. `03_load_run/` → load & run an ELF. *(functional data path)*
4. **`04_memtest/`** (this test) → memory integrity + volume over UART. *(robustness)*

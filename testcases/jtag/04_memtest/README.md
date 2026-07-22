# JTAG memory test (integrity + volume)

Fourth JTAG test: write several patterns over a memory region via the debug **system
bus** and read them back to verify. Run it **after `03_load_run` passes**. Thin wrapper
around `sw/jtag/openocd.memtest.tcl`.

## Purpose

Same idea as the UART memtest, over the JTAG data path:

- **Integrity** — each pattern is written over the *whole* region, so every cell sees
  every value. Catches **stuck bits** and, via `addr-as-data`, **address aliasing** on
  the debug system-bus path.
- **Volume** — a larger region exercises sustained SBA transfer.

No code runs; this is the pure debug memory path.

## Patterns

`0x00000000`, `0xffffffff`, `0x55/0xAA`, `addr-as-data` (each word = its own address),
and a **seeded** pseudo-random fill (reproducible).

## How to run

```bash
cd lagd-meas/testcases/jtag/04_memtest
./run.sh                              # default 8 Kb (2048 words) at 0x80000000
./run.sh -c "set MEM_WORDS 16384"     # 64 Kb -- more volume stress
./run.sh -c "set ADAPTER_KHZ 4000"    # faster JTAG clock
```

To set **several variables**, either repeat `-c` or separate them with `;` inside one
`-c` (`;` is Tcl's statement separator) — the two forms are equivalent:

```bash
./run.sh -c "set MEM_WORDS 16384" -c "set ADAPTER_KHZ 4000"   # 64 Kb at a faster clock
./run.sh -c "set MEM_WORDS 16384; set ADAPTER_KHZ 4000"       # same thing, one -c
```

Any variable you don't set keeps its default, and `run.sh` places your `-c` **before**
`-f` so the values are in place by the time the Tcl script reads them. The full list of
variables and defaults is in the header of `sw/jtag/openocd.memtest.tcl` (`MEM_BASE`,
`MEM_WORDS`, `SEED`, `ADAPTER_KHZ`).

> **Speed:** at the 100 kHz bring-up clock, SBA is slow and a large region takes a
> while. Establish a reliable higher speed with `01_idcode` first, then raise
> `ADAPTER_KHZ` here (or keep `MEM_WORDS` small).

Keep the region inside writable memory (L2 SPM is 64 KiB from `0x80000000`).

## Expected output — PASS

```
Memtest: 0x80000000 .. 0x80002000  (2048 words / 8192 bytes)
  [0x00000000  ] OK  (2048 words)
  [0xffffffff  ] OK  (2048 words)
  [0x55/0xAA   ] OK  (2048 words)
  [addr-as-data] OK  (2048 words)
  [random      ] OK  (2048 words)
==================================================================
PASS: memtest OK over 8192 bytes at 0x80000000.
==================================================================
```

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `FAIL (init/examine)` or `FAIL (halt)` | Core clock / debug module — go back to `02_halt`. |
| `FAIL: memtest '0x...'/'0xffffffff' MISMATCH` | **Stuck bit**, or memory not backed at that address. |
| `FAIL: memtest 'addr-as-data' MISMATCH` | **Addressing error** on the system-bus path. |
| `FAIL (write/read ...)` | SBA access failing — try `riscv set_prefer_sba off` (progbuf), or check the OpenOCD version (`read_memory` support). |

The reported address + expected/actual word pinpoints the failing cell and bits.

## Where this sits in the JTAG ladder

1. `01_idcode/` → IDCODE `0x1c5e5db3`. *(JTAG electrical OK)*
2. `02_halt/` → hart halts, CSRs read. *(debug module + clock OK)*
3. `03_load_run/` → load ELF, run, return code 0. *(functional data path)*
4. **`04_memtest/`** (this test) → memory integrity + volume over JTAG. *(robustness)*

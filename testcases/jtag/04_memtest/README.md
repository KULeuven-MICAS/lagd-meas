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

Unlike the UART memtest, this one really reaches the SRAM — see
[Why the system bus, and how to verify it](#why-the-system-bus-and-how-to-verify-it).

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
`MEM_WORDS`, `SEED`, `ADAPTER_KHZ`, `MEM_ACCESS`, `DEBUG_LEVEL`).

## Why the system bus, and how to verify it

OpenOCD can reach memory two ways, and **only one of them tests memory**:

| Method | Path | Tests the SRAM? |
|--------|------|-----------------|
| `sysbus` (SBA) | debug module's own AXI master → crossbar → SRAM | **yes** — core and D$ not in the path |
| `progbuf` | the halted hart executes `ld`/`sd` for the debugger | **no** — goes through CVA6's L1 D$ |

The `progbuf` path has the same blind spot as the UART memtest: everything from
`0x8000_0000` up is a CVA6 **cacheable** region in this design (`gen_cva6_cfg` →
`CachedRegionAddrBase`, with `LlcOutRegionStart = 0x8000_0000`), and the write-back D$
is 32 KiB / 8-way. The default 8 KiB region fits entirely in cache, so the read-back is
answered from cache and a dead SRAM cell still passes.

So the script sets `MEM_ACCESS sysbus` with **no `progbuf` fallback** — if SBA can't
serve the access the test fails loudly instead of silently becoming a CPU test. A PASS
is therefore proof the transfers went over the system bus.

Two further confirmations:

**1. The `SBA probe` line** (printed automatically). It reads `sbcs`, the debug module's
System Bus Access control/status register (DMI `0x38`), and reports whether SBA exists
in hardware at all:

```
Access   : sysbus   (debug_level 2)
SBA probe: sbcs=0x2004080f  sbversion=1  sbasize=64 bit  sbaccess=8/16/32/64 bit  sberror=0
```

That is the value this design should report: `dm_top` is instantiated with
`BusWidth = Cfg.AxiDataWidth = 64`, and `dm_csrs.sv` derives `sbasize = BusWidth` and
`sbaccess8/16/32/64 = 1` (`sbaccess128 = 0`) from it, with `sbversion = 1` and the
`sbaccess` field resetting to `2` (32-bit).

`sbasize = 0` would mean the debug module has no bus master; the script bails there
rather than running a meaningless test. A non-zero `sberror` points at a failed bus
access (see the debug spec for the code).

**2. An empirical trace**, if you want to see the actual OpenOCD calls:

```bash
./run.sh -c "set DEBUG_LEVEL 3" 2>&1 | grep -oE '(read|write)_memory_[a-z0-9_]+' | sort | uniq -c
```

Expect only `read_memory_bus_v1` / `write_memory_bus_v1`. Anything ending in `_progbuf`
or `_abstract` means the CPU performed the access.

> `DEBUG_LEVEL 3` traces every DMI transaction and is very verbose — use it for a
> one-off check, not routine runs. It also slows the test noticeably.

To deliberately compare the two paths (e.g. to *demonstrate* the cache masking), run the
same region both ways:

```bash
./run.sh                                          # sysbus  -- true SRAM
./run.sh -c "set MEM_ACCESS progbuf"              # progbuf -- CPU + D$
```

> **Speed:** at the 100 kHz bring-up clock, SBA is slow and a large region takes a
> while. Establish a reliable higher speed with `01_idcode` first, then raise
> `ADAPTER_KHZ` here (or keep `MEM_WORDS` small).

Keep the region inside writable memory (L2 SPM is 64 KiB from `0x80000000`).

## Expected output — PASS

```
Access   : sysbus   (debug_level 2)
SBA probe: sbcs=0x2004080f  sbversion=1  sbasize=64 bit  sbaccess=8/16/32/64 bit  sberror=0
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
| `FAIL (write/read ...)` | SBA access failing. Check the `SBA probe` line first (`sbasize`, `sberror`). To confirm it's SBA-specific, retry with `-c "set MEM_ACCESS progbuf"` — if that passes, the debug module's bus master is the problem, not the memory. |
| `FAIL (SBA): sbasize=0` | The debug module reports no system bus master — memory could only be reached through the CPU, so no valid memory test is possible over JTAG. |

The reported address + expected/actual word pinpoints the failing cell and bits.

## Where this sits in the JTAG ladder

1. `01_idcode/` → IDCODE `0x1c5e5db3`. *(JTAG electrical OK)*
2. `02_halt/` → hart halts, CSRs read. *(debug module + clock OK)*
3. `03_load_run/` → load ELF, run, return code 0. *(functional data path)*
4. **`04_memtest/`** (this test) → memory integrity + volume over JTAG. *(robustness)*

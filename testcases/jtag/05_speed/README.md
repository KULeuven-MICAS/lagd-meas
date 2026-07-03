# JTAG speed sweep

Fifth JTAG test — a **characterization**, not a pass/fail gate: find the **highest
reliable JTAG clock (TCK)** for this board. The other rungs run at a safe 100 kHz; this
tells you how fast you can actually go, which matters for load/memtest throughput.

## What it does

Sweeps a list of speeds and runs a per-speed check at each, recording PASS/FAIL, then
reports the highest passing speed. Two modes:

| Mode | Per-speed check | Measures | Needs clock? |
|------|-----------------|----------|--------------|
| `memtest` (default) | `init` + `halt` + a small memtest | highest usable **debug** speed (TAP + DMI + SBA) | yes (run after `02_halt`) |
| `idcode` | read IDCODE only | highest **electrical** speed (pure TCK) | no (works before the clock is up) |

`memtest` is what you want for real use (it validates the whole path at speed).
`idcode` isolates the pure electrical limit and works even before the debug module/clock
are alive.

## How to run

```bash
cd lagd-meas/testcases/jtag/05_speed
./speed_sweep.sh                                   # debug-speed sweep (needs clock)
MODE=idcode ./speed_sweep.sh                       # electrical-only sweep
SPEEDS="100 1000 4000 10000" MEM_WORDS=512 ./speed_sweep.sh
```

Defaults: `SPEEDS="100 500 1000 2000 4000 8000 12000 16000 20000 30000"` kHz,
`MEM_WORDS=256` (1 KiB per check). Per-speed logs go to a temp dir (printed at the top).

## Expected output

```
JTAG speed sweep  (mode=memtest)
Logs: /tmp/tmp.XXXX
SPEED/kHz  RESULT
100        PASS
500        PASS
1000       PASS
...
16000      PASS
20000      FAIL   (/tmp/tmp.XXXX/speed_20000.log)
30000      FAIL   (/tmp/tmp.XXXX/speed_30000.log)

Highest reliable JTAG speed: 16000 kHz
Use it via:  openocd -c "set ADAPTER_KHZ 16000" -f <script>
(For margin, operate a step below the first FAIL.)
```

## Using the result

Set the speed for the other flows via `ADAPTER_KHZ`, e.g.:
```bash
../04_memtest/run.sh -c "set ADAPTER_KHZ 12000" -c "set MEM_WORDS 16384"
../../../sw/jtag/run_elf.sh app.elf -c "set ADAPTER_KHZ 12000"
```
Pick **one step below** the first FAIL for margin over temperature/voltage. This is also
what makes the JTAG `04_memtest` fast enough for large regions.

## Notes

- **Reliability isn't always monotonic** — a marginal speed may pass once and fail later.
  The sweep runs every listed speed (it doesn't stop at the first FAIL) so you see the
  full picture; still, treat the boundary as approximate and keep margin.
- If **everything FAILs** in `memtest` mode but `idcode` mode passes, the issue is the
  clock/debug module (see `02_halt`), not JTAG speed.
- Check the per-speed logs for *why* a speed failed (IDCODE mismatch vs SBA error).

## Where this sits in the JTAG ladder

1. `01_idcode/` → IDCODE. 2. `02_halt/` → halt + clock. 3. `03_load_run/` → load & run.
4. `04_memtest/` → memory integrity + volume.
5. **`05_speed/`** (this test) → highest reliable TCK; feeds `ADAPTER_KHZ` back into 3/4.

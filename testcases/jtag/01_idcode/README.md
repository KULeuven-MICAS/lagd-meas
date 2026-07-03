# JTAG IDCODE probe

First-bring-up test for the JTAG link to the LAGD / Cheshire chip via the on-board
**FT4232H** (channel A / ADBUS = JTAG) and **OpenOCD**.

## Purpose

Read the chip's JTAG **IDCODE** and nothing else. This is the very first thing to
verify on the bench, because the IDCODE lives entirely in the **JTAG (TCK) clock
domain**: it can be read even if the chip's core clock is off and the debug module /
CPU can't be reached yet. So a passing IDCODE isolates one question cleanly:

> Is the JTAG electrical path good? — TCK / TMS / TDI / TDO wiring, the level-shifter
> direction (DIR) straps, IO voltage, TRST, and adapter speed.

`openocd.scan.tcl` is deliberately **decoupled from the target**: it only creates the
TAP, scans the chain, prints what it finds, and exits. It does **not** try to halt the
hart or touch memory, so it won't fail for reasons unrelated to the JTAG link.

## Prerequisites

- OpenOCD installed (with `ftdi` + `riscv` support; mainline OpenOCD is fine).
- The board powered, with the FT4232H connected over USB.
- On Linux, the kernel's `ftdi_sio` grabs all four FT4232H channels as `/dev/ttyUSB*`.
  OpenOCD needs **interface 0 (ADBUS/JTAG)** released to libusb. If OpenOCD reports it
  cannot claim the interface, unbind `ftdi_sio` from interface 0 (a udev rule, or
  `echo <busport>:1.0 > /sys/bus/usb/drivers/ftdi_sio/unbind`). The UART channel
  (interface 2) can stay as `ttyUSB`.

## How to run

```bash
cd lagd-meas/testcases/jtag/01_idcode
openocd -f openocd.scan.tcl
```

The script runs at **100 kHz** (slow, for reliable first contact) and exits on its own.

## Expected output — PASS

```
Info : JTAG tap: riscv.cpu tap/device found: 0x1c5e5db3 (mfg: 0x6d9 (PULP), part: 0xc5e5, ver: 0x1)
   TapName             Enabled  IdCode     Expected   IrLen IrCap IrMask
-- ------------------- -------- ---------- ---------- ----- ----- ------
 0 riscv.cpu              Y     0x1c5e5db3 0x00000000     5  0x01  0x03
```

The number that matters is **`0x1c5e5db3`**. It decodes as:

| Field | Value | Meaning |
|-------|-------|---------|
| version | `0x1` | Cheshire version |
| part number | `0xc5e5` | Cheshire part |
| manufacturer | `0x6d9` | PULP Platform |

(The "Expected 0x00000000" column just means the script intentionally sets no
expected-id, so it reports whatever it finds instead of erroring on a mismatch.)

If you see `0x1c5e5db3`, the **JTAG link is good** — move on to the full config
(`lagd-meas/sw/jtag/openocd.ft4232.tcl`), whose `init; halt` also exercises the debug module.

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `... all ones` / IDCODE `0xffffffff` | TDO stuck high — usually the **TDO level-shifter DIR strap** wrong, or TDO return path broken |
| `... all zeroes` / IDCODE `0x00000000` | No data from TDO — TDO direction/wiring, or chip unpowered |
| `JTAG scan chain interrogation failed` | TCK/TMS not reaching the chip, wrong channel/pins, or **TRST held low** (TAP stuck in reset) |
| IDCODE present but **not** `0x1c5e5db3` | Wrong IR length, wrong device, or bit-slippage (try lower speed) |
| OpenOCD can't open the adapter | `ftdi_sio` still bound to interface 0 (see Prerequisites), or wrong `vid_pid` |

Check order when it fails: (1) `trst_n` pulled high, (2) TDO shifter DIR strap
(chip→FTDI), (3) IO voltage (1.8 V chip / 3.3 V FTDI sides), (4) lower `adapter speed`
(e.g. 50 or 10), (5) confirm JTAG really is on ADBUS / channel 0. A scope helps: TCK
should toggle and TDO should respond during the scan.

## Important: PASS here does NOT mean `halt` will work

The IDCODE is TCK-domain only. **Halting the hart and any memory access need the chip's
core clock running.** So the normal next step — the full `openocd.ft4232.tcl` doing
`init; halt` — can still fail with "unable to halt hart" *even though this probe
passed*. That is **not** a JTAG wiring problem; it means the **core clock / PLL isn't
enabled yet** (in simulation the clocks are switched on via SPI before the test — the
same must happen on real silicon). Bring up the clock before expecting the debug
module to work.

## Where this sits in the bring-up ladder

1. **`lagd-meas/testcases/jtag/01_idcode/openocd.scan.tcl`** (this test) → IDCODE `0x1c5e5db3`. *(JTAG electrical OK)*
2. **`lagd-meas/sw/jtag/openocd.ft4232.tcl`** → `init; halt` succeeds. *(debug module + clock OK)*
3. Load & run an ELF (telnet/tcl or GDB): `load_image`, set `pc = 0x80000000`,
   `resume`, then poll the EOC scratch at `0x03000008` (bit0 = done, code = value >> 1).

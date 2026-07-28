# UART loopback (host serial sanity) — OPTIONAL

> **Optional — not a chip test.** This rung is numbered `00` because it exercises the
> **host serial path only** and involves **no chip at all**. Run it only when you suspect
> the host cable/converter, or as a one-time sanity check before the real ladder. If the
> chip's UART already answers `01_portsweep`, you can skip this entirely. The actual chip
> bring-up ladder starts at `01_portsweep`.

It checks the **host serial path only** — the USB-to-UART converter (FT4232H UART
channel), `/dev/ttyUSB*`, cabling, and the 115200 8N1 port config — with **no chip
involved**. Passing it means any *later* UART failure is on the chip side, not the host.

## Purpose

With a **TX↔RX jumper** on the UART port, everything the host sends loops straight back.
`loopback.py` sends a 256-byte pattern and checks it comes back byte-for-byte. It reuses
`send_uart.py`'s `open_port` / `write_all` / `read_exact`, so it validates the **exact
serial setup the real loader uses**.

Think of it as a pre-check that proves the "cable" before blaming the chip. Unlike
`01_portsweep` (the UART analogue of JTAG `01_idcode`), this needs **no chip** — you can
run it as soon as the converter is plugged in, which is exactly why it is optional.

## Wiring

Jumper **TX ↔ RX** on the UART port (the FT4232H UART channel). That's it. Flow control
is **off** by default, because a plain TX↔RX jumper does not loop RTS/CTS — only pass
`--rtscts` if you have *also* jumpered RTS↔CTS.

## Prerequisites

- Python 3 (standard library only — no pyserial), with the repo root on `PYTHONPATH`
  (`source env.sh`).
- The USB-to-UART converter connected; the **UART channel** device known. This is the
  same device you'll pass to `send_uart.py` (the FT4232H UART channel = USB interface 2).
- No `ftdi_sio` unbinding needed here: the UART channel *is* a normal `/dev/ttyUSB*`
  (only the JTAG channel, interface 0, must be released for OpenOCD).

## How to run

```bash
cd lagd-meas/
source env.sh          # puts the repo root on PYTHONPATH; once per shell
python testcases/uart/00_loopback/loopback.py --device /dev/ttyUSB2
```

Options: `--baud` (default 115200), `--bytes` (default 256), `--timeout`,
`--rtscts` (only with an RTS↔CTS jumper too).

## Expected output — PASS

```
Loopback: /dev/ttyUSB2 @ 115200 8N1, RTS/CTS=off, 256 bytes
Requires a TX<->RX jumper on the port. No chip involved.
PASS: 256/256 bytes echoed back correctly. Host serial path is good.
```

Exits 0 on PASS, non-zero on FAIL.

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `FAIL: could not open ...` | Wrong device path, no permission, or converter not present. |
| `FAIL: did not receive the echo` (timeout) | **No loopback** — missing TX↔RX jumper, wrong device, TX or RX line broken, or (with `--rtscts`) CTS not asserted. |
| `FAIL: data mismatch at byte N` | Wrong baud, line noise, or a flow-control mismatch. |
| `PASS` | Host serial path is good — proceed to `01_portsweep` with the chip. |

## Where this sits in the UART ladder

0. **`lagd-meas/testcases/uart/00_loopback/loopback.py`** (this test) → host serial path OK. *(optional, no chip)*
1. `01_portsweep` → find the chip's UART and confirm the bootrom answers the handshake. *(chip powered, clocked, bootrom in passive boot)*
2. `02_handshake` → reach the bootrom UART debug server (ACK↔ACK) through the real loader.
3. `03_load_run` → load & run an ELF via `sw/uart/send_uart.py`. *(full UART data path)*

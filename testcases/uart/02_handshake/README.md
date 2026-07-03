# UART handshake (reach the bootrom)

Second UART bring-up test. It connects to the chip's **bootrom UART debug server** with
the ACK challenge — the chip's first sign of life over UART. Run it **after
`01_loopback` passes** (host serial path known good).

## Purpose

Send `0x06` (ACK) and expect `0x06` back. If the chip replies, its bootrom is up and
listening. This one rung implicitly validates a lot at once:

- the chip is **powered** and out of reset,
- the **core clock is running** — the UART baud is *derived* from it, so a wrong/absent
  clock ⇒ wrong baud ⇒ garbled bytes ⇒ no ACK,
- the **bootrom is executing in passive boot** (`boot_mode = 0`) and serving UART debug,
- TX/RX **wiring** is correct end-to-end.

It's the UART counterpart of JTAG `01_idcode` + `02_halt` combined: "the link is up and
the chip responds." No ELF is loaded and nothing is run.

## Key difference from JTAG

UART goes **through the bootrom**; JTAG bypasses it. So:

- UART needs **`boot_mode = 0` (passive)** and a working bootrom; JTAG does not care about
  boot mode.
- If UART fails here but JTAG (`testcases/jtag`) works, suspect the **bootrom / boot-mode
  straps / clock-derived baud**, *not* the UART wires (those were proven by `01_loopback`).

## Prerequisites

- **`01_loopback` passes** (remove the TX↔RX jumper first — you now talk to the chip).
- Chip powered, in **passive boot (`boot_mode 0`)**, with its **core clock running**.
- Correct UART device (FT4232H UART channel; same as `send_uart.py`).

## How to run

```bash
cd lagd-meas/testcases/uart/02_handshake
./run.sh                          # default device /dev/ttyUSB10
./run.sh --device /dev/ttyUSB2    # options pass through to send_uart.py
./run.sh --no-rtscts              # if RTS/CTS aren't wired
```

## Expected output — PASS

```
Port     : /dev/ttyUSB10 @ 115200 8N1, RTS/CTS=on
Handshake: sending ACK challenge ...
Handshake: chip responded -- bootrom UART debug server is up.
```

Exits 0 on PASS, non-zero on FAIL.

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `ERROR: cannot open ...` | Wrong device / permission (host issue — but `01_loopback` should have caught it). |
| `ERROR: no ACK from chip ...` (timeout) | Chip not responding: **not in passive boot**, **core clock/baud wrong**, bootrom not running, or (with RTS/CTS) CTS not asserted. |

Since `01_loopback` already proved the host serial path, a failure here points at the
**chip**: boot mode, clock/baud, or the bootrom — in that order.

## Where this sits in the UART ladder

1. `lagd-meas/testcases/uart/01_loopback/loopback.py` → host serial path OK. *(no chip)*
2. **`lagd-meas/testcases/uart/02_handshake/run.sh`** (this test) → bootrom UART debug server reachable (ACK↔ACK). *(chip powered, clocked, passive boot)*
3. `03_load_run` → load & run an ELF via `sw/uart/send_uart.py` (also `--no-exec --verify` for a memory check). *(full UART data path)*

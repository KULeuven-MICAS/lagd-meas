# UART bring-up testcases

Step-by-step bring-up ladder for the UART link to the LAGD / Cheshire chip, via the
on-board **FT4232H** UART channel. Run the rungs **in order** — each proves a new layer
and is a prerequisite for the next.

| # | Test | Proves | Needs chip? | On failure, suspect |
|---|------|--------|-------------|---------------------|
| 0 | [`00_loopback/`](00_loopback/) | Host serial path — device, 115200 8N1, converter, cabling | **No** (TX↔RX jumper) | wrong device, baud, or cabling |
| 1 | [`01_portsweep/`](01_portsweep/) | Chip's UART found + bootrom answers the `0x06` handshake | Yes | boot mode / clock-baud / wrong port |
| 2 | [`02_handshake/`](02_handshake/) | Chip reachable via the real loader — powered, **clocked (⇒ baud right)**, **bootrom in passive boot**, wiring | Yes | boot mode / clock-baud / bootrom |
| 3 | [`03_load_run/`](03_load_run/) | Full UART data path — load ELF, run, return code 0 | Yes | payload, or link corruption |
| 4 | [`04_memtest/`](04_memtest/) | Memory integrity + volume — pattern write/read-back over the link | Yes | stuck bits, addressing, flow control |

`00_loopback` is **optional** — it is a host-only cable check with no chip involved. The
real chip bring-up ladder starts at `01_portsweep`.

Each folder has its own README with expected output and failure modes.

## Quick run

```bash
source ../../env.sh                                        # repo root on PYTHONPATH (for 00 only)
cd 00_loopback   && ./loopback.py --device /dev/ttyUSB2    # OPTIONAL host sanity (jumper TX<->RX)
cd ../01_portsweep && ./portsweep.py --scan                # find the chip's UART, ping the bootrom
cd ../02_handshake && ./run.sh                             # reach the bootrom (ACK<->ACK)
cd ../03_load_run  && ./run.sh                             # load & run helloworld
cd ../04_memtest   && ./run.sh                             # memory integrity + volume
```

## Key difference from the JTAG ladder

UART goes **through the bootrom**; JTAG bypasses it. Consequences:

- UART needs **`boot_mode = 0` (passive)** and a working bootrom; JTAG does not care about
  boot mode.
- The UART baud is **derived from the core clock/RTC**, so a wrong clock garbles UART even
  when JTAG's IDCODE still reads fine.
- So if UART fails from rung 1 on but the JTAG ladder passes, suspect **boot mode / clock
  / bootrom**, not the UART wires (those are proven by the optional `00_loopback`).

## Diagnostics vs. tool

- **`00_loopback`** (optional) is a host-only diagnostic (imports `sw/uart/send_uart.py`'s
  port code to validate the exact serial setup the loader uses). It is the one rung you
  must `source env.sh` for yourself — it's run directly as `./loopback.py`.
- **`01_portsweep`** is a standalone probe run directly as `./portsweep.py` — it uses
  **pyserial** (`pip install pyserial`) rather than the loader, to scan every serial port
  and find which one the bootrom answers on. A successful ping is **one-shot** (it leaves
  the bootrom in `uart_debug_serve()`): press `CPU_RESET` before loading. See its README.
- **`02_handshake`, `03_load_run`, and `04_memtest`** are thin examples of the reusable
  loader in [`../../sw/uart/`](../../sw/uart/) (`send_uart.py`, via `--ping`, the full
  flow, and `--memtest`). That's the tool you use routinely; `sw/uart/selftest.py` is its
  offline unit test. Their `run.sh` wrappers source `env.sh` themselves and invoke the
  loader as a module (`python3 -m sw.uart.send_uart`), so they need no setup from you.

## Common prerequisites

- Python 3 (standard library only — no pyserial).
- The FT4232H connected; the **UART channel** device known (same one you pass to
  `send_uart.py`). The UART channel is a normal `/dev/ttyUSB*` — no `ftdi_sio` unbinding
  (that's only for the JTAG channel, interface 0).
- From rung 2 on: chip powered, **`boot_mode = 0` (passive)**, and the **core clock
  running**.

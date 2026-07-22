# UART port sweep (find the chip's UART, first contact with the bootrom)

First UART rung that **involves the chip**. It answers two questions at once:

1. **Which `/dev/ttyUSB*` is the chip's UART?** The USB-to-UART bridge enumerates as
   several ports (the FT4232H UART channel = interface 2; on a ZCU102 the CP2108 is a quad
   bridge — one cable, four ports). Only one of them is wired to the SoC.
2. **Is the bootrom alive and ready to load?** It sends the bootrom's UART debug
   handshake (`0x06` ACK) and checks for the `0x06` reply.

This is the UART counterpart of JTAG `01_idcode`: the first proof that the *chip* — not
just the host cable (that's `00_loopback`) — is answering.

## Why a dedicated probe

The bootrom **prints nothing** — there is no banner anywhere in `hw/bootrom`. In passive
boot (`boot_mode = 0`) it calls `uart_debug_init()` (115200 8N1) and then silently polls
for a single `0x06` byte; on receiving it, it replies `0x06` and enters
`uart_debug_serve()`. So a blank terminal is expected in **both** the healthy and the hung
case, and this handshake is the only way to tell them apart:

| Result | Meaning |
|--------|---------|
| replies `0x06` | `clint_get_core_freq()` returned — the RTC **is** ticking and the bootrom is in passive boot, ready to be loaded. |
| no reply | stuck in `clint_get_core_freq()` waiting for an `rtc_i` edge (no driver board / no on-FPGA RTC), **or** wrong serial port / wrong baud. |

The LEDs cannot distinguish these: with no RTC the board still shows `led_clk_locked_o`
solid and `led_heartbeat_o` blinking, because `soc_clk` is fine and the SoC is out of
reset. The hang is purely in software.

`portsweep.py` also **rejects loopback ports**: before the real handshake it sends a
non-opcode byte (`0x55`) that the bootrom is required to discard. A real bootrom stays
silent; a port with TX looped to RX hands the byte straight back and is reported as
`echo`, not a bootrom. Since the SoC has exactly one UART, more than one "hit" in a scan
is proof the naive check is being fooled.

## ⚠️ A successful ping is ONE-SHOT

A successful ping leaves the bootrom inside `uart_debug_serve()`, waiting for a command
opcode. `0x06` is **not** a valid opcode, so a second ping — or a loader run that starts
with its own handshake — hits the `default: return 1` arm and **kills the session**.

**After a successful ping, press `CPU_RESET` (AM13) to restart the bootrom before you load
anything.** Equally, do not point an interactive terminal (`screen`, `minicom`) at the
port while loading.

## Prerequisites

- Python 3 with **pyserial** (`pip install pyserial`). Unlike the rest of the ladder this
  probe uses pyserial directly; `--help` still works without it.
- The USB-to-UART bridge connected. The UART channel is a normal `/dev/ttyUSB*` — no
  `ftdi_sio` unbinding (that's only for the JTAG channel).
- Chip powered, **`boot_mode = 0` (passive)**, and the **core clock / RTC running** (else
  you get the "no reply" case above).

## How to run

```bash
cd lagd-meas/testcases/uart/01_portsweep/
./portsweep.py --scan            # probe every serial port, report which one answers
./portsweep.py /dev/ttyUSB2      # probe one known port
./portsweep.py /dev/ttyUSB2 -t 5 # longer reply timeout
```

Options: `-b/--baud` (default 115200, = `__BOOT_BAUDRATE`), `-t/--timeout` (default 2.0s).

## Expected output — PASS

```
PASS  /dev/ttyUSB2: bootrom replied ACK (0x06), and did not echo
```

or, with `--scan`:

```
Bootrom answered on: /dev/ttyUSB2
```

Exit codes: `0` bootrom answered, `1` silent / echo / >1 hit, `2` could not open the port.

## Failure modes and what they mean

| Symptom | Likely cause |
|---------|--------------|
| `silent` / no response | `rtc_i` not toggling → SoC stuck in `clint_get_core_freq()`; **or** wrong CP2108/FT4232H channel; **or** wrong baud; **or** the bootrom already exited (one-shot) — press `CPU_RESET` and retry. |
| `echo` (byte handed back) | That port is a **loopback**, not the SoC — try the other channels with `--scan`. A naive `0x06`-only test would wrongly call this a PASS. |
| `>1 port answered` | The SoC has exactly one UART, so this cannot be right — suspect a loopback that also passes the echo test, or crossed wiring. Investigate before loading. |
| `could not open ...` | Wrong device path, no permission, or the bridge is not present. |

## Where this sits in the UART ladder

0. `00_loopback/` → host serial path OK *(optional, no chip)*
1. **`01_portsweep/portsweep.py`** (this test) → chip's UART found, bootrom answers the
   handshake. *(chip powered, clocked, bootrom in passive boot)*
2. `02_handshake/` → reach the bootrom UART debug server through the real loader
   (`send_uart.py --ping`).
3. `03_load_run/` → load & run an ELF over the link.
4. `04_memtest/` → memory integrity + volume.
</content>
</invoke>

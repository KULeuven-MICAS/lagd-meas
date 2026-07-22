# UART ELF loader (LAGD / Cheshire SoC)

Loads and runs an ELF on the chip over UART, using the Cheshire bootrom's
**UART debug protocol** (passive boot, `boot_mode 0`). Link layer is **115200 8N1**.

> The Cheshire bootrom does not speak XMODEM — hence a custom loader.

## Files

| File | Purpose |
|------|---------|
| `send_uart.py` | The driver (Python stdlib only — **no pyserial needed**). |
| `selftest.py`  | Offline end-to-end test with a mock chip — **no hardware**. |

## Quick start

```bash
# simplest run (executable, has a shebang)
./send_uart.py ../inputs/helloworld.spm.elf

# with options
./send_uart.py ../inputs/helloworld.spm.elf --device /dev/ttyUSB2 --verify

# equivalent explicit-interpreter form
python3 send_uart.py ../inputs/helloworld.spm.elf

# connectivity check only: ACK handshake with the bootrom, no ELF loaded
./send_uart.py --ping

# memory integrity + volume test (no ELF) (mem size in bit)
./send_uart.py --memtest --mem-size 0x10000
```

## Useful flags (`send_uart.py`)

| Flag | Default | What it does |
|------|---------|--------------|
| `elf` (positional) | — | Path to the ELF to load. Optional only with `--ping`. |
| `--ping` | off | Do only the ACK handshake with the bootrom, then exit (connectivity check; no ELF needed). |
| `--memtest` | off | Write/read-back a memory region with patterns (integrity + volume), then exit. No ELF. |
| `--mem-base` | `0x80000000` | Memtest region base address (with `--memtest`). |
| `--mem-size` | `0x2000` | Memtest region size in bytes (with `--memtest`); larger = more flow-control stress. |
| `-d`, `--device` | `/dev/ttyUSB2` | Serial device node. |
| `-b`, `--baud` | `115200` | Baud rate. **Must match the chip** (`__BOOT_BAUDRATE`). |
| `--no-rtscts` | (RTS/CTS on) | Disable hardware flow control. Use if RTS/CTS aren't wired. |
| `--chunk N` | `1024` | Max bytes per WRITE command (no chip-side limit; cosmetic/progress). |
| `--verify` | off | Read each segment back over UART and compare (poor-man's checksum). |
| `--no-exec` | (exec on) | Load only; don't send EXEC. |
| `--no-wait` | (wait on) | Send EXEC but don't wait for EOC / return code. |
| `--timeout S` | `5` | Per-command response timeout (s). |
| `--run-timeout S` | `60` | Wait for EOC after EXEC; `0` = forever. |
| `--connect-timeout S` | `10` | Wait for the initial ACK handshake (s). |

## Protocol (for reference)

All multi-byte fields are **64-bit little-endian**. Host is master; chip is server.

```
ACK challenge :  host -> 06 ;  chip -> 06
WRITE  (0x12) :  12 | addr:u64 | len:u64 | <-06 | data... | <-04(EOT)
READ   (0x11) :  11 | addr:u64 | len:u64 | <-06 | data...  | <-04(EOT)
EXEC   (0x13) :  13 | entry:u64 | <-06 ;  chip jumps to entry
EOC    (0x14) :  chip -> 14 | ret:u32          (sent when the program returns)
```

Order: handshake → WRITE all segments → (optional READ verify) → EXEC → wait EOC.
READ only works **before** EXEC (the debug server exits once the program runs).

## Verifying WITHOUT physical hardware

Run the self-test. It spins up a virtual serial port (pty), runs a mock of the
bootrom debug server on one end, and the **real** `send_uart.py` on the other:

```bash
source ../../env.sh                         # repo root on PYTHONPATH; once per shell
python3 selftest.py                         # uses helloworld.spm.elf
python3 selftest.py path/to/other.elf       # test a different ELF
```

Expected tail:
```
RESULT: PASS  (handshake, WRITE, READ-back verify, EXEC all OK)
```

It checks the full path end-to-end: handshake, every ELF byte landing at the right
address, read-back verify, the EXEC entry point, and a clean exit on return code 0.

Other no-hardware checks:
```bash
python3 -c "from sw.uart.send_uart import parse_elf; print(hex(parse_elf('../inputs/helloworld.spm.elf')[0]))"  # entry point (needs env.sh)
python3 send_uart.py app.elf --device /dev/pts/<n>   # against a socat/pty pair, if you prefer
```

## Bench checklist (real hardware)

Things the simulator can't tell you — confirm these on the bench:

1. **Boot mode** = passive (`boot_mode 0`); the chip must be sitting in the UART
   debug loop when you start. If the handshake hangs, check this first.
2. **RTS/CTS**: the chip enables auto-flow. Either wire RTS/CTS and keep flow control
   on (default), or pass `--no-rtscts` (and keep the chip's CTS in the clear state).
3. **Baud = 115200** on both ends.
4. **RTC** running at ~32.768 kHz and matching the firmware `RtcFreq`, or the chip's
   computed baud drifts off 115200 and bytes garble.

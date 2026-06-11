#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Created by Claude on 2025-06
#
# UART loader for the LAGD / Cheshire SoC.
#
# This speaks the Cheshire bootrom's UART debug protocol (passive boot, boot_mode 0):
#   - ACK challenge   : host -> 0x06 , chip -> 0x06
#   - WRITE  (0x12)   : 0x12 | addr:u64le | len:u64le | <-ACK | data... | <-EOT
#   - READ   (0x11)   : 0x11 | addr:u64le | len:u64le | <-ACK | data...  | <-EOT
#   - EXEC   (0x13)   : 0x13 | entry:u64le | <-ACK ; chip jumps to entry
#   - EOC    (0x14)   : chip -> 0x14 | ret:u32le   (sent when the program returns)
# All multi-byte fields are 64-bit little-endian. Link layer is 115200 8N1.
#
# NOTE: The Cheshire bootrom does not speak XMODEM, so
# a custom loader is required.
#
# Implemented with the Python stdlib only (termios)

import argparse
import os
import select
import struct
import sys
import termios
import time

# --- Protocol opcodes (cheshire sw/lib/hal/uart_debug.c) ---------------------
ACK = 0x06
EOT = 0x04
EOC = 0x14
CMD_READ = 0x11
CMD_WRITE = 0x12
CMD_EXEC = 0x13


class ProtoError(RuntimeError):
    pass


# --- Serial port (raw, via termios) ------------------------------------------

def open_port(device, baud, rtscts):
    fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        speed = getattr(termios, f"B{baud}")
    except AttributeError:
        os.close(fd)
        raise SystemExit(f"Unsupported baud rate: {baud}")

    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)

    # Raw mode: no input/output processing, no canonical mode, no echo/signals.
    iflag = 0                                   # -ignbrk -brkint -icrnl -ixon ...
    oflag = 0                                   # -opost
    lflag = 0                                   # -icanon -echo -isig -iexten
    # 8 data bits, no parity, 1 stop bit (8N1); enable receiver; ignore modem
    # control lines for open(), but still honour CRTSCTS for flow control.
    cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
    if rtscts:
        cflag |= termios.CRTSCTS
    ispeed = ospeed = speed
    cc = list(cc)
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = 0

    termios.tcsetattr(fd, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def write_all(fd, data):
    mv = memoryview(bytes(data))
    while len(mv):
        try:
            n = os.write(fd, mv)
            mv = mv[n:]
        except BlockingIOError:
            # Output buffer full (e.g. CTS deasserted under RTS/CTS flow control).
            select.select([], [fd], [], 5.0)
    termios.tcdrain(fd)


def read_exact(fd, n, timeout):
    buf = bytearray()
    deadline = time.monotonic() + timeout
    while len(buf) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProtoError(f"timeout: wanted {n} byte(s), got {len(buf)} "
                             f"({bytes(buf).hex()})")
        r, _, _ = select.select([fd], [], [], remaining)
        if r:
            chunk = os.read(fd, n - len(buf))
            if chunk:
                buf += chunk
    return bytes(buf)


def expect(fd, byte, timeout, what):
    got = read_exact(fd, 1, timeout)[0]
    if got != byte:
        raise ProtoError(f"expected {what} (0x{byte:02x}), received 0x{got:02x}")


# --- Protocol operations -----------------------------------------------------

def handshake(fd, total_timeout, resend_interval=0.5):
    """Send the ACK challenge until the chip echoes ACK back.

    The bootrom passive loop consumes (and discards) any non-ACK byte, then enters
    the debug server on the first ACK it sees. We therefore send ONE ACK at a time
    and stop the instant we get the reply, so a stray ACK isn't later parsed as a
    (bogus) command. Console noise that isn't ACK is ignored while we wait.
    """
    termios.tcflush(fd, termios.TCIFLUSH)
    deadline = time.monotonic() + total_timeout
    next_send = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_send:
            write_all(fd, bytes([ACK]))
            next_send = now + resend_interval
        wait = min(next_send, deadline) - time.monotonic()
        if wait <= 0:
            continue
        r, _, _ = select.select([fd], [], [], wait)
        if r:
            b = os.read(fd, 1)
            if b and b[0] == ACK:
                return
            # else: boot/console noise -- keep waiting
    raise ProtoError("no ACK from chip. Is it powered, in passive boot (boot_mode 0) "
                     "and sitting in the UART debug loop? Check baud/wiring/flow-control.")


def cmd_write(fd, addr, data, timeout):
    hdr = struct.pack("<BQQ", CMD_WRITE, addr, len(data))
    write_all(fd, hdr)
    expect(fd, ACK, timeout, "ACK")
    write_all(fd, data)
    expect(fd, EOT, timeout, "EOT")


def cmd_read(fd, addr, length, timeout):
    hdr = struct.pack("<BQQ", CMD_READ, addr, length)
    write_all(fd, hdr)
    expect(fd, ACK, timeout, "ACK")
    data = read_exact(fd, length, timeout)
    expect(fd, EOT, timeout, "EOT")
    return data


def cmd_exec(fd, entry, timeout):
    write_all(fd, struct.pack("<BQ", CMD_EXEC, entry))
    expect(fd, ACK, timeout, "ACK")


def wait_for_eoc(fd, timeout):
    """Stream the program's console output until EOC, then read the u32 return code.

    Same demux as the sim VIP: bytes are console text until a 0x14 (EOC) arrives,
    after which the next 4 bytes are the little-endian return code.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    line = bytearray()
    while True:
        remaining = 86400.0 if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            raise ProtoError("timeout waiting for EOC")
        b = read_exact(fd, 1, remaining)[0]
        if b == EOC:
            ret = read_exact(fd, 4, 5.0)
            if line:
                sys.stdout.write("[chip] " + line.decode("latin1") + "\n")
            return struct.unpack("<I", ret)[0]
        elif b == 0x0A:  # \n
            sys.stdout.write("[chip] " + line.decode("latin1") + "\n")
            sys.stdout.flush()
            line = bytearray()
        elif b == 0x0D:  # \r -- ignore
            pass
        else:
            line.append(b)


# --- ELF parsing (ELF64 little-endian, stdlib only) --------------------------

def parse_elf(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"\x7fELF":
        raise SystemExit(f"{path} is not an ELF file")
    if data[4] != 2:   # EI_CLASS == ELFCLASS64
        raise SystemExit("only ELF64 is supported")
    if data[5] != 1:   # EI_DATA == ELFDATA2LSB
        raise SystemExit("only little-endian ELF is supported")

    e_entry = struct.unpack_from("<Q", data, 24)[0]
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]

    segments = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        if p_type != 1:        # PT_LOAD
            continue
        p_offset = struct.unpack_from("<Q", data, off + 8)[0]
        p_paddr = struct.unpack_from("<Q", data, off + 24)[0]
        p_filesz = struct.unpack_from("<Q", data, off + 32)[0]
        # Only the file-backed bytes are sent; any [filesz, memsz) tail is .bss,
        # which crt0 zeroes on the chip at startup.
        if p_filesz:
            segments.append((p_paddr, data[p_offset:p_offset + p_filesz]))
    if not segments:
        raise SystemExit(f"no loadable (PT_LOAD) segments found in {path}")
    return e_entry, segments


# --- Main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Load and run an ELF on the LAGD/Cheshire SoC over UART "
                    "(passive boot debug protocol).")
    ap.add_argument("elf", help="path to the ELF to load (e.g. helloworld.spm.elf)")
    ap.add_argument("-d", "--device", default="/dev/ttyUSB10",
                    help="serial device (default: /dev/ttyUSB10)")
    ap.add_argument("-b", "--baud", type=int, default=115200,
                    help="baud rate (default: 115200 -- must match the chip)")
    ap.add_argument("--no-rtscts", dest="rtscts", action="store_false",
                    help="disable hardware RTS/CTS flow control (default: enabled)")
    ap.add_argument("--chunk", type=int, default=1024,
                    help="max bytes per WRITE command (default: 1024)")
    ap.add_argument("--verify", action="store_true",
                    help="read each segment back over UART and compare")
    ap.add_argument("--no-exec", dest="do_exec", action="store_false",
                    help="load only, do not send EXEC")
    ap.add_argument("--no-wait", dest="wait", action="store_false",
                    help="send EXEC but do not wait for EOC / return code")
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="per-command response timeout in seconds (default: 5)")
    ap.add_argument("--run-timeout", type=float, default=60.0,
                    help="seconds to wait for EOC after EXEC; 0 = forever (default: 60)")
    ap.add_argument("--connect-timeout", type=float, default=10.0,
                    help="seconds to wait for the initial ACK handshake (default: 10)")
    args = ap.parse_args()

    entry, segments = parse_elf(args.elf)
    total = sum(len(b) for _, b in segments)
    print(f"ELF      : {args.elf}")
    print(f"Entry    : 0x{entry:016x}")
    print(f"Segments : {len(segments)}, {total} bytes total")
    for paddr, blob in segments:
        print(f"  0x{paddr:016x}  {len(blob)} bytes")

    print(f"Port     : {args.device} @ {args.baud} 8N1, "
          f"RTS/CTS={'on' if args.rtscts else 'off'}")

    fd = open_port(args.device, args.baud, args.rtscts)
    try:
        print("Handshake: sending ACK challenge ...")
        handshake(fd, args.connect_timeout)
        print("Handshake: chip responded, debug server is up.")

        for paddr, blob in segments:
            for i in range(0, len(blob), args.chunk):
                chunk = blob[i:i + args.chunk]
                cmd_write(fd, paddr + i, chunk, args.timeout)
            print(f"Loaded   : 0x{paddr:016x} ({len(blob)} bytes)")
            if args.verify:
                rb = cmd_read(fd, paddr, len(blob), args.timeout)
                if rb != blob:
                    raise ProtoError(f"verify FAILED at 0x{paddr:016x}")
                print(f"Verified : 0x{paddr:016x} OK")

        if not args.do_exec:
            print("Done (load only, --no-exec).")
            return 0

        cmd_exec(fd, entry, args.timeout)
        print(f"Exec     : jumped to 0x{entry:016x}")

        if not args.wait:
            print("Done (--no-wait).")
            return 0

        rt = None if args.run_timeout == 0 else args.run_timeout
        ret = wait_for_eoc(fd, rt)
        print(f"EOC      : return code {ret}")
        return 0 if ret == 0 else 2
    except ProtoError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())

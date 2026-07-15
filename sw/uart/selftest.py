#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Created by Claude on 2025-06
#
# Offline self-test for send_uart.py -- NO physical hardware required.
#
# It creates a virtual serial port (pty pair), runs a small mock of the Cheshire
# bootrom UART debug server on one end, and runs the *real* send_uart.py against
# the other end. It then checks that:
#   - the handshake completed,
#   - every ELF byte arrived at the right address (WRITE),
#   - read-back (--verify / READ) worked,
#   - EXEC carried the correct entry point,
#   - the driver exited 0 on EOC return code 0.
#
# Usage:  source ../../env.sh                  # repo root on PYTHONPATH; once per shell
#         python3 selftest.py [path/to/file.elf]

import os
import pty
import struct
import subprocess
import sys
import threading
import tty
from pathlib import Path

from sw.uart.send_uart import parse_elf

ACK, EOT, EOC = 0x06, 0x04, 0x14
CMD_READ, CMD_WRITE, CMD_EXEC = 0x11, 0x12, 0x13

# Still needed for on-disk paths (the default ELF, and running the driver as a
# subprocess) -- env.sh only covers imports.
HERE = Path(__file__).resolve().parent
DEFAULT_ELF = HERE / "../inputs/helloworld.spm.elf"


def readn(fd, n):
    buf = b""
    while len(buf) < n:
        c = os.read(fd, n - len(buf))
        if not c:
            raise EOFError
        buf += c
    return buf


def mock_chip(fd, mem, result):
    """Emulate the bootrom passive loop + uart_debug_serve on `fd`."""
    try:
        # Passive loop: the real bootrom discards non-ACK bytes until it sees ACK.
        while readn(fd, 1)[0] != ACK:
            pass
        os.write(fd, bytes([ACK]))                       # serve() opens with ACK
        while True:
            cmd = readn(fd, 1)[0]
            if cmd == CMD_WRITE:
                addr, ln = struct.unpack("<QQ", readn(fd, 16))
                os.write(fd, bytes([ACK]))
                data = readn(fd, ln)
                for i, b in enumerate(data):
                    mem[addr + i] = b
                os.write(fd, bytes([EOT]))
            elif cmd == CMD_READ:
                addr, ln = struct.unpack("<QQ", readn(fd, 16))
                os.write(fd, bytes([ACK]))
                os.write(fd, bytes(mem.get(addr + i, 0) for i in range(ln)))
                os.write(fd, bytes([EOT]))
            elif cmd == CMD_EXEC:
                (entry,) = struct.unpack("<Q", readn(fd, 8))
                os.write(fd, bytes([ACK]))
                result["entry"] = entry
                os.write(fd, b"mock chip says hello\n")   # emulated console output
                os.write(fd, bytes([EOC]) + struct.pack("<I", 0))  # return code 0
                result["ok"] = True
                return
            else:
                result["error"] = f"unexpected command 0x{cmd:02x}"
                return
    except (EOFError, OSError) as e:
        result.setdefault("error", f"mock I/O ended: {e}")


def main():
    elf = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ELF
    entry, segs = parse_elf(elf)

    master, slave = pty.openpty()
    tty.setraw(master)
    tty.setraw(slave)
    dev = os.ttyname(slave)

    mem, result = {}, {}
    t = threading.Thread(target=mock_chip, args=(master, mem, result), daemon=True)
    t.start()

    print(f"=== self-test: running send_uart.py against mock chip on {dev} ===")
    try:
        proc = subprocess.run(
            [sys.executable, str(HERE / "send_uart.py"), str(elf),
             "--device", dev, "--no-rtscts", "--verify", "--run-timeout", "10"],
            timeout=30)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        print("FAIL: driver timed out")
        return 1
    finally:
        t.join(timeout=5)

    # --- checks ---
    fails = []
    if rc != 0:
        fails.append(f"driver exit code = {rc} (expected 0)")
    if not result.get("ok"):
        fails.append(f"mock did not reach EXEC/EOC (error: {result.get('error')})")
    if result.get("entry") != entry:
        fails.append(f"EXEC entry 0x{result.get('entry', 0):x} != ELF entry 0x{entry:x}")
    nbytes = 0
    for addr, blob in segs:
        for i, b in enumerate(blob):
            if mem.get(addr + i) != b:
                fails.append(f"byte mismatch at 0x{addr + i:x}")
                break
        nbytes += len(blob)

    print("--- checks ---")
    print(f"  driver exit code : {rc}")
    print(f"  bytes received   : {len(mem)} / {nbytes}")
    print(f"  exec entry       : 0x{result.get('entry', 0):016x}")
    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("RESULT: PASS  (handshake, WRITE, READ-back verify, EXEC all OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

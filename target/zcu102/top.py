#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Top-level bring-up entry point. Two stages:
#   1. Reload the ZCU102 (via zcu102_reload) to program the bitstream and reset the
#      chip. Optionally upload a bitstream during the reload (--bit).
#   2. On the measurement host, load & run an ELF on the chip over UART.
#
# Hosts, remote directories and the UART device differ per user; they live in
# config.ini / config.local.ini (see lab_config.py), not in this file. 
#
# Usage:
#   ./top.py                                        # default ELF and host
#   ./top.py --elf sw/inputs/lagd_scompute.spm.elf  # run a specific ELF (path on the measurement host)
#   ./top.py --host root@1.2.3.4                     # override the measurement host
#   ./top.py --bit path/to.bit                       # also upload a bitstream during the reload
#
# Any unrecognised arguments are forwarded verbatim to `send_uart` on the
# measurement host, e.g.:
#   ./top.py --rtscts            # keep hardware flow control (drops the default --no-rtscts)
#   ./top.py --baudrate 921600   # whatever send_uart accepts

import argparse
import logging
import shlex
import subprocess
import sys

import lab_config
import target.zcu102.zcu102_reload as zcu102_reload

logger = logging.getLogger(__name__)

DEFAULT_ELF = "sw/inputs/helloworld.spm.elf"

# Defaults come from config.ini / config.local.ini -- see lab_config.py.
DEFAULT_HOST = lab_config.get("measurement-host", "host")
DEFAULT_REMOTE_DIR = lab_config.get("measurement-host", "remote_dir")
DEFAULT_DEVICE = lab_config.get("measurement-host", "device")
REMOTE_PYTHON = lab_config.get("measurement-host", "python")


def run_elf(host, remote_dir, elf, device, extra_args, stdout=sys.stdout):
    """Load & run an ELF on the chip over UART from the measurement host."""
    tokens = [
        REMOTE_PYTHON, "-m", "sw.uart.send_uart", elf,
        "--device", device,
        *extra_args,
    ]
    remote_cmd = f"cd {shlex.quote(remote_dir)}/ && " + " ".join(shlex.quote(t) for t in tokens)
    subprocess.run(["ssh", "-t", host, remote_cmd], stdout=stdout, check=True)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Reload the ZCU102, then load & run an ELF on the chip over UART.",
        epilog="Unrecognised arguments are forwarded to send_uart on the measurement host.",
    )
    # Stage 2 (ELF over UART on the measurement host).
    parser.add_argument(
        "--elf", default=DEFAULT_ELF,
        help=f"ELF to run (path on the measurement host; default: {DEFAULT_ELF})",
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help=f"measurement host, user@ip (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--remote-dir", default=DEFAULT_REMOTE_DIR,
        help=f"repo directory on the measurement host (default: {DEFAULT_REMOTE_DIR})",
    )
    parser.add_argument(
        "--device", default=DEFAULT_DEVICE,
        help=f"UART device on the measurement host (default: {DEFAULT_DEVICE})",
    )
    parser.add_argument(
        "--rtscts", action="store_true",
        help="keep hardware flow control (by default --no-rtscts is passed to send_uart)",
    )
    # Stage 1 (ZCU102 reload).
    parser.add_argument(
        "--reload-host", default=zcu102_reload.DEFAULT_HOST,
        help=f"ZCU102 SSH target for the reload (default: {zcu102_reload.DEFAULT_HOST})",
    )
    parser.add_argument(
        "--bit", default=None,
        help="local bitstream to upload to the ZCU102 during the reload",
    )
    return parser


def main(argv=None):
    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)

    uart_args = list(extra)
    if not args.rtscts:
        uart_args.append("--no-rtscts")

    try:
        # Stage 1: (re)program the ZCU102 and reset the chip.
        zcu102_reload.reload_board(host=args.reload_host, bit=args.bit)
        # Stage 2: load & run the ELF on the chip over UART.
        run_elf(args.host, args.remote_dir, args.elf, args.device, uart_args)
    except FileNotFoundError as err:
        logger.error("%s", err)
        return 1
    except subprocess.CalledProcessError as err:
        logger.error("command failed (exit %s): %s", err.returncode, err.cmd)
        return err.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())

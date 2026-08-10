#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Reload and run the LAGD v1 notebook on the ZCU102 board over SSH.
#
# Optionally uploads a local bitstream to <remote-dir>/lagd.zcu102.bit first, then
# (re)runs the PYNQ notebook, which programs the PL and resets the chip.
#
# The board's SSH target and notebook directory live in config.ini /
# config.local.ini (see lab_config.py).
#
# Usage:
#   ./zcu102_reload.py                       # just reload & run the notebook
#   ./zcu102_reload.py --bit path/to.bit     # upload a bitstream first, then reload & run
#   ./zcu102_reload.py --host xilinx@1.2.3.4  # target a different board

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import lab_config

logger = logging.getLogger(__name__)

# Defaults come from config.ini / config.local.ini -- see lab_config.py.
DEFAULT_HOST = lab_config.get("zcu102", "host")
DEFAULT_REMOTE_DIR = lab_config.get("zcu102", "remote_dir")
REMOTE_BIT_NAME = "lagd.zcu102.bit"
NOTEBOOK = "lagd_v1_notebook.py"
PYNQ_PYTHON = "/usr/local/share/pynq-venv/bin/python"


def reload_board(host=DEFAULT_HOST, remote_dir=DEFAULT_REMOTE_DIR, bit=None):
    """Upload an optional bitstream, then run the PYNQ notebook on the board.

    Raises FileNotFoundError if `bit` is given but does not exist, and
    subprocess.CalledProcessError if scp/ssh fail.
    """
    if bit is not None:
        local_bit = Path(bit)
        if not local_bit.is_file():
            raise FileNotFoundError(f"bitstream file not found: {local_bit}")
        remote_bit = f"{remote_dir}/{REMOTE_BIT_NAME}"
        logger.info("Uploading %s -> %s:%s", local_bit, host, remote_bit)
        subprocess.run(["scp", str(local_bit), f"{host}:{remote_bit}"], check=True)

    remote_cmd = (
        f"source /etc/profile && cd {remote_dir}/ && "
        f"sudo -E {PYNQ_PYTHON} {NOTEBOOK}"
    )
    subprocess.run(["ssh", "-t", host, remote_cmd], check=True)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Reload and run the LAGD v1 notebook on the ZCU102 over SSH."
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help=f"ZCU102 SSH target, user@ip (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--remote-dir", default=DEFAULT_REMOTE_DIR,
        help=f"notebook directory on the board (default: {DEFAULT_REMOTE_DIR})",
    )
    parser.add_argument(
        "--bit", default=None,
        help=f"local bitstream to upload to <remote-dir>/{REMOTE_BIT_NAME} before reloading",
    )
    return parser


def main(argv=None):
    logging_level = logging.INFO
    logging_format = "%(asctime)s - %(filename)s - %(funcName)s +%(lineno)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging_level, format=logging_format, stream=sys.stdout)
    args = build_parser().parse_args(argv)
    try:
        reload_board(host=args.host, remote_dir=args.remote_dir, bit=args.bit)
    except FileNotFoundError as err:
        logger.error("%s", err)
        return 1
    except subprocess.CalledProcessError as err:
        logger.error("command failed (exit %s): %s", err.returncode, err.cmd)
        return err.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())

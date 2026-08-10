#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Per-user lab settings (SSH targets, remote workspace directories, UART device).
# These differ from person to person and from bench to bench, so they must not be
# hard-coded in the scripts.
#
# A setting is resolved in this order, first hit wins:
#   1. the CLI flag of the script you are running (--host, --remote-dir, ...)
#   2. lagd-meas/config.local.ini   (gitignored -- yours, not tracked)
#   3. lagd-meas/config.ini         (tracked -- shared defaults)
#
# First-time setup, once per user:
#   cp config.ini config.local.ini   # then edit the few lines that are yours
#
# Usage from a script:
#   import lab_config
#   DEFAULT_HOST = lab_config.get("measurement-host", "host")

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SHARED_CONFIG = REPO_ROOT / "config.ini"
LOCAL_CONFIG = REPO_ROOT / "config.local.ini"

# Read the shared file first, then the local one on top: later values win.
_parser = configparser.ConfigParser()
_parser.read([str(SHARED_CONFIG), str(LOCAL_CONFIG)])


def get(section, option, fallback=None):
    """Return a lab setting, or `fallback` if it is set in neither config file."""
    value = _parser.get(section, option, fallback=fallback)
    if value is None:
        raise KeyError(
            f"missing setting [{section}] {option} -- add it to {LOCAL_CONFIG} "
            f"(or to the shared {SHARED_CONFIG})"
        )
    return value

#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Description: Source this before running scripts under sw/:
#
#     source env.sh                 # or:  . env.sh
#
# Adds sw/ to PYTHONPATH so `from lib...` / `from tools...` resolve in plain
# script mode (`python tests/perip_test.py`) from any cwd

# Directory this file lives in = the sw/ root (works when sourced from any cwd).
_sw_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prepend sw/ to PYTHONPATH, but only once (safe to re-source).
case ":${PYTHONPATH:-}:" in
  *":$_sw_dir:"*) ;;                                       # already present
  *) export PYTHONPATH="$_sw_dir${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

echo "sw/ on PYTHONPATH -> $_sw_dir"
unset _sw_dir

#!/bin/bash

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Description: Source this once per shell, before running any Python script in
# this repo (scripts under sw/ as well as testcases/):
#
#     source env.sh                 # or:  . env.sh
#
# Adds the repo root (lagd-meas/) to PYTHONPATH so `from sw.lib...` /
# `from sw.uart...` resolve in plain script mode (`python sw/tests/perip_test.py`)
# from any cwd. Self-locating: the same file works on every server / mount path
# with no edits.

# Directory this file lives in = the repo root (works when sourced from any cwd).
_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prepend the repo root to PYTHONPATH, but only once (safe to re-source).
case ":${PYTHONPATH:-}:" in
  *":$_repo_root:"*) ;;                                    # already present
  *) export PYTHONPATH="$_repo_root${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

echo "repo root on PYTHONPATH -> $_repo_root"
unset _repo_root

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

export TOP_MEAS=$(git rev-parse --show-toplevel)
export TOP_ISING=$TOP_MEAS/submodules/openising
export TOP_LAGD_IM=$TOP_MEAS/submodules/lagd-im

echo "repo root on PYTHONPATH -> $_repo_root"

# Activate a Python environment. The FPGA lab machines have a prebuilt 3.6 env
# at /opt/pyvisa-env; the general-purpose servers do not, and there this file
# used to end up doing nothing at all silently. Fall back to the uv-managed
# .venv, and say so either way rather than leaving the shell unchanged.
if [ -f /opt/pyvisa-env/bin/activate ]; then
  source /opt/pyvisa-env/bin/activate
  echo "python env -> /opt/pyvisa-env (lab machine)"
elif [ -f "$_repo_root/.venv/bin/activate" ]; then
  source "$_repo_root/.venv/bin/activate"
  echo "python env -> $_repo_root/.venv (uv)"
else
  echo "WARNING: no python env found."
  echo "         /opt/pyvisa-env is absent (not an FPGA lab machine) and there"
  echo "         is no .venv yet -- create one with:  uv sync"
fi

unset _repo_root

#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Toon Bettens <toon.bettens@kuleuven.be>
#
# Sweep logs -> two tidy CSVs, for handing the measurements to someone who should not have to
# know what a [chip] prefix is.
#
# Usage: uv run --python 3.14 sw/tools/export_sweep.py

import csv
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_ising_problem as gen           # noqa: E402  -- for load_model and the checksum

EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"

# ---------------------------------------------------------------------------
# 1. Collect data
# ---------------------------------------------------------------------------

PROBLEMS = ["pm1d_100", "pm1s_100", "pm1d_80_0", "pm1s_80_0"]
SWEEP = "sweep_8"                     # subfolder holding runs/
OUT = EXPERIMENTS / "export"
CORE_FREQ_HZ = 512e6
MAGNITUDES = range(1, 8)              # candidates to identify; |J| <= 7 caps it at 7


def detect_magnitude(problem, checksum):
    """Which magnitude produces the J the chip actually ran?

    Every log prints the checksum of the loaded J, and the generator computes that same
    checksum from the scaled, padded, mirrored matrix -- so the magnitude is recoverable
    rather than something to remember. Cut and energy are both wrong if it is wrong.
    """
    for magnitude in MAGNITUDES:
        j_int, _, _, _ = gen.quantise(gen.load_model(problem, magnitude), gen.zeros)
        j_pad = gen._pad_matrix(j_int)
        if gen.MIRROR_TO_LOW_SPINS:
            j_pad = j_pad[::-1, ::-1]
        if gen.j_checksum(j_pad) == checksum:
            return magnitude
    return None


CHECKSUM = re.compile(r"checksum 0x([0-9a-f]+)")

TAG = re.compile(r"^\s*\[[a-z]+\]\s?")
#     3 |        4 |     -615 | fe19...     ("in" is the pre-run state, cycle 0)
ROW = re.compile(r"^\s*(in|\d+)\s*\|\s*(\d+)\s*\|\s*(-?\d+)\s*\|")

rows, meta = [], []
for problem in PROBLEMS:
    info = {}
    for line in (EXPERIMENTS / problem / "info").read_text().splitlines():
        if ":" in line and not line.startswith("note"):
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()

    # Everything leaves this script at magnitude 1: energies are divided by it below, so the
    # cut is the plain MAX-CUT relation on unscaled weights, cut = (W - E) / 2.
    logs = sorted((EXPERIMENTS / problem / SWEEP / "runs").glob("*.log"))
    if not logs:
        sys.exit(f"{problem}/{SWEEP}/runs: no logs")
    first = TAG.sub("", logs[0].read_text(errors="replace"))
    found = CHECKSUM.search(first)
    if not found:
        sys.exit(f"{logs[0]}: no J checksum line to identify the magnitude from")
    magnitude = detect_magnitude(problem, int(found.group(1), 16))
    if magnitude is None:
        sys.exit(f"{problem}: J checksum 0x{found.group(1)} matches no magnitude in "
                 f"{list(MAGNITUDES)} -- the logs were not run on this model file")

    weight = float(info["total_weight"])

    def cut(energy):
        return (weight - energy) / 2

    n_before = len(rows)
    for log in logs:
        run = int(log.stem)
        for line in log.read_text(errors="replace").splitlines():
            m = ROW.match(TAG.sub("", line))
            if not m:
                continue
            cycle, measured = int(m.group(2)), int(m.group(3))
            if measured % magnitude:
                sys.exit(f"{log.name}: energy {measured} is not divisible by magnitude "
                         f"{magnitude} -- it cannot be an exact scaling of a magnitude-1 problem")
            energy = measured // magnitude
            rows.append({"problem": problem, "run": run, "cycle": cycle,
                         "time_ns": round(cycle / CORE_FREQ_HZ * 1e9, 4),
                         "energy": energy, "cut": cut(energy)})

    meta.append({"problem": problem,
                 "spins": info.get("spins", ""),
                 "runs": len(logs),
                 "ran_at_magnitude": magnitude,
                 "total_weight": info.get("total_weight", ""),
                 "optimum_cut": info.get("optimum_cut", ""),
                 "optimum_energy": int(float(info["optimum_energy"]))
                 if "optimum_energy" in info else "",
                 "core_freq_hz": int(CORE_FREQ_HZ),
                 "source": info.get("source", "")})
    print(f"  {problem:<11} magnitude {magnitude} (from J checksum), {len(logs):>4} runs, "
          f"{len(rows) - n_before:>7} samples")

# ---------------------------------------------------------------------------
# 2. Write it out
# ---------------------------------------------------------------------------

OUT.mkdir(parents=True, exist_ok=True)
samples = OUT / f"{SWEEP}_samples.csv"
problems = OUT / f"{SWEEP}_problems.csv"

with samples.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["problem", "run", "cycle", "time_ns", "energy", "cut"])
    w.writeheader()
    w.writerows(rows)
with problems.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(meta[0]))
    w.writeheader()
    w.writerows(meta)

print(f"\n{samples}  ({len(rows)} rows)")
print(f"{problems}  ({len(meta)} rows)")

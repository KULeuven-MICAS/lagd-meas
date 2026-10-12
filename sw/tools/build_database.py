#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Toon Bettens <toon.bettens@kuleuven.be>
#
# Every sweep log -> one SQLite file. Portable, no dependencies to read it, and it carries the
# problem metadata alongside the measurements so nothing has to be remembered separately.
#
# Everything in the database is at MAGNITUDE 1. The chip runs some problems with the couplings
# scaled up for drive; that scaling is detected per sweep from the J checksum in the log and
# divided back out here, so a reader never sees it.
#
# Usage: uv run --python 3.14 --with numpy sw/tools/build_database.py

import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_ising_problem as gen           # noqa: E402  -- load_model and the J checksum

EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"

# ---------------------------------------------------------------------------
# 1. What should be there
# ---------------------------------------------------------------------------

PROBLEMS = ["pm1d_100", "pm1s_100", "pm1d_80_0", "pm1s_80_0", "mimo"]
IUNITS = [2, 5, 8, 11]
DB = EXPERIMENTS / "export" / "measurements.db"
CORE_FREQ_HZ = 512e6
MAGNITUDES = range(1, 8)              # |J| <= 7 caps what a magnitude can be


def expected(problem, iunit):
    """How many runs a sweep should hold. The 8 sweeps are the deep ones -- except mimo."""
    if iunit == 8 and problem != "mimo":
        return 100
    return 10


TAG = re.compile(r"^\s*\[[a-z]+\]\s?", re.MULTILINE)   # every line is tagged, not just the first
ROW = re.compile(r"^\s*(in|\d+)\s*\|\s*(\d+)\s*\|\s*(-?\d+)\s*\|")
CHECKSUM = re.compile(r"checksum 0x([0-9a-f]+)")

_seen = {}


def detect_magnitude(problem, checksum):
    """Which magnitude produces the J the chip actually ran, from the checksum it printed."""
    if (problem, checksum) in _seen:
        return _seen[(problem, checksum)]
    for magnitude in MAGNITUDES:
        j_int, _, _, _ = gen.quantise(gen.load_model(problem, magnitude), gen.zeros)
        j_pad = gen._pad_matrix(j_int)
        if gen.MIRROR_TO_LOW_SPINS:
            j_pad = j_pad[::-1, ::-1]
        if gen.j_checksum(j_pad) == checksum:
            _seen[(problem, checksum)] = magnitude
            return magnitude
    _seen[(problem, checksum)] = None
    return None


def read_info(problem):
    info = {}
    path = EXPERIMENTS / problem / "info"
    if path.is_file():
        for line in path.read_text().splitlines():
            if ":" in line and not line.startswith("note"):
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
    return info


# ---------------------------------------------------------------------------
# 2. Build
# ---------------------------------------------------------------------------

DB.parent.mkdir(parents=True, exist_ok=True)
if DB.exists():
    DB.unlink()                      # rebuilt from the logs every time; the logs are the truth
db = sqlite3.connect(DB)
db.executescript("""
CREATE TABLE problems (
    problem TEXT PRIMARY KEY,
    spins INTEGER,
    source TEXT,
    total_weight REAL,          -- MAX-CUT weight sum, magnitude 1; NULL if not a MAX-CUT problem
    optimum_cut REAL,           -- certified, NULL if unknown
    optimum_energy INTEGER,     -- certified, magnitude 1, NULL if unknown
    best_found_energy INTEGER,  -- not certified; only where no optimum is known
    scaling_h INTEGER,
    energy_offset REAL          -- objective = energy + offset, where the problem defines one
);
CREATE TABLE runs (
    problem TEXT, iunit INTEGER, run INTEGER,
    ran_at_magnitude INTEGER,   -- divided out already; recorded as provenance
    samples INTEGER,
    start_energy INTEGER, final_energy INTEGER, best_energy INTEGER, best_cut REAL,
    PRIMARY KEY (problem, iunit, run)
);
CREATE TABLE samples (
    problem TEXT, iunit INTEGER, run INTEGER,
    cycle INTEGER, time_ns REAL,
    energy INTEGER,             -- magnitude 1
    cut REAL,                   -- MAX-CUT value, NULL where the problem is not a MAX-CUT
    PRIMARY KEY (problem, iunit, run, cycle)
) WITHOUT ROWID;
CREATE INDEX samples_by_run ON samples (problem, iunit, run);
""")

report, sample_rows, run_rows = [], [], []
for problem in PROBLEMS:
    info = read_info(problem)
    weight = float(info["total_weight"]) if "total_weight" in info else None
    db.execute("INSERT INTO problems VALUES (?,?,?,?,?,?,?,?,?)", (
        problem,
        int(info["spins"]) if "spins" in info else None,
        info.get("source"),
        weight,
        float(info["optimum_cut"]) if "optimum_cut" in info else None,
        int(float(info["optimum_energy"])) if "optimum_energy" in info else None,
        int(float(info["best_found_energy"])) if "best_found_energy" in info else None,
        int(info["scaling_factor_h"]) if "scaling_factor_h" in info else None,
        float(info["offset"]) if "offset" in info else None,
    ))

    for iunit in IUNITS:
        runs_dir = EXPERIMENTS / problem / f"sweep_{iunit}" / "runs"
        logs = sorted(runs_dir.glob("*.log")) if runs_dir.is_dir() else []
        want = expected(problem, iunit)
        if not logs:
            report.append((problem, iunit, 0, want, "MISSING -- no runs directory"
                           if not runs_dir.is_dir() else "MISSING -- directory is empty"))
            continue

        magnitude, bad = None, []
        for log in logs:
            text = TAG.sub("", log.read_text(errors="replace"))
            run = int(log.stem)
            found = CHECKSUM.search(text)
            if found:
                m = detect_magnitude(problem, int(found.group(1), 16))
                if m is None:
                    bad.append(f"{log.name}: J checksum matches no magnitude")
                    continue
                if magnitude is not None and m != magnitude:
                    bad.append(f"{log.name}: magnitude {m}, sweep is {magnitude}")
                magnitude = m if magnitude is None else magnitude
            if magnitude is None:
                bad.append(f"{log.name}: no J checksum")
                continue

            rows, divisible = [], True
            for line in text.splitlines():
                mt = ROW.match(line)
                if not mt:
                    continue
                cycle, measured = int(mt.group(2)), int(mt.group(3))
                if measured % magnitude:
                    divisible = False
                    break
                energy = measured // magnitude
                cut = None if weight is None else (weight - energy) / 2
                rows.append((problem, iunit, run, cycle,
                             round(cycle / CORE_FREQ_HZ * 1e9, 4), energy, cut))
            if not divisible:
                bad.append(f"{log.name}: energies not divisible by magnitude {magnitude}")
                continue
            if len(rows) < 2:
                bad.append(f"{log.name}: {len(rows)} sample rows")
                continue

            energies = [r[5] for r in rows]
            cuts = [r[6] for r in rows if r[6] is not None]
            sample_rows += rows
            run_rows.append((problem, iunit, run, magnitude, len(rows),
                             energies[0], energies[-1], min(energies),
                             max(cuts) if cuts else None))

        have = len({r[2] for r in run_rows if r[0] == problem and r[1] == iunit})
        note = "ok" if have == want else ("SHORT" if have < want else "MORE THAN EXPECTED")
        if bad:
            note += " | " + "; ".join(bad[:3]) + (f" (+{len(bad) - 3})" if len(bad) > 3 else "")
        report.append((problem, iunit, have, want, note))

db.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)", run_rows)
db.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?)", sample_rows)
db.commit()

# ---------------------------------------------------------------------------
# 3. Report
# ---------------------------------------------------------------------------

print(f"  {'problem':<11}{'iunit':>6}{'runs':>7}{'expected':>10}   status")
incomplete = 0
for problem, iunit, have, want, note in report:
    if have != want:
        incomplete += 1
    print(f"  {problem:<11}{iunit:>6}{have:>7}{want:>10}   {note}")

mags = sorted({(r[0], r[1], r[3]) for r in run_rows})
print(f"\n  magnitudes detected from the J checksums:")
for problem in PROBLEMS:
    got = sorted({m for p, _, m in mags if p == problem})
    if got:
        print(f"    {problem:<11} {got}")

print(f"\n{DB}")
print(f"  {len(run_rows)} runs, {len(sample_rows)} samples, {len(PROBLEMS)} problems")
if incomplete:
    print(f"  {incomplete} of {len(report)} sweeps are not at their expected count")
db.close()

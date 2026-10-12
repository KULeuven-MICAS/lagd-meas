#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Toon Bettens <toon.bettens@kuleuven.be>
#
# sweep_states.spm.c log -> one trace per start state, indexed by state number. Pick the
# indices to draw; convergence is computed per trace and cached in a CSV you can hand-edit.
# Text callouts are added by hand after export.
#
# Usage: uv run --python 3.14 --with matplotlib sw/tools/plot_sweep.py

import csv
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt              # noqa: E402

EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"

# ---------------------------------------------------------------------------
# 1. Collect data
# ---------------------------------------------------------------------------

# Either one log with "=== state n ===" headers (the in-ELF sweep), or a directory of one log
# per state named <index>.log, which is what run_sweep.sh produces.
NAME = "mimo"
LOG = EXPERIMENTS / NAME / "sweep_8" / "runs"
CONV = (LOG / "convergence.csv") if LOG.is_dir() else LOG.with_name("convergence.csv")     # hand-editable; see below
CORE_FREQ_HZ = 512e6
OPTIMUM = {
        "pm1d_100": -709 * 3,
        "pm1s_100": -687,
        "pm1d_80_0": -534,
        "pm1s_80_0": -166,
        "mimo": -5070,
        }[NAME]
SHOW_OPTIMUM = True

TITLE = NAME                    # a string puts a title on the figure; None leaves it bare
PLOT = range(10)                # state indices to draw
WINDOW = (0,8)                   # cycles (lo, hi) drawn, same for every trace; None = whole trace

# Every line comes off the UART tagged "[chip] "; strip that before matching anything else.
TAG = re.compile(r"^\s*\[[a-z]+\]\s?")
# === state 12/100 ===
HEAD = re.compile(r"^=+\s*state\s+(\d+)\s*/\s*\d+")
#     3 |        4 |     -615 | fe19...        (the "in" row is the pre-run state, cycle 0)
ROW = re.compile(r"^\s*(?:in|\d+)\s*\|\s*(\d+)\s*\|\s*(-?\d+)\s*\|")

if not LOG.exists():
    sys.exit(f"missing {LOG}")

traces = {}                                  # index -> ([cycle], [energy])


def read_rows(text, index, traces):
    """Sample rows out of one log, into trace `index` unless a state header renames it."""
    for line in text.splitlines():
        line = TAG.sub("", line)
        m = HEAD.match(line.strip())
        if m:
            index = int(m.group(1))
            continue
        m = ROW.match(line)
        if m:
            traces.setdefault(index, ([], []))
            traces[index][0].append(int(m.group(1)))
            traces[index][1].append(int(m.group(2)))


if LOG.is_dir():
    # One log per state, named by index: 000.log, 001.log, ...
    logs = sorted(LOG.glob("*.log"))
    if not logs:
        sys.exit(f"{LOG}: no *.log files")
    for path in logs:
        stem = path.stem.lstrip("0") or "0"
        if not stem.isdigit():
            sys.exit(f"{path.name}: expected a numeric name like 003.log")
        read_rows(path.read_text(errors="replace"), int(stem), traces)
else:
    read_rows(LOG.read_text(errors="replace"), 0, traces)

traces = {i: t for i, t in traces.items() if len(t[0]) >= 2}
if not traces:
    sys.exit(f"{LOG}: no traces parsed")
print(f"  {LOG.name}: {len(traces)} traces, indices {min(traces)}..{max(traces)}")

# --- convergence ------------------------------------------------------------
# A trace has converged when it has reached its own best energy and stayed there: the first
# cycle after which every sample is within SETTLE_TOL of the best. It is flagged instead when
# that best is more than ACCEPT_GAP above the optimum (it settled on something poor), or when
# it only settles on the very last sample (it may still be moving).
SETTLE_TOL = 0      # energy units of slack around the best
ACCEPT_GAP = 100 * 7   # how far above OPTIMUM a trace may settle and still count

computed = {}
for i, (cyc, en) in sorted(traces.items()):
    best = min(en)
    k = len(en) - 1
    while k > 0 and en[k - 1] <= best + SETTLE_TOL:
        k -= 1
    note = ""
    if best < OPTIMUM:
        note = f"{OPTIMUM - best} BELOW the reference -- fine if OPTIMUM is a best-found, a "\
               f"real problem if it is certified"
    elif best > OPTIMUM + ACCEPT_GAP:
        note = f"settled {best - OPTIMUM:+d} from optimum"
    elif k == len(en) - 1:
        note = "reaches best only on the last sample"
    computed[i] = (float(cyc[k]), note)

# Cached to CSV so the flagged ones can be corrected by hand. The computed value goes in
# auto_cycle; the cycle column starts empty and WINS when you fill it in -- blank it again to
# fall back to auto. Notes survive too, so clearing one you have checked makes it stay cleared.
# New indices are appended; the file is rewritten in index order each run.
saved = {}
if CONV.is_file():
    with CONV.open() as fh:
        for r in csv.DictReader(fh):
            r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
            saved[int(r["index"])] = (r.get("cycle", ""), r.get("note", ""))

converged, flagged, hand = {}, [], 0
rows = []
for i in sorted(traces):
    auto_cyc, auto_note = computed[i]
    cyc_s, note = saved.get(i, ("", auto_note))
    at = float(cyc_s) if cyc_s else auto_cyc
    hand += bool(cyc_s)
    converged[i] = at
    if note:
        flagged.append((i, note))
    rows.append({"index": i, "auto_cycle": f"{auto_cyc:.4g}", "cycle": cyc_s,
                 "ns": f"{at / CORE_FREQ_HZ * 1e9:.4g}", "note": note})

CONV.parent.mkdir(parents=True, exist_ok=True)
with CONV.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["index", "auto_cycle", "cycle", "ns", "note"])
    w.writeheader()
    w.writerows(rows)
print(f"  convergence -> {CONV} ({hand} hand-set)")

if flagged:
    print(f"  {len(flagged)} trace(s) to check by hand:")
    for i, note in flagged:
        print(f"    state {i:<4} {note}")

print(f"\n  {'state':>6}{'start':>8}{'final':>8}{'best':>8}{'gap':>7}"
      f"{'conv (cyc)':>12}{'conv (ns)':>11}  note")
for i in sorted(traces):
    cyc, en = traces[i]
    at = converged[i]
    note = next((n for j, n in flagged if j == i), "")
    print(f"  {i:>6}{en[0]:>8}{en[-1]:>8}{min(en):>8}{min(en) - OPTIMUM:>+7d}"
          f"{at:>12.4g}{at / CORE_FREQ_HZ * 1e9:>11.4g}  {note}")

# ---------------------------------------------------------------------------
# 2. Make the figure
# ---------------------------------------------------------------------------

SHOW_HOOKS = False               # convergence hook per drawn trace

plt.rcParams.update({
    "axes.linewidth": 1.3,
    "xtick.labelsize": 12, "ytick.labelsize": 12,
    "xtick.major.width": 1.3, "ytick.major.width": 1.3,
    "xtick.major.size": 5, "ytick.major.size": 5,
    "legend.frameon": False,
    "lines.linewidth": 2.0, "lines.markersize": 8,
    "axes.grid": False,
    "savefig.dpi": 300, "figure.dpi": 120,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#4b2e83", "#d62728", "#17becf", "#8c564b", "#7f7f7f"]
NS = 1e9 / CORE_FREQ_HZ         # cycles -> ns on the x-axis

missing = [i for i in PLOT if i not in traces]
if missing:
    sys.exit(f"no trace for state(s) {missing}; parsed {min(traces)}..{max(traces)}")

lo, hi = WINDOW if WINDOW else (min(min(c) for c, _ in traces.values()),
                                max(max(c) for c, _ in traces.values()))
drawn = {i: ([c for c in traces[i][0] if lo <= c <= hi],
             [e for c, e in zip(*traces[i]) if lo <= c <= hi]) for i in PLOT}
empty = [i for i in PLOT if len(drawn[i][0]) < 2]
if empty:
    sys.exit(f"window {lo}..{hi} leaves state(s) {empty} with nothing to draw")

fig, ax = plt.subplots(figsize=(5.5, 4.2))

if SHOW_OPTIMUM:
    ax.axhline(OPTIMUM, color="black", linestyle="--", linewidth=1.2, zorder=1)

for n, i in enumerate(PLOT):
    cyc, en = drawn[i]
    ax.plot([c * NS for c in cyc], en, color=PALETTE[n % len(PALETTE)], linewidth=2.0,
            solid_joinstyle="round", solid_capstyle="round", label=str(i), zorder=3)

ylo, yhi = ax.get_ylim()
if SHOW_HOOKS:
    for n, i in enumerate(PLOT):
        cyc, en = traces[i]
        at = converged[i]
        if not lo <= at <= hi:          # convergence outside the drawn window: no hook to hang
            continue
        k = min(range(len(cyc) - 1), key=lambda j: abs(cyc[j] - at))
        w = cyc[k + 1] - cyc[k]
        y = en[k] + (0.0 if w == 0 else (at - cyc[k]) / w) * (en[k + 1] - en[k])
        c = PALETTE[n % len(PALETTE)]
        ax.plot([at * NS, at * NS], [ylo, y], color=c, linewidth=1.3, linestyle=(0, (3, 2)),
                zorder=2)
        ax.plot(at * NS, y, "o", color=c, markersize=8, zorder=6)
ax.set_ylim(ylo, yhi)           # drawing down to the floor re-triggers autoscale otherwise

if TITLE:
    ax.set_title(TITLE, fontsize=13, fontweight="bold", color="black", pad=8)


for spine in ax.spines.values():
    spine.set_linewidth(0.2)
    spine.set_color("black")
ax.tick_params(width=1.3, length=5, color="black")
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight("bold")
    lbl.set_fontsize(12)

fig.tight_layout()
out = (LOG.parent / "sweep") if LOG.is_dir() else LOG.with_name("sweep")
fig.savefig(f"{out}.pdf", bbox_inches="tight")
fig.savefig(f"{out}.png", bbox_inches="tight")
print(f"\n{out}.pdf / .png  ({len(PLOT)} traces: {', '.join(str(i) for i in PLOT)})")

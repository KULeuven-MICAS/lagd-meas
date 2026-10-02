# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# VCO lookup behind configure_vco(f, kvco) in sw/tests/pll_test.py: which (vco_tune_coarse,
# vco_current_min, vco_current_max) gives a target frequency with a Kvco closest to a target, from a table
# measured with vco_lut_measure(). Shared with sw/tools/notebooks/calibrate_vco.ipynb.
# Plain Python: runs on the lab machines' Python 3.6 as well as in the notebook environment.
#
# Vctrl drives the gate of the PMOS feeding the ring (Vctrl = 0 V: fully on, VDD: off, only the min
# branch conducts). Code 0 is the most current for both vco_current_max and vco_current_min.
#
# Table rows: {vco_tune_coarse, vco_current_min, vco_current_max, vctrl, f_vco}, f_vco NaN = no clock.
# Hard rules (never traded for a closer Kvco):
#   1. the setting has a clock at Vctrl = VDD (the ring never stops, even at the least current);
#   2. f_target is reached at a Vctrl inside the window, `margin` away from its edges;
#   3. every table point of the setting inside the window has a clock.
# Among the settings passing all three: |log(Kvco / kvco_target)| smallest, Kvco being the local slope
# at the operating Vctrl (piecewise linear between table points); ties: the more central Vctrl.
# kvco_target=None: no Kvco preference, the most central Vctrl wins. vco_frequency_range() uses that to
# find which frequencies can be reached at all.

import logging
import math

logger = logging.getLogger(__name__)

CODES = tuple(range(16))
HOLD_MIN = 15  # vco_current_min while the max setting is swept (vco_current_families)
HOLD_MAX = 0  # vco_current_max while the min setting is swept / at VDD (vco_current_families, vco_lut_measure)
VCTRL_WINDOW = (0.0, 0.75)  # [V] Vctrl range the PLL operates in: 0 V to VDD
LUT_FIELDS = ("vco_tune_coarse", "vco_current_min", "vco_current_max")


def read_lut(csv_path):
    """Read a VCO lookup table CSV into rows (codes as int, vctrl and f_vco as float, NaN = no clock).
    Drift-reference rows (`swept` = "drift") are not part of the table and are left out."""
    import csv  # local: only needed here
    rows = []
    with open(str(csv_path), newline="") as f:
        for r in csv.DictReader(f):
            if r.get("swept") == "drift":
                continue
            row = {k: int(float(r[k])) for k in LUT_FIELDS}
            row["vctrl"] = float(r["vctrl"])
            try:
                row["f_vco"] = float(r["f_vco"])
            except ValueError:
                row["f_vco"] = math.nan
            rows.append(row)
    return rows


def choose_vco(rows, f_target, kvco_target=None, window=VCTRL_WINDOW, margin=0.02, vdd=None, n_alternatives=3,
               log=True):
    """Pick the setting for f_target / kvco_target (see above) and log the expected operating point.

    kvco_target=None: any Kvco, the setting with the most central operating Vctrl. log=False: no report.
    Returns (best, alternatives): best is {vco_tune_coarse, vco_current_min, vco_current_max, vctrl, kvco,
    kvco_min, kvco_max, n_options} or None when no setting reaches f_target inside the window;
    kvco_min/kvco_max/n_options describe all settings that pass the rules for this frequency.
    Alternatives are the next best ones.
    """
    if vdd is None:
        vdd = max(r["vctrl"] for r in rows)
    curves = {}
    for r in rows:
        curves.setdefault(tuple(r[k] for k in LUT_FIELDS), []).append((r["vctrl"], r["f_vco"]))

    lo, hi, centre = window[0] + margin, window[1] - margin, (window[0] + window[1]) / 2
    found = []
    for key, pts in curves.items():
        pts.sort()
        at_vdd = [f for v, f in pts if abs(v - vdd) < 1e-6]
        if not at_vdd or math.isnan(at_vdd[0]):
            continue  # rule 1
        inside = [(v, f) for v, f in pts if window[0] - 1e-6 <= v <= window[1] + 1e-6]
        if len(inside) < 2 or any(math.isnan(f) for _, f in inside):
            continue  # rule 3
        for (v0, f0), (v1, f1) in zip(inside, inside[1:]):
            if v1 <= v0 or f0 == f1 or not min(f0, f1) <= f_target <= max(f0, f1):
                continue
            v = v0 + (f_target - f0) * (v1 - v0) / (f1 - f0)
            if lo <= v <= hi:  # rule 2
                kvco = abs(f1 - f0) / (v1 - v0)
                found.append({**dict(zip(LUT_FIELDS, key)), "vctrl": v, "kvco": kvco})
                break
    if kvco_target is None:
        found.sort(key=lambda s: abs(s["vctrl"] - centre))
    else:
        found.sort(key=lambda s: (abs(math.log(s["kvco"] / kvco_target)), abs(s["vctrl"] - centre)))
    if not found:
        if log:
            logger.info("%.1f MHz: no setting reaches it inside Vctrl %.2f-%.2f V (margin %.0f mV)",
                        f_target / 1e6, lo - margin, hi + margin, margin * 1e3)
        return None, []
    kvcos = [s["kvco"] for s in found]
    best = dict(found[0], kvco_min=min(kvcos), kvco_max=max(kvcos), n_options=len(found))
    if log:
        target = ("any" if kvco_target is None else
                  "target %.0f MHz/V, x%.2f" % (kvco_target / 1e6, best["kvco"] / kvco_target))
        logger.info("%.1f MHz: coarse %d, min %d, max %d -> expected Vctrl %.3f V, |Kvco| %.0f MHz/V (%s); "
                    "possible |Kvco| at this frequency %.0f-%.0f MHz/V (%d settings)",
                    f_target / 1e6, best["vco_tune_coarse"], best["vco_current_min"], best["vco_current_max"],
                    best["vctrl"], best["kvco"] / 1e6, target, best["kvco_min"] / 1e6, best["kvco_max"] / 1e6,
                    best["n_options"])
    return best, found[1:1 + n_alternatives]


def vco_frequency_range(rows, window=VCTRL_WINDOW, margin=0.02, points_per_decade=100):
    """Which frequencies choose_vco (kvco_target=None, same rules) can reach, overall and per coarse code.

    Scans a log-spaced frequency grid (`points_per_decade`) between the lowest and highest frequency in the
    table and merges consecutive reachable grid points into bands, so gaps show up as separate bands.
    Returns {"all": [(f_lo, f_hi), ...], coarse: [(f_lo, f_hi), ...], ...} in Hz, and logs a summary.
    """
    f_all = [r["f_vco"] for r in rows if not math.isnan(r["f_vco"]) and r["f_vco"] > 0]
    if not f_all:
        return {"all": []}
    lo_dec, hi_dec = math.log10(min(f_all)), math.log10(max(f_all))
    n = int((hi_dec - lo_dec) * points_per_decade) + 1
    grid = [10 ** (lo_dec + (hi_dec - lo_dec) * i / max(n - 1, 1)) for i in range(n)]

    def bands(sub_rows):
        out, start, last = [], None, None
        for f in grid:
            ok = choose_vco(sub_rows, f, None, window=window, margin=margin, log=False)[0] is not None
            if ok and start is None:
                start = f
            if not ok and start is not None:
                out.append((start, last))
                start = None
            if ok:
                last = f
        if start is not None:
            out.append((start, last))
        return out

    def fmt(bs):
        return ", ".join("%.1f-%.1f MHz" % (a / 1e6, b / 1e6) for a, b in bs) or "none"

    result = {"all": bands(rows)}
    for coarse in sorted({r["vco_tune_coarse"] for r in rows}):
        result[coarse] = bands([r for r in rows if r["vco_tune_coarse"] == coarse])
        logger.info("coarse %d: %s", coarse, fmt(result[coarse]))
    logger.info("reachable inside Vctrl %.2f-%.2f V (margin %.0f mV): %s", window[0], window[1], margin * 1e3,
                fmt(result["all"]))
    return result

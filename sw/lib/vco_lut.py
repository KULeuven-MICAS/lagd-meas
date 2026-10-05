# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# VCO lookup table: measure it (vco_lut_measure), read it (read_lut), and pick the (vco_tune_coarse,
# vco_current_min, vco_current_max) that gives a target frequency with a Kvco closest to a target
# (choose_vco, configure_vco); vco_frequency_range shows which frequencies can be reached at all.
#
# The selection part is plain Python and imports no instrument code, so it runs on the lab machines'
# Python 3.6 and in the notebook environment (sw/tools/notebooks/calibrate_vco.ipynb) alike; the two
# functions that talk to the hardware import sw/lib/vco_measure.py (pyvisa) only when called.
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
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "vco"  # results/ is gitignored

CODES = tuple(range(16))
HOLD_MIN = 15  # vco_current_min while the max setting is swept (vco_current_families)
HOLD_MAX = 0  # vco_current_max while the min setting is swept / at VDD (vco_current_families, vco_lut_measure)
VCTRL_WINDOW = (0.5, 0.7)  # [V] Vctrl range the PLL operates in: the steep (high Kvco) part of the curves
LUT_FIELDS = ("vco_tune_coarse", "vco_current_min", "vco_current_max")

# Lookup-table grid (vco_lut_measure defaults): Vctrl coarse where the curves are flat (PMOS fully on), 50 mV
# where they are steep; min 0 as reference plus 8..15 (codes 0..7 nearly saturate the ring on their own); max
# every other code plus 15.
LUT_VCTRLS = (0.0, 0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)
LUT_MIN_CODES = (0, 8, 9, 10, 11, 12, 13, 14, 15)
LUT_MAX_CODES = (0, 2, 4, 6, 8, 10, 12, 14, 15)
# Drift references (coarse, min, max, Vctrl), measured at the start and after every coarse code:
# at 0 V the curve is flat (PMOS fully on), so only the VCO itself (temperature, supply) moves it; at 0.65 V
# it is steep, so drift of the current source / Vctrl shows up as well.
LUT_DRIFT_REFS = ((8, 8, 8, 0.0), (8, 8, 8, 0.65))


# ---------------------------------------------------------------------------------------------
# Reading and choosing (no instruments)
# ---------------------------------------------------------------------------------------------
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


def newest_lut(sample=None):
    """Path of the newest results/vco/vco_lut_<sample>_*.csv (any sample when None); raises when none."""
    found = sorted((p for p in RESULTS_DIR.glob("vco_lut_{}_*.csv".format(sample) if sample else "vco_lut_*.csv")
                    if not p.name.startswith("vco_lut_check_")),  # vco_test.py check runs, not tables
                   key=lambda p: p.stat().st_mtime)
    if not found:
        raise FileNotFoundError(f"no VCO lookup table in {RESULTS_DIR}, run vco_lut_measure() first")
    return found[-1]


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


# ---------------------------------------------------------------------------------------------
# Hardware: measure the table, set the VCO from it
# ---------------------------------------------------------------------------------------------
def vco_lut_measure(sample=None, coarse_codes=range(16), min_codes=LUT_MIN_CODES, max_codes=LUT_MAX_CODES,
                    vctrls=LUT_VCTRLS, drift_refs=LUT_DRIFT_REFS, vdd=None, scope_ch=1, probe_att=10, settle=0.2,
                    n_read=5):
    """Measure the VCO lookup table used by configure_vco.

    Per coarse code, so every finished coarse code has complete curves if the run stops early:
      1. At Vctrl = `vdd` (SMU v_max), where only the min branch conducts: every vco_current_min 0..15
         (max = HOLD_MAX). The point is written once per code in `max_codes`, so every setting in the table
         has its VDD row (rule: the ring must still oscillate there).
      2. Per code in `min_codes` that oscillated at VDD, per Vctrl in `vctrls`: every code in `max_codes`.
      3. The drift references `drift_refs` = ((coarse, min, max, Vctrl), ...), also measured once before the
         first coarse code (`swept` = "drift"; read_lut leaves these rows out).
    Every row has a `time` stamp. Writes results/vco/vco_lut_<sample>_<stamp>.csv, flushed per curve.
    """
    import csv
    import time
    from sw.lib import vco_measure as vm  # instruments (pyvisa): only needed when measuring
    from sw.lib.pll_settings import VCO_CHARAC_CFG

    if vdd is None:
        vdd = vm.load_instr_cfg()["smu_vctrl"]["args"]["v_max"]
    vctrls = [v for v in vctrls if v < vdd - 1e-6]  # VDD itself is step 1
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "vco_lut_{}_{}.csv".format(sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))

    logger.info("VCO lookup table: coarse %s, min %s (those oscillating at VDD), max %s, Vctrl %s V + VDD %.2f V, "
                "drift references %s -> %s", list(coarse_codes), list(min_codes), list(max_codes), list(vctrls),
                vdd, list(drift_refs), csv_path.name)

    cfg = VCO_CHARAC_CFG.copy()
    cfg.update(vco_tune_coarse=coarse_codes[0], vco_current_min=HOLD_MIN, vco_current_max=HOLD_MAX)
    pll = vm.open_pll(cfg)

    smu, scope = vm.open_vco_instruments(vdd, scope_ch, probe_att)
    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["sample", "swept", "time"] + list(LUT_FIELDS) + ["vctrl"]
                                    + list(vm.POINT_COLUMNS))
            writer.writeheader()

            def measure(vctrl):
                vm.load_vco(pll, cfg)
                time.sleep(settle)
                return vm.measure_vco(pll, smu, scope, scope_ch, cfg, vctrl, settle, n_read=n_read)

            def write(point, swept, vctrl, **codes_override):
                row = dict(point, sample=sample, swept=swept, vctrl=vctrl,
                           time=datetime.now().isoformat(timespec="seconds"), **{k: cfg[k] for k in LUT_FIELDS})
                row.update(codes_override)
                writer.writerow(row)

            def drift():
                for c, m, mx, v in drift_refs:
                    cfg.update(vco_tune_coarse=c, vco_current_min=m, vco_current_max=mx)
                    vm.reset_divider(cfg)
                    vm.set_vctrl(smu, v, settle)
                    point = measure(v)
                    write(point, "drift", v)
                    logger.info("Drift reference coarse %d, min %d, max %d, Vctrl %.3f V: f_vco %.2f MHz (%s)",
                                c, m, mx, v, point["f_vco"] / 1e6, point["clock"])
                f.flush()

            drift()
            for coarse in coarse_codes:
                # 1. Which min codes keep the ring oscillating at VDD.
                logger.info("VDD %.2f V, coarse %d: vco_current_min 0..15", vdd, coarse)
                vm.set_vctrl(smu, vdd, settle)
                vm.reset_divider(cfg)
                runs_at_vdd = {}
                for m in CODES:
                    cfg.update(vco_tune_coarse=coarse, vco_current_min=m, vco_current_max=HOLD_MAX)
                    point = measure(vdd)
                    runs_at_vdd[m] = point["clock"] == "ok"
                    for mx in max_codes:  # at VDD the max branch is off: the same point for every max code
                        write(point, "vdd", vdd, vco_current_max=mx)
                f.flush()
                logger.info("Coarse %d: min codes with a clock at VDD: %s", coarse,
                            [m for m in CODES if runs_at_vdd[m]])

                # 2. The Vctrl points for every allowed min code and every max code.
                for m in min_codes:
                    if not runs_at_vdd.get(m):
                        continue
                    cfg.update(vco_tune_coarse=coarse, vco_current_min=m)
                    vm.reset_divider(cfg)
                    for vctrl in vctrls:
                        logger.info("Coarse %d, min %d, Vctrl %.3f V: vco_current_max %s", coarse, m, vctrl,
                                    list(max_codes))
                        vm.set_vctrl(smu, vctrl, settle)
                        for mx in max_codes:
                            cfg["vco_current_max"] = mx
                            write(measure(vctrl), "window", vctrl)
                        f.flush()  # keep what was measured if the run is interrupted
                logger.info("Coarse %d done", coarse)

                # 3. Drift references.
                drift()
    finally:
        smu.close()  # back to 0 V, output off
        scope.close()
    logger.info("VCO lookup table written to %s", csv_path)
    return csv_path


def configure_vco(f_vco, kvco=None, cfg=None, sample=None, lut_csv=None, window=VCTRL_WINDOW, margin=0.02):
    """Set the VCO for `f_vco` [Hz] with |Kvco| as close as possible to `kvco` [Hz/V] (None: any Kvco).

    The setting comes from choose_vco on a lookup table (`lut_csv`, else the newest
    results/vco/vco_lut_<sample>_*.csv): the ring must oscillate at Vctrl = VDD and f_vco must be reached
    inside `window` (with `margin`); only then is Kvco matched. The three codes are applied on `cfg`
    (default VCO_CHARAC_CFG: open loop, Vctrl from the pad; pass the PLL's config for closed loop) and
    loaded. Returns (pick, pll): pick is {codes, vctrl, kvco, ...}, pll the opened PllDriver. Raises when
    no setting reaches f_vco.
    """
    from sw.lib import pll_setup  # FPGA link: only needed when loading
    from sw.lib.pll_settings import VCO_CHARAC_CFG

    lut_csv = lut_csv or newest_lut(sample)
    best, alternatives = choose_vco(read_lut(lut_csv), f_vco, kvco, window=window, margin=margin)
    if best is None:
        raise ValueError(f"no VCO setting reaches {f_vco / 1e6:.1f} MHz inside Vctrl {window[0]}-{window[1]} V "
                         f"({lut_csv})")
    logger.info("  (lookup table %s)", Path(lut_csv).name)
    for alt in alternatives:
        logger.info("  alternative: coarse %d, min %d, max %d -> Vctrl %.3f V, |Kvco| %.0f MHz/V",
                    alt["vco_tune_coarse"], alt["vco_current_min"], alt["vco_current_max"], alt["vctrl"],
                    alt["kvco"] / 1e6)
    cfg = dict(VCO_CHARAC_CFG if cfg is None else cfg)
    cfg.update({k: best[k] for k in LUT_FIELDS})
    pll = pll_setup.connect()
    pll_setup.load_config(pll, cfg)
    return best, pll

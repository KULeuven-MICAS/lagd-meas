# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# VCO lookup table: measure it (vco_lut_measure) and use it (VcoLUT). Typical use in a measurement:
#
#   lut = VcoLUT(sample="S5")                     # newest results/vco/vco_lut_S5_*.csv (or VcoLUT(csv_path))
#   cfg = lut.update_config(CFG_REF8, 1e9, 1e9)   # start config + the VCO codes for 1 GHz, |Kvco| ~1 GHz/V
#   op = lut.predict(cfg, 1e9)                    # {"vctrl_pred", "kvco_pred"}: expected operating point
#   pll = pll_setup.open_pll(cfg)                 # load it on the chip
#
# VcoLUT is plain Python and imports no instrument code, so it runs on the lab machines' Python 3.6 and in the
# notebook environment (sw/tools/notebooks/calibrate_vco.ipynb) alike; vco_lut_measure imports
# sw/lib/vco_measure.py (pyvisa) only when called.
#
# Vctrl drives the gate of the PMOS feeding the ring (Vctrl = 0 V: fully on, VDD: off, only the min
# branch conducts). Code 0 is the most current for both vco_current_max and vco_current_min.
#
# Table rows: {vco_tune_coarse, vco_current_min, vco_current_max, vctrl, f_vco}, f_vco NaN = no clock.
# Hard rules for a setting (never traded for a closer Kvco):
#   1. the setting has a clock at Vctrl = VDD (the ring never stops, even at the least current);
#   2. f_target is reached at a Vctrl inside the window, `margin` away from its edges;
#   3. every table point of the setting inside the window has a clock.
# Among the settings passing all three: |log(Kvco / kvco_target)| smallest, Kvco being the local slope
# at the operating Vctrl (piecewise linear between table points); ties: the more central Vctrl.
# kvco_target=None: no Kvco preference, the most central Vctrl wins.

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
# Using the table (no instruments)
# ---------------------------------------------------------------------------------------------
def vco_codes(cfg):
    """The three VCO code fields (LUT_FIELDS) of a config, e.g. for a results row."""
    return {k: cfg[k] for k in LUT_FIELDS}


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
    """Path of the newest results/vco/vco_lut_<sample>_<stamp>.csv (any sample when None), by the stamp in the
    file name; raises when none."""
    found = sorted((p for p in RESULTS_DIR.glob("vco_lut_{}_*.csv".format(sample) if sample else "vco_lut_*.csv")
                    if not p.name.startswith("vco_lut_check_")),  # vco_test.py check runs, not tables
                   key=lambda p: p.stem[-15:])  # <YYYYmmdd>_<HHMMSS>
    if not found:
        raise FileNotFoundError(f"no VCO lookup table in {RESULTS_DIR}, run vco_lut_measure() first")
    return found[-1]


def _crossings(pts, f):
    """(vctrl, |Kvco|) where the piecewise-linear curve `pts` (sorted (vctrl, f_vco)) passes f, per segment in
    order of Vctrl; |Kvco| is the slope of that segment. Segments with a point without clock are skipped."""
    out = []
    for (v0, f0), (v1, f1) in zip(pts, pts[1:]):
        if math.isnan(f0) or math.isnan(f1) or v1 <= v0 or f0 == f1 or not min(f0, f1) <= f <= max(f0, f1):
            continue
        out.append((v0 + (f - f0) * (v1 - v0) / (f1 - f0), abs(f1 - f0) / (v1 - v0)))
    return out


class VcoLUT:
    """A measured VCO lookup table: picks the VCO codes for a frequency and |Kvco| (rules at the top of this file).

    csv: the table to use; None = the newest results/vco/vco_lut_<sample>_*.csv (any sample when sample is None).
    Attributes that can be changed directly:
      window          (Vctrl low, Vctrl high) [V] the PLL operates in
      margin          [V] minimum distance of the operating Vctrl to the window edges
      vdd             [V] Vctrl at which every setting must still oscillate (default: highest Vctrl in the table)
      n_alternatives  how many runner-up settings update_config logs
    """

    def __init__(self, csv=None, sample=None, window=VCTRL_WINDOW, margin=0.02):
        self.path = Path(csv) if csv else newest_lut(sample)
        self.rows = read_lut(self.path)
        self.window = window
        self.margin = margin
        self.vdd = max(r["vctrl"] for r in self.rows)
        self.n_alternatives = 3
        self._curves = {}  # (coarse, min, max) -> sorted [(vctrl, f_vco), ...]
        for r in self.rows:
            self._curves.setdefault(tuple(r[k] for k in LUT_FIELDS), []).append((r["vctrl"], r["f_vco"]))
        for pts in self._curves.values():
            pts.sort()
        logger.info("VCO lookup table %s: %d settings", self.path.name, len(self._curves))

    def update_config(self, cfg, f_vco, kvco=None):
        """A copy of `cfg` with the VCO codes for `f_vco` [Hz] and |Kvco| as close as possible to `kvco` [Hz/V]
        (None: any Kvco, the most central Vctrl). Logs the pick, the expected operating point and the alternatives.
        Raises ValueError when no setting reaches f_vco inside the window."""
        found = self._candidates(f_vco, kvco)
        if not found:
            raise ValueError("no VCO setting reaches %.1f MHz inside Vctrl %.2f-%.2f V (margin %.0f mV), table %s"
                             % (f_vco / 1e6, self.window[0], self.window[1], self.margin * 1e3, self.path.name))
        best = found[0]
        kvcos = [s["kvco"] for s in found]
        target = "any" if kvco is None else "target %.0f MHz/V, x%.2f" % (kvco / 1e6, best["kvco"] / kvco)
        logger.info("%.1f MHz: coarse %d, min %d, max %d -> expected Vctrl %.3f V, |Kvco| %.0f MHz/V (%s); "
                    "possible |Kvco| at this frequency %.0f-%.0f MHz/V (%d settings)",
                    f_vco / 1e6, best["vco_tune_coarse"], best["vco_current_min"], best["vco_current_max"],
                    best["vctrl"], best["kvco"] / 1e6, target, min(kvcos) / 1e6, max(kvcos) / 1e6, len(found))
        for alt in found[1:1 + self.n_alternatives]:
            logger.info("  alternative: coarse %d, min %d, max %d -> Vctrl %.3f V, |Kvco| %.0f MHz/V",
                        alt["vco_tune_coarse"], alt["vco_current_min"], alt["vco_current_max"], alt["vctrl"],
                        alt["kvco"] / 1e6)
        return dict(cfg, **vco_codes(best))

    def predict(self, cfg, f_vco):
        """Expected operating point of the VCO codes in `cfg` at `f_vco` [Hz]: {"vctrl_pred": [V], "kvco_pred":
        |Kvco| [Hz/V]}. For codes from update_config this is the point it picked; for other codes the crossing
        closest to the window centre anywhere on their curve. Raises ValueError when the codes do not reach f_vco."""
        pts = self._curve_points(cfg)
        lo, hi = self.window[0] + self.margin, self.window[1] - self.margin
        crossings = [c for c in _crossings(self._window_points(pts), f_vco) if lo <= c[0] <= hi]
        if not crossings:
            centre = (self.window[0] + self.window[1]) / 2
            crossings = sorted(_crossings(pts, f_vco), key=lambda c: abs(c[0] - centre))
        if not crossings:
            raise ValueError("coarse %d, min %d, max %d does not reach %.1f MHz (table %s)"
                             % (*vco_codes(cfg).values(), f_vco / 1e6, self.path.name))
        vctrl, kvco = crossings[0]
        return {"vctrl_pred": vctrl, "kvco_pred": kvco}

    def kvco_range(self, f_vco):
        """(lowest, highest) |Kvco| [Hz/V] among the settings that reach `f_vco` [Hz] under the rules.
        Raises ValueError when none does."""
        kvcos = [s["kvco"] for s in self._candidates(f_vco)]
        if not kvcos:
            raise ValueError("no VCO setting reaches %.1f MHz inside Vctrl %.2f-%.2f V (table %s)"
                             % (f_vco / 1e6, self.window[0], self.window[1], self.path.name))
        return min(kvcos), max(kvcos)

    def curve(self, cfg):
        """(vctrls, f_vcos) of the VCO codes in `cfg` in the table, sorted by Vctrl, points with a clock only."""
        pts = [(v, f) for v, f in self._curve_points(cfg) if not math.isnan(f)]
        return [v for v, _ in pts], [f for _, f in pts]

    def frequency_range(self, points_per_decade=100):
        """Which frequencies update_config can reach (kvco=None, same rules), overall and per coarse code.

        Scans a log-spaced frequency grid (`points_per_decade`) between the lowest and highest frequency in the
        table and merges consecutive reachable grid points into bands, so gaps show up as separate bands.
        Returns {"all": [(f_lo, f_hi), ...], coarse: [(f_lo, f_hi), ...], ...} in Hz, and logs a summary.
        """
        f_all = [r["f_vco"] for r in self.rows if not math.isnan(r["f_vco"]) and r["f_vco"] > 0]
        if not f_all:
            return {"all": []}
        lo_dec, hi_dec = math.log10(min(f_all)), math.log10(max(f_all))
        n = int((hi_dec - lo_dec) * points_per_decade) + 1
        grid = [10 ** (lo_dec + (hi_dec - lo_dec) * i / max(n - 1, 1)) for i in range(n)]

        def bands(coarse):
            out, start, last = [], None, None
            for f in grid:
                ok = bool(self._candidates(f, coarse=coarse))
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

        result = {"all": bands(None)}
        for coarse in sorted({key[0] for key in self._curves}):
            result[coarse] = bands(coarse)
            logger.info("coarse %d: %s", coarse, fmt(result[coarse]))
        logger.info("reachable inside Vctrl %.2f-%.2f V (margin %.0f mV): %s", self.window[0], self.window[1],
                    self.margin * 1e3, fmt(result["all"]))
        return result

    def _curve_points(self, cfg):
        key = tuple(cfg[k] for k in LUT_FIELDS)
        if key not in self._curves:
            raise ValueError("coarse %d, min %d, max %d is not in the table %s" % (*key, self.path.name))
        return self._curves[key]

    def _window_points(self, pts):
        return [(v, f) for v, f in pts if self.window[0] - 1e-6 <= v <= self.window[1] + 1e-6]

    def _candidates(self, f_vco, kvco=None, coarse=None):
        """Every setting (optionally of one coarse code) that reaches f_vco under the rules, best first:
        [{vco_tune_coarse, vco_current_min, vco_current_max, vctrl, kvco}, ...]."""
        lo, hi = self.window[0] + self.margin, self.window[1] - self.margin
        centre = (self.window[0] + self.window[1]) / 2
        found = []
        for key, pts in self._curves.items():
            if coarse is not None and key[0] != coarse:
                continue
            at_vdd = [f for v, f in pts if abs(v - self.vdd) < 1e-6]
            if not at_vdd or math.isnan(at_vdd[0]):
                continue  # rule 1
            inside = self._window_points(pts)
            if len(inside) < 2 or any(math.isnan(f) for _, f in inside):
                continue  # rule 3
            crossings = [c for c in _crossings(inside, f_vco) if lo <= c[0] <= hi]  # rule 2
            if crossings:
                found.append(dict(zip(LUT_FIELDS, key), vctrl=crossings[0][0], kvco=crossings[0][1]))
        if kvco is None:
            found.sort(key=lambda s: abs(s["vctrl"] - centre))
        else:
            found.sort(key=lambda s: (abs(math.log(s["kvco"] / kvco)), abs(s["vctrl"] - centre)))
        return found


# ---------------------------------------------------------------------------------------------
# Hardware: measure the table
# ---------------------------------------------------------------------------------------------
def vco_lut_measure(sample=None, coarse_codes=range(16), min_codes=LUT_MIN_CODES, max_codes=LUT_MAX_CODES,
                    vctrls=LUT_VCTRLS, drift_refs=LUT_DRIFT_REFS, vdd=None, scope_ch=1, probe_att=10, settle=0.2,
                    n_read=5):
    """Measure the VCO lookup table used by VcoLUT.

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
    from sw.lib import pll_setup, vco_measure as vm  # FPGA link, instruments (pyvisa): only needed when measuring
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
    pll = pll_setup.open_pll(cfg)

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

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Influence of vco_current_max on the locked PLL. In the 2026-10-20 runs (pll_test_vctrl.py) the noise jitter at the
# same predicted Vctrl (~0.54 V, 1 GHz) rose with vco_current_max: 21 ps at code 0, 45 ps at 12, 192 / 351 ps at
# 14 / 15. Those runs mix three things: the VCO codes, the real Kvco (the lookup table of 2026-10-01 is ~5 % off and
# too coarse at the knee of the curves) and the loop's stability margin (LOOP_FILTER: most pump current, least
# capacitance; at Vctrl 0.60 V max codes 0-10 only locked with the Vctrl pad's extra capacitance). The plan:
#
#   Step 1  vco_map()               the f_vco-Vctrl curves measured in closed loop (conservative filter, Vctrl read
#                                   on the pad): today's curves and measured Kvco instead of the table; every point
#                                   is also a lock check (other coarse codes too). Read back with VcoMap.
#   Step 2  filter_check()          two mapped points (measured |Kvco| ~1.5 and ~4 GHz/V near 1 GHz), each with
#                                   LOOP_FILTER and one filter change at a time: how much of "noisy" / "no lock" is
#                                   the filter; picks a filter stable over the Kvco range.
#   Step 3  current_max_matched()   every max code of FAMILIES at the same measured |Kvco| (from the map), with the
#                                   filter of step 2: current effect or Kvco effect.
#   Step 3b loop_gain_sweep()       one coarse / min and f_vco, max codes x every charge-pump code: jitter against
#                                   set_current x measured |Kvco| (binary-weighted Icp): loop gain or VCO noise.
#
# Earlier tests (predicted operating point from the table):
#   current_max_family(coarse, cur_min)   vco_tune_coarse and vco_current_min fixed, only vco_current_max stepped.
#                                         To keep the operating point the same too, every setting is locked at the
#                                         f_vco where the table expects Vctrl = VCTRL (VcoLUT.frequency_at): the
#                                         frequency (and with it the reference, f_vco / FB_DIV) moves instead.
#   current_max_sweep(f_vco)              the earlier variant: one f_vco, per max code the table's setting closest to
#                                         VCTRL (other codes free).
#
# Every setting is measured with pll_test_vctrl.measure_pll_vctrl, Vctrl read the safe way (vctrl_pad="read": the pad
# connected only to read Vctrl right after lock on the RTB2004, then reloaded with the pad off for the analyzer).
#
# Results:
#   results/pll/pll_vco_map_<sample>_<stamp>.csv                   step 1, one row per point (pll_vco_map.ipynb)
#   results/pll/pll_filter_check_<sample>_<stamp>[_traces].csv     step 2, one row per point and filter
#   results/pll/pll_test_current_max_<sample>_<stamp>.csv          step 3 and the earlier tests, one row per setting
#   results/pll/pll_test_current_max_<sample>_<stamp>_traces.csv   (columns of pll_test_vctrl; pll_test_current_max.ipynb)
#
# Tests:
#   vco_map(settings, sample)                     # step 1 (default settings: map_settings())
#   filter_check(vco_map, kvcos, sample)          # step 2
#   current_max_matched(vco_map, kvco, sample)    # step 3
#   loop_gain_sweep(vco_map, f_vco, sample)       # step 3b
#   current_max_family(coarse, cur_min, sample)   # one coarse / min family, max stepped at one constant Vctrl
#   current_max_families(families, sample)        # several families into one CSV; lock_only=True: lock check only
#   current_max_sweep(f_vco, vctrl, sample)       # one f_vco, the table's setting per max code
#

import csv
import logging
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import FILTER_FIELDS, LOOP_FILTER, SAFE_LOOP_CFG
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows
from sw.tests.pll_test_vctrl import (PROBE_ATT, SCOPE_CENTRE, SCOPE_CH, SCOPE_SCALE, SCOPE_TIMEBASE, VCTRL_WINDOW,
                                     loop_cfg, measure_pll_vctrl, result_csv_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"
CSV_PREFIX = "pll_test_current_max"
LOCK_CHECK_PREFIX = "pll_lock_check_current_max"  # lock_only runs: kept apart from the notebook's result CSVs

# Predicted Vctrl every setting is locked at: where the clean settings were (measured ~0.49 V: the table from
# 2026-10-01 predicts 15-50 mV high).
VCTRL = 0.54
# Operating points of current_max_families. Every f-Vctrl curve is flat up to ~0.5 V (PMOS fully on, current set by
# the max code), drops steeply between ~0.5 and ~0.65 V (PMOS turning off, the same window for every code) and is
# flat again above (min branch only). 0.54 V sits on the upper knee: the local |Kvco| hardly depends on the max code
# there (c9 min 9: 0.6-1.8 GHz/V). 0.60 V is in the steep part: |Kvco| scales with the code (c9 min 9: 3.9 GHz/V at
# max 0 -> 0.9 at 15; c7 min 9: 5.8 -> 1.0), so a Kvco effect shows there and not at 0.54 V.
VCTRLS = (0.54, 0.60)
# coarse / min families of current_max_families (from the S5 table at VCTRL): c9 min 9: max 0 -> 1073 MHz ... max 15 ->
# 789 MHz, |Kvco| 0.6-1.8 GHz/V; c7 min 9: 1313 ... 903 MHz, 0.8-3.3 GHz/V (holds c7 min 9 max 14, noisy on
# 2026-10-20). At 0.60 V: c9 min 9 869 ... 739 MHz, c7 min 9 1005 ... 845 MHz. All above the lock limit (~640 MHz) and
# on pads of 50-100 MHz.
FAMILIES = ((9, 9), (7, 9))
# Frequencies are rounded to this step [Hz] (a neat reference; the Vctrl change is < 1 mV)
F_STEP = 1e6

# Step 1, vco_map: closed-loop VCO map. Filter: SAFE_LOOP_CFG's (Icp 1, C1 7, C2 7, R1 3: smallest bandwidth, most
# capacitance), which should lock where LOOP_FILTER (Icp 7, C1 0, C2 0, R1 7) does not; only Vctrl is read, so the
# loop dynamics do not matter. Per setting MAP_POINTS frequencies from MAP_F_LOW x the table's f at MAP_VCTRL_HIGH
# (the floor) to the table's f at MAP_VCTRL_LOW (the top): ~5 % below the table's range (the VCO runs ~5 % slower
# than the 2026-10-01 table) up to its top. Kvco from neighbouring points at least MAP_MIN_DV apart.
MAP_PREFIX = "pll_vco_map"
MAP_FILTER = {k: SAFE_LOOP_CFG[k] for k in FILTER_FIELDS}
MAP_POINTS = 20
MAP_VCTRL_LOW, MAP_VCTRL_HIGH = 0.40, 0.70
MAP_F_LOW = 0.95
MAP_MIN_DV = 0.003
# Settings of the map: FAMILIES with every max code of the table, plus other coarse codes (vco_current_min 9, max 0 /
# 8 / 15) as a lock check over the frequency bands (c13 ~0.7 GHz ... c0 ~4 GHz).
MAP_EXTRA_COARSE = (13, 11, 5, 3, 1, 0)
MAP_EXTRA_MAX = (0, 8, 15)
MAP_COLUMNS = (["time", "lut_csv"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
               + ["f_vco", "f_ref", "set_div_freq", "total_div", "set_v_ctrl", "locked", "vctrl_meas",
                  "vctrl_meas_std", "vctrl_pkpk", "vctrl_table"])

# Step 2, filter_check: the mapped points with these measured |Kvco| [Hz/V] (f_vco in FILTER_CHECK_F_RANGE [Hz]),
# each measured with every filter of FILTERS: LOOP_FILTER and one change at a time (more C1 / C2: more phase margin;
# less pump current; smaller R1).
FILTER_CHECK_PREFIX = "pll_filter_check"
FILTER_CHECK_KVCOS = (1.5e9, 4e9)
FILTER_CHECK_F_RANGE = (0.8e9, 1.3e9)
FILTERS = [dict(LOOP_FILTER)] + [dict(LOOP_FILTER, **change) for change in (
    {"set_c1": 2}, {"set_c1": 4}, {"set_c1": 7}, {"set_c2": 2}, {"set_c2": 4}, {"set_current": 3}, {"set_r1": 3})]

# Step 3, current_max_matched: every max code of FAMILIES at this measured |Kvco| [Hz/V] (max 15 peaks at ~1 GHz/V);
# a setting more than a factor MATCHED_KVCO_TOL off is skipped.
MATCHED_KVCO = 1.0e9
MATCHED_KVCO_TOL = 1.3

# Step 3b, loop_gain_sweep: one coarse / min and one f_vco (inside the lock range of every max code: c9 min 9 max 15
# only reaches ~814 MHz), max codes x every charge-pump code. set_current is binary weighted (Icp ~ code), so the loop
# gain is ~ set_current x measured |Kvco|: at 760 MHz max 0 has ~2.7 GHz/V and max 15 ~0.8 GHz/V, so max 0 at
# Icp 1-2 overlaps max 15 at Icp 4-7. Same coarse and f_vco: the same total VCO current (current-starved ring).
LOOP_GAIN_F_VCO = 760e6
LOOP_GAIN_CODES = (9, 9)  # vco_tune_coarse, vco_current_min
LOOP_GAIN_MAX_CODES = (0, 8, 12, 14, 15)
LOOP_GAIN_ICP_CODES = (1, 2, 3, 4, 5, 6, 7)


def current_max_family(coarse=9, cur_min=9, max_codes=vco_lut.LUT_MAX_CODES, vctrl=VCTRL, sample=None, lut=None,
                       csv_path=None, scope=None, scope_ch=SCOPE_CH, probe_att=PROBE_ATT, vctrl_pad="read", **kwargs):
    """Step vco_current_max through `max_codes` (default: the codes in the table) with vco_tune_coarse `coarse` and
    vco_current_min `cur_min` fixed; every setting locked at the f_vco where the table expects Vctrl = `vctrl` [V]
    (VcoLUT.frequency_at, rounded to F_STEP), so only the max code (and the frequency) changes.
    A code whose curve does not reach `vctrl`, or whose frequency the table rules (Vctrl window) reject, is skipped
    (logged). `scope`: an open pll_setup.open_rtb_scope (None: opened here when `scope_ch` is set, and closed).
    `vctrl_pad`, `kwargs`: as pll_test_vctrl.measure_pll_vctrl (lock_only=True: only lock and read Vctrl). Appends to
    `csv_path` (default a new results/pll/pll_test_current_max_<sample>_<stamp>.csv); returns the CSV path.
    A setting that fails is recorded and the test continues; a VISA error stops it.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    csv_path = csv_path or result_csv_path(sample, prefix=CSV_PREFIX)
    points = []
    for code in max_codes:
        codes = {"vco_tune_coarse": coarse, "vco_current_min": cur_min, "vco_current_max": code}
        f_vco = lut.frequency_at(codes, vctrl)
        if math.isnan(f_vco):
            logging.warning("c%d min %d max %d: no clock at Vctrl %.3f V in the table, skipped", coarse, cur_min,
                            code, vctrl)
            continue
        points.append((code, round(f_vco / F_STEP) * F_STEP))
    logging.info("current_max family c%d min %d at Vctrl ~%.3f V: %s", coarse, cur_min, vctrl,
                 ", ".join("max {} -> {:.0f} MHz".format(c, f / 1e6) for c, f in points))

    own_scope = scope is None and scope_ch is not None
    if own_scope:
        scope = pll_setup.open_rtb_scope()
    rows = []
    try:
        for i, (code, f_vco) in enumerate(points, 1):
            logging.info("=== c%d min %d, Vctrl %.2f V: %d/%d, vco_current_max %d at %.0f MHz ===", coarse, cur_min,
                         vctrl, i, len(points), code, f_vco / 1e6)
            codes = {"vco_tune_coarse": coarse, "vco_current_min": cur_min, "vco_current_max": code}
            try:
                rows.append(measure_pll_vctrl(f_vco, vctrl, sample=sample, lut=lut, csv_path=csv_path, scope=scope,
                                              scope_ch=scope_ch, probe_att=probe_att, vctrl_pad=vctrl_pad, fixed=codes,
                                              **kwargs))
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop
            except Exception:
                logging.exception("c%d min %d max %d failed, continuing", coarse, cur_min, code)
    finally:
        if own_scope:
            scope.close()
    log_summary(rows, "c%d min %d at Vctrl %.2f V" % (coarse, cur_min, vctrl))
    logging.info("current_max family written to %s", csv_path)
    return csv_path


def current_max_families(families=FAMILIES, vctrls=VCTRLS, sample=None, scope_ch=SCOPE_CH, lock_only=False, **kwargs):
    """current_max_family for every predicted Vctrl in `vctrls` [V] and every (coarse, cur_min) in `families`, all into
    one CSV, one scope connection.
    `lock_only`: only lock and read Vctrl per setting (seconds instead of ~1.5 min), into a separate
    results/pll/pll_lock_check_current_max_<sample>_<stamp>.csv: checks the whole test locks before the full run.
    `kwargs` go to current_max_family. Returns the CSV path."""
    lut = vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    csv_path = result_csv_path(sample, prefix=LOCK_CHECK_PREFIX if lock_only else CSV_PREFIX)
    scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
    try:
        for vctrl in vctrls:
            for coarse, cur_min in families:
                current_max_family(coarse, cur_min, vctrl=vctrl, sample=sample, lut=lut, csv_path=csv_path,
                                   scope=scope, scope_ch=scope_ch, lock_only=lock_only, **kwargs)
    finally:
        if scope is not None:
            scope.close()
    return csv_path


def log_summary(rows, label):
    """One log line per measured setting: max code, f_vco, lock (pad on / pad off), Vctrl predicted / measured, and
    the jitter when there is one."""
    logging.info("%s summary (max, f_vco, locked pad on / off, Vctrl pred / meas, jitter):", label)
    for row in rows:
        logging.info("  max %2d  %6.0f MHz  lock %s / %s  Vctrl %.3f / %.3f V  %s", row["vco_current_max"],
                     row["f_vco"] / 1e6, row.get("locked_peek", "-"), row.get("locked", "-"), row["vctrl_pred"],
                     row["vctrl_meas"], "%.0f ps" % row["time_jitter_trace_ps"] if "time_jitter_trace_ps" in row
                     else row["status"])


def current_max_sweep(f_vco=1e9, vctrl=VCTRL, max_codes=vco_lut.LUT_MAX_CODES, kvco=2e9, vctrl_tol=0.02, sample=None,
                      lut=None, scope_ch=SCOPE_CH, probe_att=PROBE_ATT, vctrl_pad="read", **kwargs):
    """measure_pll_vctrl for every vco_current_max code in `max_codes` (default: the codes in the table) at one
    `f_vco` [Hz] and predicted Vctrl `vctrl` [V], all into one CSV: per code the setting whose expected Vctrl is
    closest to `vctrl` (among those within 10 mV, the |Kvco| closest to `kvco` [Hz/V]); the other codes change along.
    A code without a setting within `vctrl_tol` [V] of `vctrl` is skipped (logged).
    `scope_ch` / `probe_att` / `vctrl_pad`: as pll_test_vctrl.vctrl_sweep. A setting that fails is recorded and the
    sweep continues; a VISA error stops it. `kwargs` go to measure_pll_vctrl. Returns the CSV path.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    picks = []
    for code in max_codes:
        try:
            cfg = lut.update_config_vctrl(loop_cfg(f_vco, pad_on=vctrl_pad != "off"), f_vco, vctrl, kvco=kvco,
                                          fixed={"vco_current_max": code})
        except ValueError:
            logging.warning("vco_current_max %d: no setting reaches %.1f MHz, skipped", code, f_vco / 1e6)
            continue
        op = lut.predict(cfg, f_vco)
        if abs(op["vctrl_pred"] - vctrl) > vctrl_tol:
            logging.warning("vco_current_max %d: closest setting expects Vctrl %.3f V (target %.3f V), skipped",
                            code, op["vctrl_pred"], vctrl)
            continue
        picks.append(code)
    logging.info("current_max sweep at %.1f MHz, Vctrl ~%.3f V: vco_current_max %s", f_vco / 1e6, vctrl,
                 ", ".join(str(c) for c in picks))

    csv_path = result_csv_path(sample, prefix=CSV_PREFIX)
    scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
    try:
        for i, code in enumerate(picks, 1):
            logging.info("=== current_max sweep %d/%d: vco_current_max %d ===", i, len(picks), code)
            try:
                measure_pll_vctrl(f_vco, vctrl, kvco=kvco, sample=sample, lut=lut, csv_path=csv_path, scope=scope,
                                  scope_ch=scope_ch, probe_att=probe_att, vctrl_pad=vctrl_pad,
                                  fixed={"vco_current_max": code}, **kwargs)
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop
            except Exception:
                logging.exception("vco_current_max %d failed, continuing", code)
    finally:
        if scope is not None:
            scope.close()
    logging.info("current_max sweep written to %s", csv_path)
    return csv_path


# ---------------------------------------------------------------------------------------------
# Step 1: closed-loop VCO map
# ---------------------------------------------------------------------------------------------
def map_settings(families=FAMILIES, extra_coarse=MAP_EXTRA_COARSE, extra_min=9, extra_max=MAP_EXTRA_MAX):
    """VCO codes ({LUT_FIELDS: code}) of vco_map: every max code of the table for each (coarse, cur_min) in
    `families`, plus `extra_max` codes for each coarse code in `extra_coarse` (vco_current_min `extra_min`)."""
    settings = []
    for coarse, cur_min in families:
        for code in vco_lut.LUT_MAX_CODES:
            settings.append({"vco_tune_coarse": coarse, "vco_current_min": cur_min, "vco_current_max": code})
    for coarse in extra_coarse:
        for code in extra_max:
            settings.append({"vco_tune_coarse": coarse, "vco_current_min": extra_min, "vco_current_max": code})
    return settings


def map_frequencies(lut, codes, n_points=MAP_POINTS):
    """`n_points` f_vco [Hz] for vco_map of one setting: from MAP_F_LOW x the table's f at Vctrl MAP_VCTRL_HIGH (the
    floor: only the min branch) up to the table's f at MAP_VCTRL_LOW (the top), rounded to F_STEP. Empty when the
    table has no clock there."""
    f_floor = lut.frequency_at(codes, MAP_VCTRL_HIGH)
    f_top = lut.frequency_at(codes, MAP_VCTRL_LOW)
    if math.isnan(f_floor) or math.isnan(f_top):
        return []
    return sorted({round(f / F_STEP) * F_STEP for f in np.linspace(MAP_F_LOW * f_floor, f_top, n_points)})


def vco_map(settings=None, sample=None, loop_filter=MAP_FILTER, n_points=MAP_POINTS, scope_ch=SCOPE_CH,
            probe_att=PROBE_ATT, n_read=5, lock_timeout=3.0):
    """Step 1: the VCO's f_vco-Vctrl curves measured in closed loop, instead of the lookup table (measured open loop
    on 2026-10-01 with an SMU on Vctrl, now ~5 % off; the SMU is gone).

    For every setting in `settings` (default map_settings()) and every f_vco of map_frequencies: reference
    f_vco / FB_DIV, the config loaded with the Vctrl pad on (set_v_ctrl V_CTRL_PEEK, fine for a DC reading) and the
    conservative `loop_filter` (default MAP_FILTER: locks where LOOP_FILTER does not), lock waited for, Vctrl read on
    the scope (`n_read` readings per measurement slot). No analyzer measurement. Unlocked points are kept (Vctrl then
    shows where the loop rails). Every lock is also a lock check of that setting at that frequency.
    One row per point in results/pll/pll_vco_map_<sample>_<stamp>.csv (read back with VcoMap; plotted in
    sw/tools/notebooks/pll_vco_map.ipynb). The reference, the PLL ports and the scope are closed at the end, also on
    an error. Returns the CSV path.
    """
    lut = vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    settings = settings or map_settings()
    csv_path = result_csv_path(sample, prefix=MAP_PREFIX)
    plan = [(codes, map_frequencies(lut, codes, n_points)) for codes in settings]
    logging.info("VCO map: %d settings, %d points, loop filter %s", len(plan), sum(len(f) for _, f in plan),
                 loop_filter)

    fg = pll = scope = None
    try:
        scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
        if scope is not None:
            scope.setup_dc_level(scope_ch, scale=SCOPE_SCALE, offset=SCOPE_CENTRE, timebase=SCOPE_TIMEBASE,
                                 probe_att=probe_att)
        fg = pll_setup.open_reference_generator()
        for i, (codes, freqs) in enumerate(plan, 1):
            label = "c%d min %d max %d" % (codes["vco_tune_coarse"], codes["vco_current_min"], codes["vco_current_max"])
            if not freqs:
                logging.warning("%s: no clock in the table, not mapped", label)
                continue
            logging.info("=== VCO map %d/%d: %s, %.0f-%.0f MHz ===", i, len(plan), label, freqs[0] / 1e6,
                         freqs[-1] / 1e6)
            rows = []
            for f_vco in freqs:
                cfg = dict(loop_cfg(f_vco, pad_on=True, loop_filter=loop_filter), **codes)
                pll_setup.start_reference(f_vco / FB_DIV, vpp=1.8, channel=1, load=50, fg=fg)
                if pll is None:
                    pll = pll_setup.open_pll(cfg)
                else:
                    pll_setup.load_config(pll, cfg)
                locked = pll.wait_lock(timeout=lock_timeout)
                level = scope.read_dc_level(n=n_read) if scope is not None else {}
                _, total_div = calculate_div_factor(cfg)
                rows.append(dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name,
                                 f_vco=f_vco, f_ref=f_vco / FB_DIV, set_div_freq=cfg["set_div_freq"],
                                 total_div=total_div, set_v_ctrl=cfg["set_v_ctrl"], locked=int(locked),
                                 vctrl_meas=level.get("mean", float("nan")),
                                 vctrl_meas_std=level.get("mean_std", float("nan")),
                                 vctrl_pkpk=level.get("pkpk", float("nan")),
                                 vctrl_table=table_vctrl(lut, codes, f_vco), **codes,
                                 **{k: cfg[k] for k in FILTER_FIELDS}))
            append_rows(csv_path, MAP_COLUMNS, rows)
            locked_rows = [r for r in rows if r["locked"]]
            if locked_rows:
                vctrls = [r["vctrl_meas"] for r in locked_rows if not math.isnan(r["vctrl_meas"])]  # NaN: no reading
                logging.info("%s: locked %d/%d, %.0f-%.0f MHz, Vctrl %.3f-%.3f V", label, len(locked_rows), len(rows),
                             min(r["f_vco"] for r in locked_rows) / 1e6, max(r["f_vco"] for r in locked_rows) / 1e6,
                             min(vctrls, default=float("nan")), max(vctrls, default=float("nan")))
            else:
                logging.warning("%s: locked nowhere (%d points)", label, len(rows))
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
        if scope is not None:
            scope.close()
    logging.info("VCO map written to %s", csv_path)
    return csv_path


def table_vctrl(lut, codes, f_vco):
    """The lookup table's expected Vctrl [V] for `codes` at `f_vco` (NaN where it does not reach it), to compare."""
    try:
        return lut.predict(dict(codes), f_vco)["vctrl_pred"]
    except ValueError:
        return float("nan")


class VcoMap:
    """A closed-loop VCO map (vco_map CSV): per setting the locked points (Vctrl measured, f_vco) and the |Kvco|
    between neighbouring points. `csv_path`: the map; None = the newest results/pll/pll_vco_map_<sample>_*.csv."""

    def __init__(self, csv_path=None, sample=None):
        if csv_path is None:
            found = sorted(p for p in RESULTS_DIR.glob("{}_{}_*.csv".format(MAP_PREFIX, sample or "*"))
                           if not p.stem.endswith("_traces"))
            if not found:
                raise FileNotFoundError("no VCO map in %s: run vco_map() first" % RESULTS_DIR)
            csv_path = found[-1]
        self.path = Path(csv_path)
        self.curves = {}  # (coarse, min, max) -> sorted [(vctrl, f_vco), ...], locked points with a reading
        with self.path.open(newline="") as f:
            for r in csv.DictReader(f):
                vctrl = float(r["vctrl_meas"] or "nan")
                if int(float(r["locked"] or 0)) != 1 or math.isnan(vctrl):
                    continue
                key = tuple(int(float(r[k])) for k in vco_lut.LUT_FIELDS)
                self.curves.setdefault(key, []).append((vctrl, float(r["f_vco"])))
        for pts in self.curves.values():
            pts.sort()
        logging.info("VCO map %s: %d settings with locked points", self.path.name, len(self.curves))

    def kvco_points(self, key, min_dv=MAP_MIN_DV):
        """[(f_vco, vctrl, |Kvco|), ...] of setting `key` (coarse, min, max): the midpoints between neighbouring locked
        points at least `min_dv` [V] apart (closer ones: the reading noise would dominate the slope)."""
        out = []
        pts = self.curves.get(key, [])
        i = 0
        while i < len(pts) - 1:
            j = i + 1
            while j < len(pts) and pts[j][0] - pts[i][0] < min_dv:
                j += 1
            if j == len(pts):
                break
            (v0, f0), (v1, f1) = pts[i], pts[j]
            out.append(((f0 + f1) / 2, (v0 + v1) / 2, abs(f1 - f0) / (v1 - v0)))
            i = j
        return out

    def pick(self, kvco, f_range=(0, float("inf")), keys=None):
        """The point with measured |Kvco| closest to `kvco` [Hz/V] (log scale) and f_vco inside `f_range` [Hz], among
        the settings `keys` (default all): {LUT_FIELDS: code, "f_vco", "vctrl", "kvco"}; None when there is none."""
        best = None
        for key in keys or self.curves:
            for f_vco, vctrl, k in self.kvco_points(key):
                if not f_range[0] <= f_vco <= f_range[1]:
                    continue
                err = abs(math.log(k / kvco))
                if best is None or err < best[0]:
                    best = (err, dict(zip(vco_lut.LUT_FIELDS, key), f_vco=round(f_vco / F_STEP) * F_STEP,
                                      vctrl=vctrl, kvco=k))
        return best[1] if best else None

    def kvco_at(self, key, f_vco):
        """(vctrl, |Kvco|) of setting `key` (coarse, min, max) at the mapped Kvco point closest to `f_vco` [Hz];
        (NaN, NaN) when the setting has none."""
        points = self.kvco_points(key)
        if not points:
            return float("nan"), float("nan")
        _, vctrl, kvco = min(points, key=lambda p: abs(p[0] - f_vco))
        return vctrl, kvco


# ---------------------------------------------------------------------------------------------
# Step 2: loop-filter check
# ---------------------------------------------------------------------------------------------
def filter_check(vco_map=None, kvcos=FILTER_CHECK_KVCOS, f_range=FILTER_CHECK_F_RANGE, filters=FILTERS, sample=None,
                 scope_ch=SCOPE_CH, probe_att=PROBE_ATT, **kwargs):
    """Step 2: how much of "noisy" and "does not lock" is the loop filter. For every |Kvco| in `kvcos` [Hz/V] the
    mapped point (VcoMap.pick, f_vco in `f_range`) with that measured Kvco, measured with every filter in `filters`
    (pll_test_vctrl.measure_pll_vctrl with codes and loop_filter; Vctrl pad on only to read). All into one
    results/pll/pll_filter_check_<sample>_<stamp>.csv. `vco_map`: a VcoMap (None: the newest map of `sample`).
    `kwargs` go to measure_pll_vctrl. Returns the CSV path."""
    vco_map = vco_map or VcoMap(sample=sample)
    lut = vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    csv_path = result_csv_path(sample, prefix=FILTER_CHECK_PREFIX)
    points = []
    for kvco in kvcos:
        p = vco_map.pick(kvco, f_range)
        if p is None:
            logging.warning("|Kvco| %.1f GHz/V: no mapped point in %.0f-%.0f MHz", kvco / 1e9, f_range[0] / 1e6,
                            f_range[1] / 1e6)
            continue
        logging.info("|Kvco| %.1f GHz/V: c%d min %d max %d at %.0f MHz (measured %.2f GHz/V, Vctrl %.3f V)",
                     kvco / 1e9, p["vco_tune_coarse"], p["vco_current_min"], p["vco_current_max"], p["f_vco"] / 1e6,
                     p["kvco"] / 1e9, p["vctrl"])
        points.append((kvco, p))

    scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
    try:
        for kvco, p in points:
            codes = {k: p[k] for k in vco_lut.LUT_FIELDS}
            for i, filt in enumerate(filters, 1):
                logging.info("=== filter check, |Kvco| %.1f GHz/V: filter %d/%d %s ===", kvco / 1e9, i, len(filters),
                             filt)
                try:
                    measure_pll_vctrl(p["f_vco"], float("nan"), kvco=p["kvco"], sample=sample, lut=lut,
                                      csv_path=csv_path, scope=scope, scope_ch=scope_ch, probe_att=probe_att,
                                      codes=codes, loop_filter=filt, **kwargs)
                except pyvisa.VisaIOError:
                    raise  # instrument connection lost: stop
                except Exception:
                    logging.exception("filter %s failed, continuing", filt)
    finally:
        if scope is not None:
            scope.close()
    logging.info("Filter check written to %s", csv_path)
    return csv_path


# ---------------------------------------------------------------------------------------------
# Step 3: vco_current_max at matched measured Kvco
# ---------------------------------------------------------------------------------------------
def current_max_matched(vco_map=None, kvco=MATCHED_KVCO, families=FAMILIES, f_range=(0, float("inf")),
                        kvco_tol=MATCHED_KVCO_TOL, loop_filter=None, sample=None, scope_ch=SCOPE_CH,
                        probe_att=PROBE_ATT, **kwargs):
    """Step 3: vco_current_max compared at the same measured |Kvco|. For every max code of every (coarse, cur_min)
    in `families` the mapped point of that setting with measured Kvco closest to `kvco` [Hz/V] (VcoMap.pick per
    setting, f_vco in `f_range`); a setting whose closest Kvco is more than a factor `kvco_tol` off is skipped
    (logged: max 15 hardly reaches 1 GHz/V). Measured with pll_test_vctrl.measure_pll_vctrl (codes; `loop_filter`:
    the one step 2 found, None: LOOP_FILTER; Vctrl pad on only to read) into one
    results/pll/pll_test_current_max_<sample>_<stamp>.csv (pll_test_current_max.ipynb; vctrl_target NaN,
    kvco_request = the measured |Kvco| of the picked point). `kwargs` go to measure_pll_vctrl. Returns the CSV
    path."""
    vco_map = vco_map or VcoMap(sample=sample)
    lut = vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    csv_path = result_csv_path(sample, prefix=CSV_PREFIX)
    points = []
    for coarse, cur_min in families:
        for code in vco_lut.LUT_MAX_CODES:
            p = vco_map.pick(kvco, f_range, keys=[(coarse, cur_min, code)])
            if p is None or abs(math.log(p["kvco"] / kvco)) > math.log(kvco_tol):
                logging.warning("c%d min %d max %d: no mapped point near %.2f GHz/V (closest %s), skipped", coarse,
                                cur_min, code, kvco / 1e9, "%.2f GHz/V" % (p["kvco"] / 1e9) if p else "none")
                continue
            points.append(p)
    logging.info("current_max at |Kvco| ~%.2f GHz/V: %d settings", kvco / 1e9, len(points))

    scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
    rows = []
    try:
        for i, p in enumerate(points, 1):
            logging.info("=== current_max matched %d/%d: c%d min %d max %d at %.0f MHz (|Kvco| %.2f GHz/V) ===", i,
                         len(points), p["vco_tune_coarse"], p["vco_current_min"], p["vco_current_max"],
                         p["f_vco"] / 1e6, p["kvco"] / 1e9)
            codes = {k: p[k] for k in vco_lut.LUT_FIELDS}
            try:
                rows.append(measure_pll_vctrl(p["f_vco"], float("nan"), kvco=p["kvco"], sample=sample, lut=lut,
                                              csv_path=csv_path, scope=scope, scope_ch=scope_ch, probe_att=probe_att,
                                              codes=codes, loop_filter=loop_filter, **kwargs))
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop
            except Exception:
                logging.exception("c%d min %d max %d failed, continuing", p["vco_tune_coarse"], p["vco_current_min"],
                                  p["vco_current_max"])
    finally:
        if scope is not None:
            scope.close()
    log_summary(rows, "current_max at |Kvco| %.2f GHz/V" % (kvco / 1e9))
    logging.info("current_max matched written to %s", csv_path)
    return csv_path


def loop_gain_sweep(vco_map=None, f_vco=LOOP_GAIN_F_VCO, coarse=LOOP_GAIN_CODES[0], cur_min=LOOP_GAIN_CODES[1],
                    max_codes=LOOP_GAIN_MAX_CODES, icp_codes=LOOP_GAIN_ICP_CODES, loop_filter=None, sample=None,
                    scope_ch=SCOPE_CH, probe_att=PROBE_ATT, **kwargs):
    """Step 3b: VCO noise or loop gain. One coarse / min and one `f_vco` [Hz] (the same ring length and total VCO
    current), every max code in `max_codes` with every charge-pump code in `icp_codes` (set_current, binary weighted:
    loop gain ~ set_current x |Kvco|). If the jitter of all max codes falls on one curve against set_current x Kvco, it
    is the loop gain; if max 14 / 15 stay worse at the same loop gain, it is the VCO. `loop_filter`: the other filter
    fields (step 2; None: LOOP_FILTER), set_current replaced per point. kvco_request = the measured |Kvco| of the map
    at `f_vco` (VcoMap.kvco_at). Measured with pll_test_vctrl.measure_pll_vctrl (Vctrl pad on only to read) into one
    results/pll/pll_test_current_max_<sample>_<stamp>.csv. `kwargs` go to measure_pll_vctrl. Returns the CSV path."""
    vco_map = vco_map or VcoMap(sample=sample)
    lut = vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    csv_path = result_csv_path(sample, prefix=CSV_PREFIX)
    base_filter = dict(loop_filter or LOOP_FILTER)
    settings = []
    for code in max_codes:
        vctrl, kvco = vco_map.kvco_at((coarse, cur_min, code), f_vco)
        logging.info("c%d min %d max %d at %.0f MHz: mapped Vctrl %.3f V, |Kvco| %.2f GHz/V", coarse, cur_min, code,
                     f_vco / 1e6, vctrl, kvco / 1e9)
        settings.append((code, kvco))
    logging.info("loop gain sweep: %d max codes x %d Icp codes, filter %s", len(max_codes), len(icp_codes),
                 base_filter)

    scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
    rows = []
    n = len(settings) * len(icp_codes)
    try:
        for i, ((code, kvco), icp) in enumerate(((s, icp) for s in settings for icp in icp_codes), 1):
            logging.info("=== loop gain %d/%d: c%d min %d max %d, set_current %d (Icp x |Kvco| ~%.1f) ===", i, n,
                         coarse, cur_min, code, icp, icp * kvco / 1e9)
            codes = dict(zip(vco_lut.LUT_FIELDS, (coarse, cur_min, code)))
            try:
                rows.append(measure_pll_vctrl(f_vco, float("nan"), kvco=kvco, sample=sample, lut=lut,
                                              csv_path=csv_path, scope=scope, scope_ch=scope_ch, probe_att=probe_att,
                                              codes=codes, loop_filter=dict(base_filter, set_current=icp), **kwargs))
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop
            except Exception:
                logging.exception("max %d, set_current %d failed, continuing", code, icp)
    finally:
        if scope is not None:
            scope.close()
    log_summary(rows, "loop gain sweep at %.0f MHz" % (f_vco / 1e6))
    logging.info("loop gain sweep written to %s", csv_path)
    return csv_path


def start_log_file():
    """Also write the log to results/logs/pll_test_current_max_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_test_current_max_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():  # core in reset: no pollution
        # PLL supply: fixed on the board, always on (no SMU since 2026-10-19): power columns stay NaN
        # RTB2004 channel 1 on the Vctrl pin header (10:1 passive probe), pad on only to read Vctrl.

        # Step 1: closed-loop VCO map. c9 min 9 and c7 min 9 with every max code of the table, plus coarse 13, 11, 5,
        # 3, 1, 0 (min 9, max 0 / 8 / 15): 36 settings x 20 frequencies, conservative filter MAP_FILTER, Vctrl pad on,
        # no analyzer (~3 s per point, ~40 min). Plotted in sw/tools/notebooks/pll_vco_map.ipynb.
        # vco_map(sample="S5", scope_ch=1, probe_att=10)

        # Step 2: loop-filter check on the newest map (measured |Kvco| ~1.5 and ~4 GHz/V near 1 GHz, 8 filters each;
        # ~25 min). Pick the filter for step 3 from it.
        # (done 2026-10-20 19:27, pll_filter_check_S5_20261020_192704: C1 7 halves the jitter at 1.5 GHz/V, C2: none;
        # at 4 GHz/V only Icp 3 locks without the pad: Icp x |Kvco| above ~12 code GHz/V is unstable)
        # filter_check(sample="S5", scope_ch=1, probe_att=10)

        # Step 3: every max code of c9 min 9 / c7 min 9 at measured |Kvco| ~1 GHz/V (~30 min); loop_filter: from step 2
        # current_max_matched(kvco=1e9, loop_filter=None, sample="S5", scope_ch=1, probe_att=10)

        # Step 3b: c9 min 9 at 760 MHz, max 0 / 8 / 12 / 14 / 15 x set_current 1-7 (35 points, ~60 min): jitter against
        # loop gain (set_current x measured |Kvco|); loop_filter: from step 2 (set_current is swept)
        loop_gain_sweep(loop_filter=dict(LOOP_FILTER, set_c1=7), sample="S5", scope_ch=1, probe_att=10)

        # Earlier tests (operating point predicted by the table):
        # lock check / full test at predicted Vctrl 0.54 and 0.60 V (lock check done 2026-10-20 15:52,
        # pll_lock_check_current_max_S5_20261020_155245: at 0.60 V max 0-10 only lock with the Vctrl pad on)
        # current_max_families(FAMILIES, sample="S5", scope_ch=1, probe_att=10, lock_only=True)
        # current_max_families(FAMILIES, sample="S5", scope_ch=1, probe_att=10)
        # 1 GHz, per max code the table's setting at ~0.54 V
        # (done 2026-10-20 15:00, pll_test_current_max_S5_20261020_150031)
        # current_max_sweep(1e9, vctrl=0.54, kvco=2e9, sample="S5", scope_ch=1, probe_att=10)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Top script for the open-loop VCO tests of the Pomelo PLL. The measurement bench lives in lib/vco_measure.py
# (SMU on the Vctrl pad, scope on the divided output, adaptive divider) and the lookup table with
# configure_vco(f, kvco) in lib/vco_lut.py; this file only runs tests on top of them.
#
# Tests:
#   test_lut_pick(f, kvco, sample)       # configure_vco from the lookup table, sweep Vctrl, compare with the table
#   test_lut_range(targets, sample)      # the same for a list of (f, kvco) targets, one CSV for all
#                                        # (plotted in sw/tools/notebooks/LUT_test.ipynb)
#

import csv
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from sw.lib import vco_lut, vco_measure
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_settings import VCO_CHARAC_CFG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Columns of the LUT check CSV. `kind`: table / operating / kvco for measured points, "summary" for the
# per-target verdict (f_vco = frequency at the predicted Vctrl, dev_pct = worst deviation from the table),
# "unreachable" when the lookup table has no setting for the target.
CHECK_COLUMNS = (["lut_csv", "f_target", "kvco_target", "vctrl_pred", "kvco_pred", "kvco_meas", "kind", "f_table",
                  "dev_pct", "result"] + list(vco_lut.LUT_FIELDS) + list(vco_measure.POINT_COLUMNS))
# Default targets for test_lut_range: log-spaced over the VCO range, no Kvco preference (central Vctrl).
LUT_TEST_TARGETS = [(f, None) for f in (50e6, 100e6, 200e6, 300e6, 500e6, 700e6, 1e9, 1.5e9, 2e9, 3e9, 5e9, 7e9,
                                        10e9)]


def table_curve(rows, key):
    """(vctrl, f_vco) arrays of one (coarse, min, max) setting in the lookup table, sorted by Vctrl, with clock."""
    pts = sorted((r["vctrl"], r["f_vco"]) for r in rows
                 if tuple(r[k] for k in vco_lut.LUT_FIELDS) == key and not np.isnan(r["f_vco"]))
    v, f = (np.array(x) for x in zip(*pts)) if pts else (np.array([]), np.array([]))
    return v, f


def check_csv_path(sample):
    vco_lut.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return vco_lut.RESULTS_DIR / "vco_lut_check_{}_{}.csv".format(
        sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def append_rows(csv_path, rows):
    """Append rows to the check CSV (header written when the file is new)."""
    new = not Path(csv_path).exists() or Path(csv_path).stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CHECK_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def test_lut_pick(f_vco, kvco=None, sample=None, lut_csv=None, csv_path=None, dv=0.025, f_tol=0.03, kvco_tol=0.25,
                  scope_ch=1, probe_att=10, settle=0.3, n_read=10):
    """Check a lookup-table pick on the chip: configure_vco, then sweep Vctrl and compare with the table.

    Measured points: the table's Vctrl points of the picked setting, plus the predicted operating Vctrl and
    `dv` either side of it (for the local Kvco). PASS when every point is within `f_tol` (relative) of the
    table (interpolated between table points), the frequency at the operating Vctrl within `f_tol` of
    `f_vco`, and the measured local |Kvco| within `kvco_tol` of the predicted one.
    Appends to `csv_path` (default a new results/vco/vco_lut_check_<sample>_<stamp>.csv); returns True on PASS.
    """
    csv_path = csv_path or check_csv_path(sample)
    lut_csv = lut_csv or vco_lut.newest_lut(sample)
    rows = vco_lut.read_lut(lut_csv)
    target = dict(lut_csv=Path(lut_csv).name, f_target=f_vco, kvco_target=kvco)
    try:
        pick, pll = vco_lut.configure_vco(f_vco, kvco, sample=sample, lut_csv=lut_csv)
    except ValueError as e:  # no setting reaches f_vco
        logging.warning("LUT check %.1f MHz: %s", f_vco / 1e6, e)
        append_rows(csv_path, [dict(target, kind="unreachable", result="UNREACHABLE")])
        return False
    key = tuple(pick[k] for k in vco_lut.LUT_FIELDS)
    codes = dict(zip(vco_lut.LUT_FIELDS, key))
    target.update(vctrl_pred=pick["vctrl"], kvco_pred=pick["kvco"], **codes)
    v_tab, f_tab = table_curve(rows, key)
    vdd = vco_measure.load_instr_cfg()["smu_vctrl"]["args"]["v_max"]
    v_op = round(pick["vctrl"], 4)
    v_lo, v_hi = round(max(v_op - dv, 0.0), 4), round(min(v_op + dv, vdd), 4)  # for the local Kvco
    vctrls = sorted(set(float(v) for v in np.round(v_tab, 4)) | {v_op, v_lo, v_hi})

    logging.info("LUT check: %.1f MHz -> coarse %d, min %d, max %d, predicted Vctrl %.3f V, |Kvco| %.0f MHz/V; "
                 "sweeping %s V (table %s)", f_vco / 1e6, *key, v_op, pick["kvco"] / 1e6, list(vctrls),
                 Path(lut_csv).name)

    measured, out = {}, []
    try:
        # The same config configure_vco loaded, with the start divider the measurement adapts from.
        cfg = dict(VCO_CHARAC_CFG, **codes)
        vco_measure.reset_divider(cfg)
        vco_measure.load_vco(pll, cfg)
        smu, scope = vco_measure.open_vco_instruments(vctrls[0], scope_ch, probe_att)
        try:
            for i, v in enumerate(vctrls):
                vco_measure.set_vctrl(smu, v, settle)
                point = vco_measure.measure_vco(pll, smu, scope, scope_ch, cfg, v, settle, n_read=n_read,
                                                fit_passes=2 if i == 0 else 1)
                f_t = float(np.interp(v, v_tab, f_tab)) if len(v_tab) else np.nan
                dev = (point["f_vco"] / f_t - 1) * 100
                kind = "operating" if v == v_op else ("table" if np.isclose(v_tab, v).any() else "kvco")
                measured[v] = point["f_vco"]
                out.append(dict(point, kind=kind, f_table=f_t, dev_pct=dev, **target))
                logging.info("  Vctrl %.3f V (%s): measured %.2f MHz, table %.2f MHz, %+.2f %%",
                             v, kind, point["f_vco"] / 1e6, f_t / 1e6, dev)
        finally:
            smu.close()  # back to 0 V, output off
            scope.close()
    finally:
        pll.close()

    # Verdicts.
    devs = [abs(measured[v] / float(np.interp(v, v_tab, f_tab)) - 1) for v in vctrls if not np.isnan(measured[v])]
    f_op = measured[v_op]
    kvco_meas = abs(measured[v_hi] - measured[v_lo]) / (v_hi - v_lo)  # NaN when either point had no clock
    ok_points = bool(devs) and max(devs) <= f_tol and len(devs) == len(vctrls)
    ok_op = abs(f_op / f_vco - 1) <= f_tol
    ok_kvco = abs(kvco_meas / pick["kvco"] - 1) <= kvco_tol
    ok = ok_points and ok_op and ok_kvco
    logging.info("%s: table vs measured, worst %.2f %% over %d/%d points (tolerance %.0f %%)",
                 "PASS" if ok_points else "FAIL", 100 * max(devs) if devs else np.nan, len(devs), len(vctrls),
                 100 * f_tol)
    logging.info("%s: at the predicted Vctrl %.3f V: %.2f MHz vs target %.2f MHz (%+.2f %%)",
                 "PASS" if ok_op else "FAIL", v_op, f_op / 1e6, f_vco / 1e6, (f_op / f_vco - 1) * 100)
    logging.info("%s: local |Kvco| %.0f MHz/V vs predicted %.0f MHz/V (%+.0f %%, tolerance %.0f %%)",
                 "PASS" if ok_kvco else "FAIL", kvco_meas / 1e6, pick["kvco"] / 1e6,
                 (kvco_meas / pick["kvco"] - 1) * 100, 100 * kvco_tol)
    out.append(dict(target, kind="summary", vctrl_set=v_op, f_vco=f_op, kvco_meas=kvco_meas,
                    dev_pct=100 * max(devs) if devs else np.nan, result="PASS" if ok else "FAIL"))
    for r in out:
        r["kvco_meas"] = kvco_meas
    append_rows(csv_path, out)
    logging.info("LUT check written to %s", csv_path)
    return ok


def test_lut_range(targets=LUT_TEST_TARGETS, sample=None, lut_csv=None, **kwargs):
    """test_lut_pick for every (f_vco, kvco) in `targets`, all into one CSV; logs a PASS/FAIL overview."""
    csv_path = check_csv_path(sample)
    lut_csv = lut_csv or vco_lut.newest_lut(sample)
    results = []
    for f_vco, kvco in targets:
        results.append((f_vco, test_lut_pick(f_vco, kvco, sample=sample, lut_csv=lut_csv, csv_path=csv_path,
                                             **kwargs)))
    logging.info("LUT check overview (%s):", Path(lut_csv).name)
    for f_vco, ok in results:
        logging.info("  %8.1f MHz: %s", f_vco / 1e6, "PASS" if ok else "FAIL or unreachable")
    logging.info("%d/%d targets passed; results in %s", sum(ok for _, ok in results), len(results), csv_path)
    return csv_path


def start_log_file():
    """Also write the log to results/logs/vco_test_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "vco_test_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # One lookup-table check: 1 GHz with |Kvco| ~1 GHz/V from the S5 table
        # test_lut_pick(1.0e9, 1.0e9, sample="S5")

        # Lookup-table check over the whole VCO range (LUT_TEST_TARGETS: 50 MHz .. 10 GHz, central Vctrl),
        # plotted in sw/tools/notebooks/LUT_test.ipynb
        test_lut_range(sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

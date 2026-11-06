# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Locking range of the PLL for a loop filter (default: pll_settings.LOOP_FILTER of the spectrum scripts). The reference
# (33600A) is swept; per reference frequency the VCO is set up for f_vco = FB_DIV x f_ref with codes from the lookup
# table (lib/vco_lut.py, VcoLUT) for the requested |Kvco| (kvco="max": the highest the table offers at that frequency,
# which gave the lowest jitter in the Kvco sweeps; None: the setting with its Vctrl closest to the window centre, as in
# the first run of 2026-10-13, which leaves |Kvco| to chance), the config is loaded and the lock bit read. Per point:
#   - lock bit after lock_timeout, and again after the measurement (locked_end);
#   - PLL supply voltage, current and power when a supply SMU is passed (`supply`); NaN otherwise (since 2026-10-19
#     the PLL supply is fixed on the board, no SMU);
#   - when locked: the output pad (VCO / 2**set_div_freq, <= PAD_F_MAX) on the R&S FSV with
#     lib/pll_spectrum.measure_output: carrier and divider check (f_vco_meas = carrier x N, so a "lock" on a wrong
#     frequency shows), full phase-noise curve with spurs, averaged spectrum, RMS jitter (also over
#     COMMON_BAND, the same band for every point).
# Points the lookup table has no VCO setting for inside the Vctrl window: above what its fastest setting gives at the
# top of the window (the top of the range, or a gap in it), that fastest setting is tried (vco_pick "fastest" instead
# of "lut"; vctrl_pred / kvco_pred NaN where the table does not reach f_vco at all); below, the point is recorded with
# status "no_vco_setting" and not configured.
#
# Results:
#   results/pll/pll_range_<sample>_<stamp>.csv          one row per reference frequency
#   results/pll/pll_range_<sample>_<stamp>_traces.csv   averaged spectrum + phase-noise traces per reference frequency
#
# Tests:
#   range_sweep(f_refs, sample)   # every reference frequency in f_refs, one CSV
#   range_sweep([f_ref], sample, cfg_overrides=dict(...), csv_path=...)   # one point with forced config fields
#

import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8, DEFAULT_FILTER, FILTER_FIELDS, LOOP_FILTER
from sw.lib.pll_spectrum import (FB_DIV, OUTPUT_COLUMNS, RESULTS_DIR, TRACE_FIELDS, append_rows, kvco_target_for,
                                 measure_output, offsets_for, pad_divider, trace_csv_path, trace_rows)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Reference frequencies of range_sweep: 1-100 MHz log-spaced, 41 points (~12 % steps; VCO 128 MHz - 12.8 GHz), up to
# the 33600A limit. The S5 table of 2026-10-01 has settings inside the Vctrl window for VCO ~55 MHz - 9 GHz, so the
# lock, not the table, should set the edges; points above the table get its fastest setting (vco_pick "fastest").
# ~2 min per locked point.
REF_SWEEP = tuple(np.geomspace(1e6, 100e6, 41))
# Quick test: VCO 400 MHz - 6.4 GHz in octaves and 12 GHz (near the ~12.5 GHz top of the fastest setting), 6 points;
# ~10 min per sweep.
REF_QUICK = tuple(f_vco / FB_DIV for f_vco in (400e6, 800e6, 1.6e9, 3.2e9, 6.4e9, 12e9))
# Band integrated for every point, so the jitter can be compared: the pad is always 50-100 MHz (pad_divider), so
# 10 MHz fits everywhere. The same band as pll_spectrum_kvco.COMMON_BAND.
COMMON_BAND = (1e3, 1e7)

RESULT_COLUMNS = (["time", "lut_csv", "f_ref", "f_vco", "kvco_request", "kvco_target", "vco_pick", "cfg_overrides"]
                  + list(vco_lut.LUT_FIELDS)
                  + list(FILTER_FIELDS)
                  + ["vctrl_pred", "kvco_pred", "kvco_min", "kvco_max", "set_div_freq", "total_div", "locked",
                     "locked_end"] + OUTPUT_COLUMNS + list(pll_setup.SUPPLY_COLUMNS))
TRACE_COLUMNS = ["f_ref", "f_vco"] + TRACE_FIELDS


def loop_cfg(f_vco, loop_filter=LOOP_FILTER):
    """Closed-loop config (CFG_REF8 with the filter fields of `loop_filter`, internal Vctrl) on the direct
    output (no external divider: pad = PLL output), divided inside the PLL to at most PAD_F_MAX on the pad
    (pll_spectrum.pad_divider). The VCO codes are added by VcoLUT.update_config."""
    return dict(CFG_REF8, **loop_filter, pll_clk_o_en=1, set_div_freq=pad_divider(f_vco))


def fastest_cfg(lut, f_vco, loop_filter=LOOP_FILTER):
    """Closed-loop config with the fastest VCO setting of the table (VcoLUT.fastest_setting) for a frequency the table
    has no setting for inside the Vctrl window, when f_vco lies above what that setting gives at the top of the window
    (the top of the range or a gap in it, where the fastest setting can only help). None below that (the bottom of the
    range: the fastest setting would run even further off)."""
    cfg = dict(loop_cfg(f_vco, loop_filter), **lut.fastest_setting())
    vctrls, freqs = lut.curve(cfg)
    if f_vco <= np.interp(lut.window[1], vctrls, freqs):
        return None
    return cfg


def range_sweep(f_refs=REF_SWEEP, kvco="max", loop_filter=LOOP_FILTER, sample=None, lut=None, supply=None, span=5e6,
                spectrum_averages=20, n_averages=10, lock_timeout=3.0, common_band=COMMON_BAND, cfg_overrides=None,
                csv_path=None, measure=True, hold=5.0):
    """For every reference frequency in `f_refs` [Hz]: VCO codes from the lookup table for f_vco = FB_DIV x f_ref and
    |Kvco| `kvco` (pll_spectrum.kvco_target_for: [Hz/V], "max", "middle", "min" or None = central Vctrl),
    with the loop filter `loop_filter` (FILTER_FIELDS dict, e.g. pll_settings.LOOP_FILTER or DEFAULT_FILTER),
    load the config, wait for lock (`lock_timeout` [s]), record the PLL supply power and, when locked, measure the pad
    with measure_output (full curve with spurs, spectrum, jitter, also over `common_band`).

    No analyzer measurement when the PLL did not lock (status "not_locked"). Without a table setting for f_vco the
    fastest setting is tried where it can help (fastest_cfg), else the point is not configured (status
    "no_vco_setting"). A point that fails is recorded and the sweep continues; a VISA error stops it. The reference
    (33600A) is started here and turned off at the end, the FPGA link closed; the PLL supply `supply`
    (pll_setup.pll_supply) must already be on. `lut`: the lookup table (vco_lut.VcoLUT); None = the newest
    table of `sample`. Appends one row per point to `csv_path` (None: a new results/pll/pll_range_<sample>_<stamp>.csv)
    and the traces to <stem>_traces.csv; returns the CSV path.

    `cfg_overrides`: config fields (pll_command_api names) forced on every point after the VCO pick, to debug a
    point, e.g. dict(vco_tune_coarse=0, vco_current_min=10, vco_current_max=6) or dict(set_current=3). With all
    three VCO codes (vco_lut.LUT_FIELDS) in it the table is not used for the pick (vco_pick "manual"). The overrides
    are recorded in the column cfg_overrides, the resulting codes and filter in their own columns.

    `measure` False: lock check only, no analyzer (a quick debug sweep): when locked, wait `hold` [s] and read the lock
    bit again (locked_end); status "lock_only".
    """
    lut = lut or vco_lut.VcoLUT(sample=sample)
    cfg_overrides = dict(cfg_overrides or {})
    manual_vco = set(vco_lut.LUT_FIELDS) <= set(cfg_overrides)
    csv_path = csv_path or result_csv_path(sample)
    if cfg_overrides:
        logging.info("Config overrides on every point: %s", cfg_overrides)
    logging.info("Range sweep: %d reference frequencies %.3f-%.3f MHz (VCO %.1f-%.1f MHz), |Kvco| %s, loop filter %s",
                 len(f_refs), min(f_refs) / 1e6, max(f_refs) / 1e6, FB_DIV * min(f_refs) / 1e6,
                 FB_DIV * max(f_refs) / 1e6, kvco, loop_filter)

    fg = pll = None
    try:
        fg = pll_setup.open_reference_generator()
        pll = pll_setup.connect()  # one link; every point loads its own config on it
        for i, f_ref in enumerate(f_refs, 1):
            f_vco = FB_DIV * f_ref
            logging.info("=== Range sweep %d/%d: ref %.4f MHz -> VCO %.1f MHz ===", i, len(f_refs), f_ref / 1e6,
                         f_vco / 1e6)
            row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, f_ref=f_ref,
                       f_vco=f_vco, kvco_request=kvco, cfg_overrides=repr(cfg_overrides) if cfg_overrides else "",
                       status="error", **loop_filter)
            traces = []
            try:
                try:
                    if manual_vco:
                        cfg = loop_cfg(f_vco, loop_filter)
                        target = kvco_min = kvco_max = float("nan")
                        row["vco_pick"] = "manual"
                    else:
                        target, kvco_min, kvco_max = kvco_target_for(lut, f_vco, kvco)
                        cfg = lut.update_config(loop_cfg(f_vco, loop_filter), f_vco, target)
                        row["vco_pick"] = "lut"
                except ValueError as e:
                    cfg = fastest_cfg(lut, f_vco, loop_filter)
                    if cfg is None:
                        logging.warning("No VCO setting for %.1f MHz: not configured (%s)", f_vco / 1e6, e)
                        row["status"] = "no_vco_setting"
                        continue  # the finally block still writes the row
                    target = kvco_min = kvco_max = float("nan")
                    row["vco_pick"] = "fastest"
                    logging.warning("No VCO setting for %.1f MHz inside the Vctrl window: trying the fastest setting "
                                    "(coarse %d, min %d, max %d)", f_vco / 1e6, cfg["vco_tune_coarse"],
                                    cfg["vco_current_min"], cfg["vco_current_max"])
                if cfg_overrides:
                    cfg = dict(cfg, **cfg_overrides)
                    row.update({k: cfg[k] for k in FILTER_FIELDS})  # the filter as loaded
                    logging.info("With overrides: coarse %d, min %d, max %d, Icp %d C1 %d C2 %d R1 %d, set_div_freq %d",
                                 cfg["vco_tune_coarse"], cfg["vco_current_min"], cfg["vco_current_max"],
                                 cfg["set_current"], cfg["set_c1"], cfg["set_c2"], cfg["set_r1"],
                                 cfg["set_div_freq"])
                _, total_div = calculate_div_factor(cfg)
                try:
                    op = lut.predict(cfg, f_vco)
                except ValueError:  # the fastest setting does not reach f_vco in the table at all
                    op = dict(vctrl_pred=float("nan"), kvco_pred=float("nan"))
                row.update(vco_lut.vco_codes(cfg), **op, kvco_target=target, kvco_min=kvco_min, kvco_max=kvco_max,
                           set_div_freq=cfg["set_div_freq"], total_div=total_div)

                pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50, fg=fg)
                pll_setup.load_config(pll, cfg)
                locked = pll.wait_lock(timeout=lock_timeout)
                row["locked"] = int(locked)
                logging.info("PLL %s at %.1f MHz (ref %.4f MHz x %d), Vctrl ~%.3f V, |Kvco| %.0f MHz/V; /%d inside the "
                             "PLL -> pad %.4f MHz", "LOCKED" if locked else "NOT LOCKED", f_vco / 1e6, f_ref / 1e6,
                             FB_DIV, row["vctrl_pred"], row["kvco_pred"] / 1e6, total_div, f_vco / total_div / 1e6)
                row.update(pll_setup.measure_pll_supply(supply, label="ref %.4f MHz" % (f_ref / 1e6)))
                if not locked:
                    # No lock: no carrier at f_vco / N either; the analyzer would only measure noise
                    logging.warning("Not locked: not measured")
                    row["status"] = "not_locked"
                    continue
                if not measure:
                    time.sleep(hold)
                    row["locked_end"] = pll.read_lock()
                    row["status"] = "lock_only"
                    logging.info("Lock bit after %.1f s: %s (lock check only, not measured)", hold, row["locked_end"])
                    continue

                meas, traces = measure_output(f_vco, total_div, offsets_for(f_vco / total_div), n_averages=n_averages,
                                              span=span, spectrum_averages=spectrum_averages, common_band=common_band)
                row.update(meas)
                row["locked_end"] = pll.read_lock()  # still locked after the measurement (None: no answer)
                logging.info("Lock bit after the measurement: %s", row["locked_end"])
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop, outputs off in the finally block below
            except Exception:
                logging.exception("ref %.4f MHz failed, continuing", f_ref / 1e6)
            finally:
                append_rows(csv_path, RESULT_COLUMNS, [row])
                append_rows(trace_csv_path(csv_path), TRACE_COLUMNS, trace_rows(traces, f_ref=f_ref, f_vco=f_vco))
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
    logging.info("Range sweep written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return csv_path


# Edges of the lock range (2026-11-03), lock check only (range_sweep measure=False). Filters: DEFAULT_FILTER with the
# fields of each entry forced (cfg_overrides); a higher code = more current / capacitance / resistance (the low-end
# debug of 2026-11-03, pll_range_lowend_S5_20261103_163916: Icp 0 locks VCO 200 MHz, Icp 3 not; LOOP_FILTER, Icp 7,
# never below 1 GHz).
# Floor: VCO 50-200 MHz (ref 0.39-1.56 MHz); the VCO reaches ~50 MHz open loop, the table's window ~55 MHz. The weak
# loops that locked 200 MHz, plus C2 7.
FLOOR_VCO = (50e6, 60e6, 70e6, 85e6, 100e6, 128e6, 160e6, 200e6)
FLOOR_FILTERS = [
    dict(set_current=0),
    dict(set_current=0, set_c1=7),
    dict(set_current=0, set_c1=7, set_c2=7),
    dict(set_current=0, set_c1=7, set_r1=1),
]
FLOOR_KVCO = (2e9, "min")
# Upper end: VCO 11.4-12.5 GHz (ref 89-98 MHz) on the table's fastest setting (c0 min 0 max 0, ~12.5 GHz at Vctrl 0
# open loop): 11.4 GHz locked on 2026-10-13, 12 GHz locked with LOOP_FILTER on 2026-11-03 but lost the lock during the
# measurement. A strong loop is safe at these references and makes up for the flattening Kvco; a higher PLL supply
# speeds up the VCO and the divider. Longer hold to see whether the lock holds.
UPPER_VCO = (11.4e9, 11.7e9, 12.0e9, 12.25e9, 12.5e9)
UPPER_FILTERS = [
    dict(LOOP_FILTER),  # Icp 7 C1 0 C2 0 R1 7
    dict(),  # DEFAULT_CFG filter: Icp 3 C1 3 C2 3 R1 3
    dict(set_current=7),  # Icp 7 C1 3 C2 3 R1 3
    dict(set_current=7, set_r1=7),  # Icp 7 C1 3 C2 3 R1 7
]
UPPER_VDDS = (0.75, 0.80, 0.85)  # [V] PLL supply (PllSupplyChannel, inside its V_LIMITS)
UPPER_HOLD = 15.0  # [s] between the two lock reads


def floor_search(supply=None, sample="S5"):
    """Lock check (no analyzer) at FLOOR_VCO for every |Kvco| of FLOOR_KVCO and filter of FLOOR_FILTERS, one CSV
    results/pll/pll_range_floor_<sample>_<stamp>.csv; ~10 s per point. Returns the CSV path."""
    csv_path = result_csv_path(sample, prefix="pll_range_floor")
    f_refs = [f_vco / FB_DIV for f_vco in FLOOR_VCO]
    for kvco in FLOOR_KVCO:
        for overrides in FLOOR_FILTERS:
            range_sweep(f_refs, kvco=kvco, loop_filter=DEFAULT_FILTER, sample=sample, supply=supply,
                        cfg_overrides=overrides, csv_path=csv_path, measure=False)
    return csv_path


def upper_search(supply, sample="S5"):
    """Lock check (no analyzer, UPPER_HOLD s between the lock reads) at UPPER_VCO for every PLL supply of UPPER_VDDS
    (`supply`: PllSupplyChannel; set here, back to its nominal at the end, also on an error) and filter of
    UPPER_FILTERS, one CSV results/pll/pll_range_upper_<sample>_<stamp>.csv (pll_vdd: the measured supply);
    ~10-25 s per point. Returns the CSV path."""
    csv_path = result_csv_path(sample, prefix="pll_range_upper")
    f_refs = [f_vco / FB_DIV for f_vco in UPPER_VCO]
    try:
        for vdd in UPPER_VDDS:
            supply.set(vdd)
            for overrides in UPPER_FILTERS:
                range_sweep(f_refs, kvco=2e9, loop_filter=DEFAULT_FILTER, sample=sample, supply=supply,
                            cfg_overrides=overrides, csv_path=csv_path, measure=False, hold=UPPER_HOLD)
    finally:
        supply.set(supply.nominal)  # what follows runs at the nominal supply again
    return csv_path


# Loop filter and |Kvco| per reference frequency (FB_DIV fixed: the loop must slow down with f_ref), from the lock
# checks of 2026-11-03 (pll_range_lowend_S5_20261103_163916, pll_range_floor_S5_20261103_165653,
# pll_range_upper_S5_20261103_170454) and the range sweeps of 2026-10-13; lock only, the jitter decides the
# breakpoints later:
#   - VCO 128 MHz (ref 1.0 MHz): holds lock only with Icp 0 + C1 7 at the table's lowest |Kvco| (~280 MHz/V);
#     100 MHz locks and loses it again, 85 MHz and below never (the weakest loop the codes offer);
#   - 160-200 MHz: Icp 0 + C1 7 at either |Kvco|; 400 MHz (3.1 MHz): Icp 0 / Icp 1 / C1 7, the DEFAULT_CFG filter
#     not; 800 MHz (6.25 MHz): DEFAULT_CFG, LOOP_FILTER not, the lowest |Kvco| (86 MHz/V) not at all;
#   - from ~1 GHz LOOP_FILTER (Oct 13: solid from 720 MHz), the lower jitter at 1.6 GHz (102 vs 182 ps); at the top
#     (nominal supply) Icp 7 holds 11.7 GHz, the DEFAULT_CFG filter only 11.4 GHz.
# Entries: (f_ref upper bound [Hz], filter, |Kvco| request of kvco_target_for), the first whose bound exceeds f_ref.
FILTER_SCHEDULE = [
    (1.4e6, dict(DEFAULT_FILTER, set_current=0, set_c1=7), "min"),  # VCO < 180 MHz
    (2.5e6, dict(DEFAULT_FILTER, set_current=0, set_c1=7), 2e9),  # VCO 180-320 MHz
    (5e6, dict(DEFAULT_FILTER, set_current=0), 2e9),  # VCO 320-640 MHz
    (8e6, dict(DEFAULT_FILTER), 2e9),  # VCO 640 MHz - 1 GHz
    (float("inf"), dict(LOOP_FILTER), 2e9),  # VCO > 1 GHz
]
# Coarse measured sweep over the lock range at the nominal supply: VCO 128 MHz - 11.7 GHz (the edges of 2026-11-03),
# 15 points log-spaced (~1/2 octave), ~2 min per locked point (~30 min).
COARSE_VCO = tuple(np.geomspace(128e6, 11.7e9, 15))


def filter_for(f_ref, schedule=FILTER_SCHEDULE):
    """(loop filter as a FILTER_FIELDS dict, |Kvco| request) of `schedule` for the reference frequency `f_ref` [Hz]."""
    return next((flt, kvco) for bound, flt, kvco in schedule if f_ref < bound)


def coarse_sweep(supply=None, sample="S5", f_vcos=COARSE_VCO, schedule=FILTER_SCHEDULE):
    """Full measurement (range_sweep, analyzer) at every VCO frequency of `f_vcos`, each with the loop filter and
    |Kvco| of `schedule` for its reference (filter_for); one CSV results/pll/pll_range_coarse_<sample>_<stamp>.csv (the
    filter and |Kvco| request of each point in its columns). Returns the CSV path."""
    csv_path = result_csv_path(sample, prefix="pll_range_coarse")
    for f_vco in f_vcos:
        f_ref = f_vco / FB_DIV
        loop_filter, kvco = filter_for(f_ref, schedule)
        range_sweep([f_ref], kvco=kvco, loop_filter=loop_filter, sample=sample, supply=supply, csv_path=csv_path)
    return csv_path


# Highest |Kvco| above VCO ~1 GHz (2026-11-03): in the coarse sweep (pll_range_coarse_S5_20261103_174312, |Kvco|
# ~2 GHz/V) only the points where the table picked a high |Kvco| had a low jitter (3.2 / 6.1 / 8.5 GHz: 5-37 GHz/V,
# 19-39 ps); the ~2 GHz/V picks gave 88-524 ps (1.2 / 1.7 GHz) or no lock (2.3 / 4.4 GHz). On 2026-10-13 a high |Kvco|
# locked from 1.8 GHz with the DEFAULT_CFG filter (_151724) but only from 5.1 GHz with LOOP_FILTER (_150230): with
# both strong the loop is too fast for its reference. Measured here with the table's highest |Kvco| at the coarse
# points of 1.2-6.1 GHz, once per filter (one CSV each, results/pll/pll_range_kvmax_<sample>_<stamp>.csv), ~12 min
# per filter.
KVMAX_VCO = tuple(f for f in COARSE_VCO if 1e9 < f < 7e9)
KVMAX_FILTERS = (DEFAULT_FILTER, LOOP_FILTER)


def kvmax_check(supply=None, sample="S5"):
    """Full measurement at KVMAX_VCO with the table's highest |Kvco| ("max"), once per filter of KVMAX_FILTERS, one
    CSV per filter. Returns the CSV paths."""
    paths = []
    for loop_filter in KVMAX_FILTERS:
        paths.append(range_sweep([f / FB_DIV for f in KVMAX_VCO], kvco="max", loop_filter=loop_filter,
                                 sample=sample, supply=supply,
                                 csv_path=result_csv_path(sample, prefix="pll_range_kvmax")))
    return paths


# Top of the usable range (2026-11-03): the highest VCO where jitter and power still hold. The power scales linearly
# (0.21-0.23 mW/GHz from 3 to 11.7 GHz); the jitter held 15-18 ps (14-16 % of the period) at 8.1-10.2 GHz on
# 2026-10-13 (_161640), 29 ps (33 %) at 11.4 GHz, and 11.7 GHz lost the lock in the coarse sweep: where between
# 10 and 11.7 GHz does it break? Measured at the nominal supply, LOOP_FILTER (Icp 7 held the top best in upper_search),
# the table's fastest VCO setting above ~9.2 GHz; one CSV results/pll/pll_range_top_<sample>_<stamp>.csv, ~16 min.
TOP_VCO = (8.5e9, 9.0e9, 9.5e9, 10.0e9, 10.5e9, 11.0e9, 11.4e9, 11.7e9)


def top_sweep(supply=None, sample="S5"):
    """Full measurement at TOP_VCO with LOOP_FILTER and the table's highest |Kvco| (the fastest setting where the
    table runs out). Returns the CSV path."""
    return range_sweep([f / FB_DIV for f in TOP_VCO], kvco="max", loop_filter=LOOP_FILTER, sample=sample,
                       supply=supply, csv_path=result_csv_path(sample, prefix="pll_range_top"))


# Operating edges of the lock range against the PLL supply (2026-11-06), lock check only (no analyzer, no jitter): per
# supply of EDGE_VDDS the lowest and highest VCO frequency that locks and still holds the lock after EDGE_HOLD s, with
# the PLL supply power at every probe. Per edge (find_edge):
#   1. bracket: from the seed EDGE_SEEDS (the same at every supply) step outward by EDGE_STEP while the probe holds
#      the lock, inward while it does not, until a held probe sits next to a failed one;
#   2. bisect between the two until they are EDGE_TOL apart (10 MHz at the bottom, 100 MHz at the top).
# A probe without any VCO setting to try it with (no_vco_setting) is unknown, not failed: the bracket steps over it
# and it is never taken as an edge (an unknown midpoint ends the bisection early, the bracket stays wider). Loop per
# probe (edge_loops): the filter and |Kvco| of FILTER_SCHEDULE, but the table's highest |Kvco| above VCO 1 GHz for
# the top (mid curve, away from the knees where the ~2 GHz/V picks failed at 2.3 / 4.4 GHz; the fastest setting
# above the table). The table was measured at 0.75 V: at other supplies the VCO curves shift and the picks land
# elsewhere on them. A bottom probe tries every filter of EDGE_LOWER_FILTERS with every |Kvco| of EDGE_LOWER_KVCOS
# (one CSV row per try) and holds when one of them holds, to keep a failed VCO pick or a filter switch of the
# schedule apart from the loop limit. Without a setting inside the table's Vctrl window a probe takes one inside
# EDGE_WIDE_WINDOW (vco_pick "lut_wide"). Assumes one locked stretch between the edges: a hole shows only where a
# probe lands in it (every probe is in the CSV). ~10-25 probes of ~5-25 s per edge, ~30-60 min for both edges.
# Full run of 2026-11-06 (pll_edges_S5_20261106_101806), before the unknown probes, the wide window, the fixed seeds
# and the bottom filters: a gap of the table at VCO 5.63-5.9 GHz (no setting inside 0.5-0.7 V, below the fastest
# setting) counted as failed, so the top stuck at 5.56 GHz from 0.60 V on (the previous edge was the next seed); the
# bottom at 0.90 V failed with Icp 0 up to 636 MHz and held 643 MHz, the schedule's switch to Icp 3.
#   results/pll/pll_edges_<sample>_<stamp>.csv           one row per try (EDGE_COLUMNS): supply set (vdd_set) and
#       measured (pll_vdd), which search (edge), frequencies, table pick (VCO codes, |Kvco| request / target,
#       predicted Vctrl / |Kvco|), loop filter, divider, lock bit after lock_timeout (locked) and after hold s
#       (locked_end, held), status, PLL current and power: measured after the hold when locked, else right after
#       the lock timeout (VCO free running, not at f_vco)
#   results/pll/pll_edges_<sample>_<stamp>_summary.csv   one row per supply: the search settings (tol_*, hold), per
#       edge the outermost held and innermost failed frequency (f_fail empty: nothing failed up to the limit; both
#       empty: nothing held), the supply, current and power of the held try, the number of probed frequencies
EDGE_VDDS = tuple(np.round(np.arange(0.50, 0.90 + 1e-9, 0.05), 2))  # [V] 0.50-0.90 V in 50 mV
EDGE_TOL = dict(lower=10e6, upper=100e6)  # [Hz] final gap between the held and the failed probe
EDGE_STEP = dict(lower=0.85, upper=1.05)  # outward factor per bracket step (~20 MHz at the bottom, ~550 MHz at the top)
EDGE_SEEDS = dict(lower=128e6, upper=11.7e9)  # [Hz] seeds at every supply: the edges at 0.75 V of 2026-11-03
# [Hz] outward limits: 40 MHz (the table ends at ~55 MHz: below it no VCO setting, a failed probe) and the 33600A's
# 100 MHz reference (VCO 12.8 GHz); an edge held at the limit is recorded with an empty failed frequency
EDGE_LIMITS = dict(lower=40e6, upper=FB_DIV * 100e6)
EDGE_INWARD_STOP = dict(lower=2e9, upper=500e6)  # [Hz] inward walk gives up here: nothing locks at this supply
EDGE_HOLD = 15.0  # [s] between the two lock reads (11.7 GHz held 15 s on 2026-11-03, lost it within ~2 min)
EDGE_LOWER_KVCOS = ("min", 2e9)  # |Kvco| requests a bottom probe tries in turn (after the schedule's)
EDGE_LOWER_FILTERS = (  # filters a bottom probe tries in turn, each with every request of EDGE_LOWER_KVCOS
    dict(DEFAULT_FILTER, set_current=0, set_c1=7),
    dict(DEFAULT_FILTER, set_current=0),
    dict(DEFAULT_FILTER),
)
EDGE_WIDE_WINDOW = (0.40, 0.80)  # [V] Vctrl window of the fallback pick (the top held down to Vctrl ~0.40 V)
# Quick run to check the setup and the notebook (~5-8 min): three supplies, coarse tolerances, short hold
EDGE_QUICK_VDDS = (0.65, 0.75, 0.85)
EDGE_QUICK_TOL = dict(lower=40e6, upper=500e6)
EDGE_QUICK_HOLD = 3.0
EDGE_COLUMNS = (["vdd_set", "edge", "time", "lut_csv", "f_ref", "f_vco", "kvco_request", "kvco_target", "vco_pick"]
                + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
                + ["vctrl_pred", "kvco_pred", "kvco_min", "kvco_max", "set_div_freq", "total_div", "locked",
                   "locked_end", "held", "status", "lock_timeout", "hold"] + list(pll_setup.SUPPLY_COLUMNS))
EDGE_SUMMARY_COLUMNS = (["vdd_set", "vdd_meas", "tol_lower", "tol_upper", "hold"]
                        + ["{}_{}".format(edge, k) for edge in ("lower", "upper")
                           for k in ("f", "f_fail", "vdd", "i", "p", "n_probes")])


def edge_loops(f_ref, edge):
    """[(loop filter, |Kvco| request), ...] tried in turn for a probe of the `edge` ("lower" / "upper") search at
    `f_ref` [Hz], until one holds: the schedule's (with "max" above VCO 1 GHz for the top), then for the bottom every
    other filter of EDGE_LOWER_FILTERS with every request of EDGE_LOWER_KVCOS."""
    loop_filter, kvco = filter_for(f_ref)
    if edge == "upper":
        return [(loop_filter, "max" if FB_DIV * f_ref > 1e9 else kvco)]
    tries = [(loop_filter, kvco)]
    tries += [(flt, k) for flt in EDGE_LOWER_FILTERS for k in EDGE_LOWER_KVCOS if (flt, k) not in tries]
    return tries


def lock_probe(pll, fg, lut, f_vco, loop_filter, kvco, supply=None, lock_timeout=3.0, hold=EDGE_HOLD,
               wide_lut=None):
    """One lock check at `f_vco` [Hz] on an open link `pll` and reference `fg`: VCO codes from the table `lut` for
    |Kvco| `kvco` (else its fastest setting where that can help, fastest_cfg, else the pick of `wide_lut`, the same
    table with a wider Vctrl window, vco_pick "lut_wide"), filter `loop_filter`; wait for lock, when locked wait
    `hold` s and read the lock bit again, then the PLL supply power. Returns the row (EDGE_COLUMNS; held = 1 when
    still locked after `hold`; status "no_vco_setting" when nothing was configured)."""
    f_ref = f_vco / FB_DIV
    row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, f_ref=f_ref, f_vco=f_vco,
               kvco_request=kvco, status="error", held=0, lock_timeout=lock_timeout, hold=hold, **loop_filter)
    pick_lut = lut
    try:
        target, kvco_min, kvco_max = kvco_target_for(lut, f_vco, kvco)
        cfg = lut.update_config(loop_cfg(f_vco, loop_filter), f_vco, target)
        row["vco_pick"] = "lut"
    except ValueError as e:
        cfg = fastest_cfg(lut, f_vco, loop_filter)
        target = kvco_min = kvco_max = float("nan")
        row["vco_pick"] = "fastest"
        if cfg is None and wide_lut is not None:
            try:
                target, kvco_min, kvco_max = kvco_target_for(wide_lut, f_vco, kvco)
                cfg = wide_lut.update_config(loop_cfg(f_vco, loop_filter), f_vco, target)
                pick_lut, row["vco_pick"] = wide_lut, "lut_wide"
            except ValueError:
                pass
        if cfg is None:
            logging.warning("No VCO setting for %.1f MHz: not configured (%s)", f_vco / 1e6, e)
            row.update(status="no_vco_setting", vco_pick="")
            return row
    _, total_div = calculate_div_factor(cfg)
    try:
        op = pick_lut.predict(cfg, f_vco)
    except ValueError:  # the fastest setting does not reach f_vco in the table at all
        op = dict(vctrl_pred=float("nan"), kvco_pred=float("nan"))
    row.update(vco_lut.vco_codes(cfg), **op, kvco_target=target, kvco_min=kvco_min, kvco_max=kvco_max,
               set_div_freq=cfg["set_div_freq"], total_div=total_div)

    pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50, fg=fg)
    pll_setup.load_config(pll, cfg)
    row["locked"] = int(pll.wait_lock(timeout=lock_timeout))
    if row["locked"]:
        time.sleep(hold)
        row["locked_end"] = pll.read_lock()
        row["held"] = int(row["locked_end"] == 1)
    row["status"] = "lock_only" if row["locked"] else "not_locked"
    row.update(pll_setup.measure_pll_supply(supply, label="VCO %.1f MHz" % (f_vco / 1e6)))
    logging.info("VCO %.1f MHz (%s, coarse %d min %d max %d, Vctrl ~%.3f V, Icp %d C1 %d C2 %d R1 %d): %s",
                 f_vco / 1e6, row["vco_pick"], cfg["vco_tune_coarse"], cfg["vco_current_min"],
                 cfg["vco_current_max"], row["vctrl_pred"], cfg["set_current"], cfg["set_c1"], cfg["set_c2"],
                 cfg["set_r1"], "HELD" if row["held"] else "lost after %.0f s" % hold if row["locked"]
                 else "NOT LOCKED")
    return row


def find_edge(probe, f_seed, outward, tol, f_limit, f_stop):
    """Edge of the lock range by bracketing and bisection. `probe(f)` [Hz] -> True: f holds the lock, False: it does
    not, None: unknown (nothing to try it with). From `f_seed` step inward by the factor `outward` (> 1: the top
    edge, < 1: the bottom) until a probe holds, then outward while it holds, then bisect the bracket down to `tol`
    [Hz]. Unknown probes are stepped over and never taken as an edge; an unknown midpoint ends the bisection (the
    bracket stays wider than `tol`). Outward never past `f_limit`, inward never past `f_stop`.
    Returns (f_in, f_out): the outermost held and the innermost failed frequency (f_out None: nothing failed up to
    f_limit; both None: nothing held between f_seed and f_stop)."""
    clamp = min if outward > 1 else max
    f, f_out = f_seed, None
    while True:  # inward until a probe holds
        held = probe(f)
        if held:
            f_in = f
            break
        if held is False:
            f_out = f  # the innermost failure so far
        f = f / outward
        if (f < f_stop) if outward > 1 else (f > f_stop):
            return None, None
    f = f_in
    while f_out is None and f != f_limit:  # held at the seed (or only unknowns outward): outward until a failure
        f = clamp(f * outward, f_limit)
        held = probe(f)
        if held:
            f_in = f
        elif held is False:
            f_out = f
    while f_out is not None and abs(f_out - f_in) > tol:
        f = (f_in + f_out) / 2
        held = probe(f)
        if held is None:
            logging.warning("No VCO setting at %.1f MHz: bisection stops, edge between %.1f and %.1f MHz",
                            f / 1e6, f_in / 1e6, f_out / 1e6)
            break
        if held:
            f_in = f
        else:
            f_out = f
    return f_in, f_out


def edge_search(supply, sample="S5", vdds=EDGE_VDDS, tol=EDGE_TOL, hold=EDGE_HOLD, edges=("lower", "upper")):
    """Lowest and highest held VCO frequency (find_edge, see EDGE_* above) at every PLL supply of `vdds` [V]
    (`supply`: PllSupplyChannel; back to its nominal at the end, also on an error), down to `tol` (dict
    lower / upper [Hz]) with `hold` [s] between the two lock reads; only the edges in `edges` (the summary columns
    of the other stay empty). Every probe is a row of results/pll/pll_edges_<sample>_<stamp>.csv, one row per
    supply in <stem>_summary.csv (the edges, the power at each held edge). Returns the CSV path."""
    csv_path = result_csv_path(sample, prefix="pll_edges")
    summary_path = csv_path.with_name(csv_path.stem + "_summary.csv")
    lut = vco_lut.VcoLUT(sample=sample)
    wide_lut = vco_lut.VcoLUT(sample=sample, window=EDGE_WIDE_WINDOW)
    fg = pll = None
    try:
        fg = pll_setup.open_reference_generator()
        pll = pll_setup.connect()
        for vdd in vdds:
            summary = dict(vdd_set=vdd, vdd_meas=supply.set(vdd), tol_lower=tol["lower"], tol_upper=tol["upper"],
                           hold=hold)
            for edge in edges:
                logging.info("=== PLL supply %.2f V: %s edge, from %.1f MHz ===", vdd, edge, EDGE_SEEDS[edge] / 1e6)
                rows, results = {}, {}

                def probe(f_vco):
                    """True: held with one of the tries, False: none held, None: no try had a VCO setting."""
                    if f_vco in results:
                        return results[f_vco]
                    statuses = []
                    for loop_filter, kvco in edge_loops(f_vco / FB_DIV, edge):
                        try:
                            row = lock_probe(pll, fg, lut, f_vco, loop_filter, kvco, supply=supply, hold=hold,
                                             wide_lut=wide_lut)
                        except pyvisa.VisaIOError:
                            raise  # instrument connection lost: stop
                        except Exception:
                            logging.exception("VCO %.1f MHz failed, counted as not held", f_vco / 1e6)
                            row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name,
                                       f_ref=f_vco / FB_DIV, f_vco=f_vco, kvco_request=kvco, status="error", held=0,
                                       hold=hold, **loop_filter)
                        row.update(vdd_set=vdd, edge=edge)
                        append_rows(csv_path, EDGE_COLUMNS, [row])
                        rows[f_vco] = row  # the held try, else the last one
                        statuses.append(row["status"])
                        if row["held"]:
                            break
                    results[f_vco] = (True if rows[f_vco]["held"]
                                      else None if all(s == "no_vco_setting" for s in statuses) else False)
                    return results[f_vco]

                f_in, f_out = find_edge(probe, EDGE_SEEDS[edge], EDGE_STEP[edge], tol[edge], EDGE_LIMITS[edge],
                                        EDGE_INWARD_STOP[edge])
                held = rows[f_in] if f_in is not None else {}
                summary.update({"{}_f".format(edge): f_in, "{}_f_fail".format(edge): f_out,
                                "{}_vdd".format(edge): held.get("pll_vdd"), "{}_i".format(edge): held.get("pll_i"),
                                "{}_p".format(edge): held.get("pll_p"), "{}_n_probes".format(edge): len(rows)})
                if f_in is None:
                    logging.warning("PLL supply %.2f V: nothing held on the %s side", vdd, edge)
                else:
                    logging.info("PLL supply %.2f V: %s edge %.1f MHz (fails at %s), %.3f mW, %d probes", vdd, edge,
                                 f_in / 1e6, "%.1f MHz" % (f_out / 1e6) if f_out else "- (nothing failed)",
                                 held.get("pll_p", float("nan")) * 1e3, len(rows))
            append_rows(summary_path, EDGE_SUMMARY_COLUMNS, [summary])
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
        supply.set(supply.nominal)
    logging.info("Edge search written to %s (summary: %s)", csv_path, summary_path.name)
    return csv_path


def result_csv_path(sample, prefix="pll_range"):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / "{}_{}_{}.csv".format(prefix, sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def start_log_file():
    """Also write the log to results/logs/pll_range_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_range_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():  # core in reset: no pollution
        # PLL supply from the E36312A CH2 (pll_setup.PllSupplyChannel: voltage, current, power per point; only
        # upper_search and edge_search change the voltage, close() programs the nominal it found again, also on an
        # error).
        # supply = None: PLL supply from a battery / fixed on the board, power columns NaN (not with upper_search).
        supply = pll_setup.PllSupplyChannel(channel=2)
        try:
            # Operating edges against the PLL supply: 0.50-0.90 V in 50 mV, lowest (to 10 MHz) and highest (to
            # 100 MHz) VCO frequency that holds the lock, with the power; lock check only, ~30-40 min. See EDGE_*
            # above; plots: sw/tools/notebooks/pll_edges.ipynb
            # Bottom edge only (~20-30 min), every weak filter per probe (EDGE_LOWER_FILTERS); combined with the top
            # of pll_edges_S5_20261106_110104 in the notebook (BOTTOM_CSV)
            edge_search(supply, edges=("lower",))
            # Rerun of the top edge only (done 2026-11-06: pll_edges_S5_20261106_110104; 3.54 GHz at 0.50 V to
            # >= 12.8 GHz at 0.90 V): the full run pll_edges_S5_20261106_101806 stuck at a gap of the table (see
            # EDGE_* above)
            # edge_search(supply, edges=("upper",))
            # edge_search(supply)
            # Quick check of the setup and the notebook: 0.65 / 0.75 / 0.85 V, bottom to 40 MHz, top to 500 MHz,
            # 3 s hold (~4 min); same CSV names, so the notebook picks it up as the newest run (done 2026-11-06:
            # pll_edges_S5_20261106_100452)
            # edge_search(supply, vdds=EDGE_QUICK_VDDS, tol=EDGE_QUICK_TOL, hold=EDGE_QUICK_HOLD)

            # Highest |Kvco| at the coarse points of 1.2-6.1 GHz, DEFAULT_CFG filter and LOOP_FILTER (~25 min), to
            # set the |Kvco| and filter of FILTER_SCHEDULE above VCO ~1 GHz; see KVMAX_* above
            # kvmax_check(supply)
            # Top of the usable range: VCO 8.5-11.7 GHz, measured (~16 min); see TOP_* above
            # top_sweep(supply)

            # Coarse measured sweep over the lock range (VCO 128 MHz - 11.7 GHz, 15 points, ~30 min): jitter,
            # spectrum and power with the loop filter and |Kvco| of FILTER_SCHEDULE per point, for the first curves
            # and to pick the frequency for the detailed paper measurement (done 2026-11-03:
            # pll_range_coarse_S5_20261103_174312)
            # coarse_sweep(supply)

            # Edges of the lock range (done 2026-11-03: pll_range_floor_S5_20261103_165653,
            # pll_range_upper_S5_20261103_170454): floor (VCO 50-200 MHz, weak loops, ~11 min), then the upper end (VCO
            # 11.4-12.5 GHz, strong loops, PLL supply 0.75 / 0.80 / 0.85 V, back to the nominal at the end, ~20 min).
            # Lock check only; see FLOOR_* / UPPER_* above. Floor 128 MHz (100 MHz locks, then loses it); top
            # 11.7 GHz at 0.75 V, 12.0 GHz at 0.80 V, 12.25 GHz at 0.85 V
            # floor_search(supply)
            # upper_search(supply)

            # Debug of the low end (2026-11-03, done: pll_range_lowend_S5_20261103_163916; Icp 0 locks 200 MHz): no
            # lock below ~510 MHz VCO (ref ~4 MHz), although the VCO runs down to ~50 MHz open loop (vco_lut_S5_20261001_161638). The lowest lock moves with the loop gain: 1.8 GHz at
            # |Kvco| 5-28 GHz/V, 510 MHz at ~2 GHz/V with the DEFAULT_CFG filter, 642 MHz (lost again) with the
            # stronger LOOP_FILTER. Suspect: FB_DIV fixed at 128, so the loop bandwidth stays while f_ref drops with
            # the VCO, until the loop is too fast for its reference (discrete-time stability limit, ~f_ref / 10).
            # Test: weaken the loop at VCO 200 / 400 / 800 MHz, lock check only (measure=False, ~10 s per point,
            # ~8 min). Filters: DEFAULT_FILTER with the fields of each entry forced (cfg_overrides); assumes a higher
            # code = more current / capacitance / resistance (consistent with LOOP_FILTER, Icp 7 C 0 R 7, being the
            # faster loop). Both the |Kvco| ~2 GHz/V pick and the table's lowest |Kvco| ("min").
            # f_refs = [f_vco / FB_DIV for f_vco in (200e6, 400e6, 800e6)]
            # LOW_END_FILTERS = [
            #     dict(),  # DEFAULT_CFG filter: Icp 3 C1 3 C2 3 R1 3 (lowest lock 510 MHz on 2026-10-13)
            #     dict(set_current=1),
            #     dict(set_current=0),
            #     dict(set_c1=7),
            #     dict(set_current=0, set_c1=7),
            #     dict(set_r1=1),
            #     dict(set_current=0, set_c1=7, set_r1=1),
            #     dict(LOOP_FILTER),  # Icp 7 C1 0 C2 0 R1 7: the strong loop, expected to fail
            # ]
            # csv_path = result_csv_path("S5", prefix="pll_range_lowend")
            # for kvco in (2e9, "min"):
            #     for overrides in LOW_END_FILTERS:
            #         range_sweep(f_refs, kvco=kvco, loop_filter=DEFAULT_FILTER, sample="S5", supply=supply,
            #                     cfg_overrides=overrides, csv_path=csv_path, measure=False)

            # Quick rerun of the range sweeps of 2026-10-13 (pll_range_S5_20261013_160525 / _161640) with this supply
            # (done 2026-11-03: _155029 / _155259): REF_QUICK (VCO 400 MHz - 6.4 GHz in octaves and 12 GHz;
            # REF_SWEEP for the full ~1 h sweep), VCO codes from the S5 table for |Kvco| ~2 GHz/V, first the
            # DEFAULT_CFG filter, then LOOP_FILTER; ~2 min per locked point, ~10 min per sweep.
            # range_sweep(REF_QUICK, kvco=2e9, loop_filter=DEFAULT_FILTER, sample="S5", supply=supply)
            # range_sweep(REF_QUICK, kvco=2e9, loop_filter=LOOP_FILTER, sample="S5", supply=supply)
        finally:
            if supply is not None:
                supply.close()  # back to the voltage it found (nominal), connection released

        # Debug of a failed point of the range sweeps of 2026-10-13: ref 22.387 MHz -> VCO 2865.6 MHz
        # (REF_SWEEP[27]). At |Kvco| ~2 GHz/V the table picks coarse 3, min 0, max 0 (Vctrl pred 0.521 V,
        # 1.7 GHz/V): not locked with either filter (pll_range_S5_20261013_160525 / _161640). With central Vctrl
        # (coarse 0, min 10, max 6, Vctrl pred 0.549 V, 33 GHz/V) it locked with the DEFAULT_CFG filter
        # (_151724). Each entry of DEBUG_CONFIGS is one try, recorded as one row of one
        # pll_range_debug_S5_<stamp>.csv: cfg_overrides is forced on top of the table pick (any config field;
        # all three VCO codes = no table pick), lock_timeout [s] is how long to wait for the lock bit.
        # (not run yet)
        # f_ref = REF_SWEEP[27]
        # loop_filter = LOOP_FILTER  # or DEFAULT_FILTER (Icp 3, C1 3, C2 3, R1 3)
        # DEBUG_CONFIGS = [
        #     dict(),  # the table pick as in the sweep (coarse 3, min 0, max 0)
        #     dict(vco_tune_coarse=0, vco_current_min=10, vco_current_max=6),  # the setting that locked in _151724
        #     # dict(vco_tune_coarse=3, vco_current_min=0, vco_current_max=0, set_current=3),  # weaker charge pump
        # ]
        # lock_timeout = 3.0
        # csv_path = result_csv_path("S5", prefix="pll_range_debug")
        # for cfg_overrides in DEBUG_CONFIGS:
        #     range_sweep([f_ref], kvco=2e9, loop_filter=loop_filter, sample="S5",
        #                 cfg_overrides=cfg_overrides, lock_timeout=lock_timeout, csv_path=csv_path)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

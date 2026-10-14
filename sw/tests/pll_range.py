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
#   - PLL supply voltage, current and power (2450 SMU);
#   - when locked: the output pad (VCO / 2**set_div_freq, <= PAD_F_MAX) on the R&S FSV with
#     lib/pll_spectrum.measure_output: carrier and divider check (f_vco_meas = carrier x N, so a "lock" on a wrong
#     frequency shows), phase-noise markers, full curve with spurs, averaged spectrum, RMS jitter (also over
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
#

import logging
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
# Band integrated for every point, so the jitter can be compared: the pad is always 62.5-125 MHz (pad_divider), so
# 10 MHz fits everywhere. The same band as pll_spectrum_kvco.COMMON_BAND.
COMMON_BAND = (1e3, 1e7)

RESULT_COLUMNS = (["time", "lut_csv", "f_ref", "f_vco", "kvco_request", "kvco_target", "vco_pick"]
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
                spectrum_averages=20, n_averages=10, lock_timeout=3.0, common_band=COMMON_BAND):
    """For every reference frequency in `f_refs` [Hz]: VCO codes from the lookup table for f_vco = FB_DIV x f_ref and
    |Kvco| `kvco` (pll_spectrum.kvco_target_for: [Hz/V], "max", "middle", "min" or None = central Vctrl),
    with the loop filter `loop_filter` (FILTER_FIELDS dict, e.g. pll_settings.LOOP_FILTER or DEFAULT_FILTER),
    load the config, wait for lock (`lock_timeout` [s]), record the PLL supply power and, when locked, measure the pad
    with measure_output (markers, full curve with spurs, spectrum, jitter, also over `common_band`).

    No analyzer measurement when the PLL did not lock (status "not_locked"). Without a table setting for f_vco the
    fastest setting is tried where it can help (fastest_cfg), else the point is not configured (status
    "no_vco_setting"). A point that fails is recorded and the sweep continues; a VISA error stops it. The reference
    (33600A) is started here and turned off at the end, the FPGA link closed; the PLL supply `supply`
    (pll_setup.pll_supply) must already be on. `lut`: the lookup table (vco_lut.VcoLUT); None = the newest
    table of `sample`. Appends one row per point to a new results/pll/pll_range_<sample>_<stamp>.csv and the traces
    to <stem>_traces.csv; returns the CSV path.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample)
    csv_path = result_csv_path(sample)
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
                       f_vco=f_vco, kvco_request=kvco, status="error", **loop_filter)
            traces = []
            try:
                try:
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
    with iclab_session(parser.get_credentials()):
        # PLL VDD 0.75 V from the 2450 (smu_vdd_pll) for the block, off afterwards (also on an error)
        with pll_setup.pll_supply() as supply:
            # Reference 1-100 MHz (REF_SWEEP, 41 points), VCO codes from the S5 table for |Kvco| ~2 GHz/V at each
            # frequency (the closest the table offers), so the lock depends on the frequency, not on a changing Kvco.
            # The highest |Kvco| (kvco="max") never locked at 1 GHz in the Kvco sweeps; kvco=None: central Vctrl.
            # Two runs, one CSV each: first the old DEFAULT_CFG filter (Icp 3, C1 3, C2 3, R1 3; the frequency sweeps
            # of 2026-10-07 locked 0.5-4 GHz with it at ~2 GHz/V), then the loop filter of the spectrum scripts
            # (Icp 7, C1 0, C2 0, R1 7)
            range_sweep(REF_SWEEP, kvco=2e9, loop_filter=DEFAULT_FILTER, sample="S5", supply=supply)
            range_sweep(REF_SWEEP, kvco=2e9, loop_filter=LOOP_FILTER, sample="S5", supply=supply)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# The simulated PLL case on silicon: 32 MHz reference, VCO at FB_DIV x 32 MHz = 4.096 GHz (the feedback ratio is
# fixed at 128, so "4 GHz" is 4.096 GHz). The VCO codes and loop filter are set directly (SIM_CFG), as in the
# simulation, not picked from the lookup table: coarse 0, min 10, max 8; C1 3, C2 3, charge-pump current 3, R1 3.
# The lookup table's expected operating point for these codes (Vctrl, |Kvco|) is recorded for the comparison with
# the simulation (S5 table of 2026-10-01: Vctrl ~0.52 V, |Kvco| ~34 GHz/V).
# The reference comes from the 33600A, the PLL supply is the 2450 SMU (current and power recorded). The output pad
# (VCO / 2**set_div_freq, <= PAD_F_MAX) is measured on the R&S FSV with lib/pll_spectrum.measure_output:
# phase-noise markers, the full phase-noise curve with spur detection, an averaged spectrum, and the RMS jitter
# (also over COMMON_BAND, comparable with the pll_spectrum_kvco.py runs).
#
# Results:
#   results/pll/pll_test_sim_<sample>_<stamp>.csv          one row: settings, lock, L(f), jitter, supply
#   results/pll/pll_test_sim_<sample>_<stamp>_traces.csv   averaged spectrum + phase-noise traces
#
# Tests:
#   measure_pll_sim(cfg, f_ref, sample)   # lock on f_ref with cfg, measure the pad
#

import logging
from datetime import datetime
from pathlib import Path

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8, FILTER_FIELDS
from sw.lib.pll_spectrum import (FB_DIV, OFFSET_SPAN_MAP, OUTPUT_COLUMNS, RESULTS_DIR, TRACE_FIELDS, append_rows,
                                 measure_output, offsets_for, pad_divider, trace_csv_path, trace_rows)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Simulated case: 32 MHz reference -> VCO FB_DIV x 32 MHz = 4.096 GHz
SIM_F_REF = 32e6
# Band the jitter is also integrated over: the same as pll_spectrum_kvco.COMMON_BAND, fits the 64 MHz pad
COMMON_BAND = (1e3, 1e7)
# CFG_REF8 base (internal Vctrl, loop closed) on the direct output (no external divider: pad = PLL output), divided
# inside the PLL to at most PAD_F_MAX on the pad; VCO codes and loop filter as in the simulation.
SIM_CFG = dict(
    CFG_REF8,
    pll_clk_o_en=1,
    set_div_freq=pad_divider(FB_DIV * SIM_F_REF),
    vco_tune_coarse=0,
    vco_current_min=10,
    vco_current_max=8,
    set_c1=0b011,
    set_c2=0b011,
    set_current=0b011,
    set_r1=0b011,
)

RESULT_COLUMNS = (["time", "f_vco", "f_ref"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
                  + ["lut_csv", "vctrl_pred", "kvco_pred", "set_div_freq", "total_div", "locked"] + OUTPUT_COLUMNS
                  + list(pll_setup.SUPPLY_COLUMNS))
TRACE_COLUMNS = ["f_vco"] + TRACE_FIELDS


def measure_pll_sim(cfg=SIM_CFG, f_ref=SIM_F_REF, sample=None, lut=None, csv_path=None, supply=None, span=5e6,
                    spectrum_averages=20, n_averages=10, offset_span_map=None, lock_timeout=3.0,
                    common_band=COMMON_BAND):
    """Lock the PLL with `cfg` on a reference of `f_ref` [Hz] (VCO at FB_DIV x f_ref), then measure the output pad
    with pll_spectrum.measure_output (markers, full curve with spurs, spectrum, jitter) and the PLL supply power.

    `lut`: the lookup table (vco_lut.VcoLUT) for the expected Vctrl and |Kvco| of the codes in `cfg`; None = the
    newest table of `sample`. Codes the table does not reach f_vco with are logged and recorded as NaN.
    `common_band`: also integrate the jitter over only this band (time_jitter_common_ps / time_jitter_trace_common_ps).
    No analyzer measurement when the PLL did not lock (status "not_locked").
    The reference (33600A) is started here and turned off at the end; the PLL supply `supply`
    (pll_setup.pll_supply) must already be on. Every connection is closed at the end, also on an error.
    Appends one row to `csv_path` (default a new results/pll/pll_test_sim_<sample>_<stamp>.csv) and the traces to
    <stem>_traces.csv; returns the row.
    """
    csv_path = csv_path or result_csv_path(sample)
    f_vco = FB_DIV * f_ref
    _, total_div = calculate_div_factor(cfg)
    offset_span_map = offsets_for(f_vco / total_div, offset_span_map or OFFSET_SPAN_MAP)  # band limited by the pad
    row = dict(time=datetime.now().isoformat(timespec="seconds"), f_vco=f_vco, f_ref=f_ref,
               set_div_freq=cfg["set_div_freq"], total_div=total_div, status="error", **vco_lut.vco_codes(cfg),
               **{k: cfg[k] for k in FILTER_FIELDS})
    lut = lut or vco_lut.VcoLUT(sample=sample)
    row["lut_csv"] = lut.path.name
    try:
        row.update(lut.predict(cfg, f_vco))
        logging.info("Lookup table %s: expected Vctrl %.3f V, |Kvco| %.0f MHz/V at %.1f MHz", lut.path.name,
                     row["vctrl_pred"], row["kvco_pred"] / 1e6, f_vco / 1e6)
    except ValueError as e:
        logging.warning("No lookup-table prediction: %s", e)
        row.update(vctrl_pred=float("nan"), kvco_pred=float("nan"))
    traces = []

    fg = pll = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=lock_timeout)
        row["locked"] = int(locked)
        logging.info("PLL %s at %.1f MHz (ref %.4f MHz x %d), VCO coarse %d min %d max %d, C1 %d C2 %d Icp %d R1 %d; "
                     "/%d inside the PLL -> pad %.4f MHz", "LOCKED" if locked else "NOT LOCKED", f_vco / 1e6,
                     f_ref / 1e6, FB_DIV, cfg["vco_tune_coarse"], cfg["vco_current_min"], cfg["vco_current_max"],
                     cfg["set_c1"], cfg["set_c2"], cfg["set_current"], cfg["set_r1"], total_div,
                     f_vco / total_div / 1e6)
        row.update(pll_setup.measure_pll_supply(supply, label="%.1f MHz" % (f_vco / 1e6)))

        if not locked:
            # No lock: no carrier at f_vco / N either; the analyzer would only measure noise
            logging.warning("Not locked: not measured")
            row["status"] = "not_locked"
            return row  # the finally block still closes everything and writes the row

        meas, traces = measure_output(f_vco, total_div, offset_span_map, n_averages=n_averages, span=span,
                                      spectrum_averages=spectrum_averages, common_band=common_band)
        row.update(meas)
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
        append_rows(csv_path, RESULT_COLUMNS, [row])
        append_rows(trace_csv_path(csv_path), TRACE_COLUMNS, trace_rows(traces, f_vco=f_vco))
        logging.info("Results written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return row


def result_csv_path(sample, prefix="pll_test_sim"):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / "{}_{}_{}.csv".format(prefix, sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def start_log_file():
    """Also write the log to results/logs/pll_test_sim_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_test_sim_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
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
        # Simulated case: 32 MHz reference, VCO 4.096 GHz, codes and loop filter of SIM_CFG
        measure_pll_sim(SIM_CFG, SIM_F_REF, sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

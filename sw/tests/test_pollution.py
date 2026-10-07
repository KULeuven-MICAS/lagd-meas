# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Do the lab instruments pollute the spectrum? The R&S FSV records an averaged spectrum (RMS detector, power
# averaging) over F_START - F_STOP while the instruments are switched on one by one (the PLL is not configured):
#   all_off   2450 PLL-supply SMU and 33600A reference generator reset: outputs off
#   smu_0v    SMU output on at 0 V: the instrument's source stage active, the chip's PLL domain still unpowered
#   smu_vdd   SMU at the PLL VDD: the PLL domain powered, not configured (an unconfigured VCO may oscillate)
#   smu_fg    + the reference from the 33600A (square 0 -> REF_VPP into 50 Ohm at F_REF)
# Compare each state with all_off: smu_0v shows the SMU itself, smu_vdd the powered chip, smu_fg the generator.
# The PLL supply current is recorded in the states with the SMU on.
#
# Results:
#   results/pll/test_pollution_<stamp>.csv          one row per state: settings, levels, rise over all_off
#   results/pll/test_pollution_<stamp>_traces.csv   the averaged spectrum per state
#
# Tests:
#   pollution_sweep()   all four states, one CSV
#

import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from sw.lib import pll_setup
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_spectrum import (FB_DIV, RBW_SPAN_RATIO, RESULTS_DIR, TRACE_FIELDS, append_rows, open_spectrum,
                                 trace_csv_path, trace_rows)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Band recorded per state: the pad frequencies (<= 125 MHz) and their offsets (<= 50 MHz) of the PLL measurements.
F_START, F_STOP = 100e3, 200e6
# Reference of the PLL measurements at f_vco = 1 GHz (f_vco / FB_DIV), same amplitude and load.
F_REF = 1e9 / FB_DIV
REF_VPP = 1.8
VDD = 0.75  # PLL VDD [V]
AVERAGES = 20  # sweeps averaged per state
SETTLE = 2.0  # wait [s] after switching, before the sweeps

RESULT_COLUMNS = ["time", "state", "smu_output", "smu_v_set", "fg_output", "f_ref", "ref_vpp", "f_start", "f_stop",
                  "rbw", "vbw", "averages", "level_median_dbm", "level_max_dbm", "f_at_max",
                  "rise_median_db", "rise_max_db", "f_at_rise_max"] + list(pll_setup.SUPPLY_COLUMNS)
TRACE_COLUMNS = ["state"] + TRACE_FIELDS


def measure_state(spectrum, state, f_start, f_stop, averages=AVERAGES, settle=SETTLE, supply=None, baseline=None):
    """Wait `settle` [s], then one averaged spectrum over f_start - f_stop [Hz] (RBW = span / RBW_SPAN_RATIO).

    `supply`: the PLL-supply SMU when its output is on (current recorded), else None.
    `baseline`: the all_off trace; the rise over it (per point, in dB) is summarized as its median and maximum.
    Returns (row, trace): the levels of the RESULT_COLUMNS and the trace (pll_spectrum.trace_rows format).
    """
    time.sleep(settle)
    trace = spectrum.averaged_trace((f_start + f_stop) / 2, f_stop - f_start, averages=averages,
                                    rbw_span_ratio=RBW_SPAN_RATIO)
    trace["kind"] = "spectrum"
    freq, level = np.asarray(trace["freq"]), np.asarray(trace["level"])
    row = dict(time=datetime.now().isoformat(timespec="seconds"), state=state, f_start=f_start, f_stop=f_stop,
               rbw=trace["rbw"], vbw=trace["vbw"], averages=averages, level_median_dbm=float(np.median(level)),
               level_max_dbm=float(level.max()), f_at_max=float(freq[level.argmax()]))
    if baseline is not None:
        rise = level - np.asarray(baseline["level"])
        row.update(rise_median_db=float(np.median(rise)), rise_max_db=float(rise.max()),
                   f_at_rise_max=float(freq[rise.argmax()]))
    row.update(pll_setup.measure_pll_supply(supply, label=state))
    logging.info("%s: median %.1f dBm, max %.1f dBm at %.3f MHz (RBW %g Hz)%s", state, row["level_median_dbm"],
                 row["level_max_dbm"], row["f_at_max"] / 1e6, row["rbw"],
                 "" if baseline is None else "; over all_off: median %+.1f dB, max %+.1f dB at %.3f MHz" % (
                     row["rise_median_db"], row["rise_max_db"], row["f_at_rise_max"] / 1e6))
    return row, trace


def pollution_sweep(f_start=F_START, f_stop=F_STOP, f_ref=F_REF, ref_vpp=REF_VPP, vdd=VDD, averages=AVERAGES,
                    settle=SETTLE):
    """The four states of the header, in order, each measured with measure_state, into one CSV.

    The SMU and the generator are reset at the start (outputs off) and turned off again at the end, also on an error
    (every connection closed). Rows and traces measured so far are written also when a state fails.
    Returns the CSV path.
    """
    csv_path = result_csv_path()
    rows, traces = [], []
    spectrum = smu = fg = None
    try:
        spectrum = open_spectrum()  # reset
        smu = pll_setup.open_pll_smu()  # reset: 0 V, output off
        fg = pll_setup.open_reference_generator()  # reset: outputs off
        settings = dict(smu_output=0, smu_v_set=0.0, fg_output=0, f_ref=f_ref, ref_vpp=ref_vpp)

        row, baseline = measure_state(spectrum, "all_off", f_start, f_stop, averages, settle)
        rows.append(dict(row, **settings))
        traces.append(baseline)

        pll_setup.start_pll_supply(0.0, smu=smu)
        settings.update(smu_output=1, smu_v_set=0.0)
        row, trace = measure_state(spectrum, "smu_0v", f_start, f_stop, averages, settle, smu, baseline)
        rows.append(dict(row, **settings))
        traces.append(trace)

        pll_setup.start_pll_supply(vdd, smu=smu)
        settings.update(smu_v_set=vdd)
        row, trace = measure_state(spectrum, "smu_vdd", f_start, f_stop, averages, settle, smu, baseline)
        rows.append(dict(row, **settings))
        traces.append(trace)

        pll_setup.start_reference(f_ref, vpp=ref_vpp, channel=1, load=50, fg=fg)
        settings.update(fg_output=1)
        row, trace = measure_state(spectrum, "smu_fg", f_start, f_stop, averages, settle, smu, baseline)
        rows.append(dict(row, **settings))
        traces.append(trace)
    finally:
        if fg is not None:
            fg.close()  # reference off
        if smu is not None:
            smu.close()  # back to 0 V, output off
        if spectrum is not None:
            spectrum.set_sweep_mode(continuous=True)  # screen live again
            spectrum.close()
        append_rows(csv_path, RESULT_COLUMNS, rows)
        append_rows(trace_csv_path(csv_path), TRACE_COLUMNS,
                    [r for state_row, t in zip(rows, traces) for r in trace_rows([t], state=state_row["state"])])
        logging.info("Results written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return csv_path


def result_csv_path():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / "test_pollution_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))


def start_log_file():
    """Also write the log to results/logs/test_pollution_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "test_pollution_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # 100 kHz - 200 MHz: all off, SMU on at 0 V, SMU at 0.75 V, + 7.8125 MHz reference (~10 s per state)
        pollution_sweep()


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Repeated measurements of the PLL output pad on a spectrum analyzer, to compare analyzers (FSV / FSW43) and check that
# two measurements of the same signal agree. The PLL is NOT touched here: program it first with tests/pll_manual.py
# (keep that script running, or let it quit: the config stays on the chip) and set the supply and reference by hand.
# The PLL settings (VCO frequency, divider) are taken from pll_manual.CFG / F_REF, so the carrier search and the
# divider check use the config that is on the chip.
#
# Per entry of MEASUREMENTS: lib/pll_spectrum.measure_output on that analyzer (carrier, phase-noise markers, full
# curve with spurs, averaged spectrum, RMS jitter also over COMMON_BAND). The notebook
# sw/tools/notebooks/pll_analyzer.ipynb overlays two of them.
#
# Results:
#   results/pll/pll_analyzer_<stamp>.csv          one row per measurement
#   results/pll/pll_analyzer_<stamp>_traces.csv   averaged spectrum + phase-noise traces per measurement
#
# Tests:
#   measure_repeated(measurements, cfg, f_ref)   # one measure_output per (label, analyzer), one CSV
#

import logging
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import FILTER_FIELDS
from sw.lib.pll_spectrum import (FB_DIV, OUTPUT_COLUMNS, RESULTS_DIR, TRACE_FIELDS, append_rows, measure_output,
                                 offsets_for, trace_csv_path, trace_rows)
from sw.lib.vco_measure import load_instr_cfg
from sw.tests import pll_manual

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

FSW, FSV = "spectrum_analyzer", "spectrum_analyzer_fsv"  # meas_setup.yaml keys (spectrum_analyzer: the FSW43 now)
# (label, analyzer) per measurement, in order; the label names the curve in the notebook
MEASUREMENTS = [
    ("FSW 1", FSW),
    ("FSW 2", FSW),
]
COMMON_BAND = (1e3, 1e7)  # also integrated per measurement, as in pll_range.py

RESULT_COLUMNS = (["time", "label", "analyzer", "f_ref", "f_vco"] + list(vco_lut.LUT_FIELDS)
                  + list(FILTER_FIELDS) + ["set_div_freq", "total_div"] + OUTPUT_COLUMNS)
TRACE_COLUMNS = ["label", "analyzer"] + TRACE_FIELDS


def measure_repeated(measurements, cfg, f_ref, span=5e6, spectrum_averages=20, n_averages=10,
                     common_band=COMMON_BAND):
    """For every (label, analyzer) in `measurements`: measure the pad of the PLL running `cfg` on a reference of
    `f_ref` [Hz] (VCO = FB_DIV x f_ref) with measure_output on `analyzer` (meas_setup.yaml key). The PLL must already
    be configured and locked (pll_manual.py); cfg is only used for the expected frequencies and recorded. A failing
    measurement is recorded and the next one runs; a VISA error stops. Appends one row per measurement to a new
    results/pll/pll_analyzer_<stamp>.csv and the traces to <stem>_traces.csv; returns the CSV path."""
    instr_cfg = load_instr_cfg()
    f_vco = FB_DIV * f_ref
    _, total_div = calculate_div_factor(cfg)
    csv_path = RESULTS_DIR / "pll_analyzer_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for i, (label, analyzer) in enumerate(measurements, 1):
        logging.info("=== Measurement %d/%d: %s on %s, VCO %.1f MHz, pad %.4f MHz ===", i, len(measurements), label,
                     instr_cfg[analyzer]["name"], f_vco / 1e6, f_vco / total_div / 1e6)
        row = dict(time=datetime.now().isoformat(timespec="seconds"), label=label, analyzer=analyzer,
                   analyzer_name=instr_cfg[analyzer]["name"], f_ref=f_ref, f_vco=f_vco,
                   set_div_freq=cfg["set_div_freq"], total_div=total_div, status="error")
        row.update(vco_lut.vco_codes(cfg))
        row.update({k: cfg[k] for k in FILTER_FIELDS})
        traces = []
        try:
            meas, traces = measure_output(f_vco, total_div, offsets_for(f_vco / total_div), n_averages=n_averages,
                                          span=span, spectrum_averages=spectrum_averages, common_band=common_band,
                                          analyzer=analyzer)
            row.update(meas)
        except pyvisa.VisaIOError:
            raise  # instrument connection lost: stop
        except Exception:
            logging.exception("%s failed, continuing", label)
        finally:
            append_rows(csv_path, RESULT_COLUMNS, [row])
            append_rows(trace_csv_path(csv_path), TRACE_COLUMNS, trace_rows(traces, label=label, analyzer=analyzer))
    logging.info("Measurements written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return csv_path


def start_log_file():
    """Also write the log to results/logs/pll_analyzer_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_analyzer_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the analyzers
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # PLL programmed with pll_manual.py (CFG on F_REF = 32 MHz: VCO 4096 MHz, pad 64 MHz); supply and reference
        # set by hand. Two measurements on the FSW43 that should be identical (MEASUREMENTS).
        measure_repeated(MEASUREMENTS, pll_manual.CFG, pll_manual.F_REF)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

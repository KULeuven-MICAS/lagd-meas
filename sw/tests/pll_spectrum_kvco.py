# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Influence of Kvco on the locked PLL's spectrum and jitter. The VCO codes come from the lookup table
# (lib/vco_lut.py, VcoLUT) for f_vco and a requested |Kvco|; the loop is closed on a reference of
# f_vco / FB_DIV from the 33600A, the PLL supply is the 2450 SMU (current and power recorded). The output pad
# (VCO / 2**set_div_freq) is measured on the R&S FSV with lib/pll_spectrum.measure_output: phase-noise markers,
# the full phase-noise curve with spur detection, an averaged spectrum, and the RMS jitter from both.
#
# Results (plotted in sw/tools/notebooks/pll_spectrum_kvco.ipynb):
#   results/pll/pll_spectrum_kvco_<sample>_<stamp>.csv          one row per setting: codes, lock, L(f), jitter, supply
#   results/pll/pll_spectrum_kvco_<sample>_<stamp>_traces.csv   averaged spectrum + phase-noise traces per setting
#   results/pll/pll_spectrum_freq_<sample>_<stamp>[_traces].csv  frequency_sweep, same columns
#                                                               (sw/tools/notebooks/pll_spectrum_freq.ipynb)
#
# Tests:
#   measure_pll_kvco(f_vco, kvco, sample)   # one setting; kvco="middle": geometric middle of the possible |Kvco|
#   kvco_sweep(f_vco, n_kvco, sample)       # measure_pll_kvco for |Kvco| log-spaced over the table's range, one CSV
#   frequency_sweep(freqs, kvco, sample)   # measure_pll_kvco at several f_vco with the same requested |Kvco|, one CSV
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
from sw.lib.pll_settings import CFG_REF8
from sw.lib.pll_spectrum import (FB_DIV, OFFSET_SPAN_MAP, OUTPUT_COLUMNS, RBW_SPAN_RATIO, offsets_for, pad_divider,
                                 RESULTS_DIR, TRACE_FIELDS, append_rows, kvco_target_for, measure_output,
                                 open_spectrum, trace_csv_path, trace_rows)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Band integrated for every setting, so settings with different pad frequencies (and so different bands, up to
# pad / OUT_OFFSET_RATIO) can be compared: fits every pad frequency from PAD_F_MAX / 2 = 62.5 MHz up.
COMMON_BAND = (1e3, 1e7)
# Live spectrum shown on the analyzer during the pause of measure_pll_kvco(pause=True): carrier +- 1.25 MHz.
PAUSE_VIEW_SPAN = 2.5e6
# Frequencies of frequency_sweep (8: one notebook colour each); reference f / 128 = 2.3-31 MHz.
FREQ_SWEEP = (300e6, 500e6, 750e6, 1e9, 1.5e9, 2e9, 3e9, 4e9)

RESULT_COLUMNS = (["time", "lut_csv", "f_vco", "kvco_request", "kvco_target"] + list(vco_lut.LUT_FIELDS)
                  + ["vctrl_pred", "kvco_pred", "kvco_min", "kvco_max", "f_ref", "set_div_freq", "total_div",
                     "locked", "locked_after_pause"] + OUTPUT_COLUMNS + list(pll_setup.SUPPLY_COLUMNS))
TRACE_COLUMNS = ["f_vco", "kvco_target"] + TRACE_FIELDS


def loop_cfg(f_vco):
    """Closed-loop config (CFG_REF8 base: loop filter defaults, internal Vctrl) on the direct output (no external
    divider: pad = PLL output), divided inside the PLL to at most PAD_F_MAX on the pad (pll_spectrum.pad_divider).
    The VCO codes are added by VcoLUT.update_config."""
    return dict(CFG_REF8, pll_clk_o_en=1, set_div_freq=pad_divider(f_vco))


def measure_pll_kvco(f_vco=1e9, kvco="middle", sample=None, lut=None, csv_path=None, supply=None,
                     span=5e6, spectrum_averages=20, n_averages=10, offset_span_map=None, lock_timeout=3.0,
                     pause=False, skip_unlocked=True, common_band=COMMON_BAND):
    """Lock the PLL at `f_vco` [Hz] with VCO codes from the lookup table for |Kvco| `kvco` [Hz/V] (or "middle"),
    then measure the output pad with pll_spectrum.measure_output (markers, full curve with spurs, spectrum, jitter).

    `skip_unlocked`: no analyzer measurement when the PLL did not lock (status "not_locked").
    `common_band`: also integrate the jitter over only this band (time_jitter_common_ps / time_jitter_trace_common_ps).
    `pause`: after the PLL is configured and locked, show the live spectrum and wait for Enter before measuring (e.g.
    to switch off the PCB 5 V); the lock is read again afterwards and the PLL supply current is measured after it.
    The reference (f_vco / FB_DIV from the 33600A) is started here and turned off at the end; the PLL supply
    `supply` (pll_setup.pll_supply) must already be on. Every connection is closed at the end, also on an error.
    `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`.
    Appends one row to `csv_path` (default a new results/pll/pll_spectrum_kvco_<sample>_<stamp>.csv) and the
    traces to <stem>_traces.csv; returns the row.
    """
    offset_span_map = offset_span_map or OFFSET_SPAN_MAP
    csv_path = csv_path or result_csv_path(sample)
    lut = lut or vco_lut.VcoLUT(sample=sample)
    target, kvco_min, kvco_max = kvco_target_for(lut, f_vco, kvco)
    cfg = lut.update_config(loop_cfg(f_vco), f_vco, target)
    op = lut.predict(cfg, f_vco)
    _, total_div = calculate_div_factor(cfg)
    offset_span_map = offsets_for(f_vco / total_div, offset_span_map)  # band limited by the pad frequency
    f_ref = f_vco / FB_DIV
    row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, f_vco=f_vco,
               kvco_request=kvco, kvco_target=target, kvco_min=kvco_min, kvco_max=kvco_max, f_ref=f_ref,
               set_div_freq=cfg["set_div_freq"], total_div=total_div, status="error", **vco_lut.vco_codes(cfg), **op)
    traces = []

    fg = pll = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=lock_timeout)
        row["locked"] = int(locked)
        logging.info("PLL %s at %.1f MHz (ref %.4f MHz x %d), Vctrl ~%.3f V, |Kvco| %.0f MHz/V; "
                     "/%d inside the PLL, no external divider -> PLL output = pad %.4f MHz",
                     "LOCKED" if locked else "NOT LOCKED", f_vco / 1e6, f_ref / 1e6, FB_DIV, op["vctrl_pred"],
                     op["kvco_pred"] / 1e6, total_div, f_vco / total_div / 1e6)
        row.update(pll_setup.measure_pll_supply(supply, label="%.1f MHz, |Kvco| %.0f MHz/V" % (
            f_vco / 1e6, op["kvco_pred"] / 1e6)))
        if pause:
            # Live spectrum while waiting: carrier +- PAUSE_VIEW_SPAN / 2, continuous sweep, so the effect of switching
            # off the 5 V shows directly. Closed again after Enter (the measurement starts from a fresh reset).
            view = open_spectrum()
            try:
                view.set_center_frequency(f_vco / total_div)
                view.set_span(PAUSE_VIEW_SPAN)
                view.set_bandwidths_for_span(PAUSE_VIEW_SPAN, RBW_SPAN_RATIO)
                view.set_sweep_mode(continuous=True)
                view.set_display_update(True)
                input("PLL configured (%s); the analyzer shows the live spectrum. Switch off the PCB 5 V now, then "
                      "press Enter to measure..." % ("locked" if locked else "NOT locked"))
            finally:
                view.close()
            lock = pll.read_lock()  # None: no answer from the chip (e.g. its IO is unpowered now)
            row["locked_after_pause"] = lock
            logging.info("After the pause: lock bit %s", "no answer" if lock is None else lock)
            row.update(pll_setup.measure_pll_supply(supply, label="after the pause"))

        if not locked and skip_unlocked:
            # No lock: no carrier at f_vco / N either; the analyzer would only measure noise
            logging.warning("Not locked: setting not measured (|Kvco| %.0f MHz/V)", op["kvco_pred"] / 1e6)
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
        append_rows(trace_csv_path(csv_path), TRACE_COLUMNS, trace_rows(traces, f_vco=f_vco, kvco_target=target))
        logging.info("Results written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return row


def kvco_sweep(f_vco=1e9, n_kvco=8, sample=None, lut=None, supply=None, **kwargs):
    """measure_pll_kvco for `n_kvco` |Kvco| targets log-spaced over the range the lookup table offers at f_vco (inside
    the Vctrl window), all into one CSV. Targets that pick the same VCO codes as an earlier one are skipped. A setting
    that fails (no lock, instrument error) is recorded and the sweep continues; a VISA error stops it (outputs off).
    `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`.
    `kwargs` go to measure_pll_kvco. Returns the CSV path.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample)
    k_min, k_max = lut.kvco_range(f_vco)
    targets = np.geomspace(k_min, k_max, n_kvco)
    picks, seen = [], []
    for k in targets:
        codes = vco_lut.vco_codes(lut.update_config(loop_cfg(f_vco), f_vco, k))
        if codes in seen:
            logging.info("|Kvco| %.0f MHz/V: same setting as before (%s), skipped", k / 1e6, codes)
            continue
        seen.append(codes)
        picks.append(float(k))
    logging.info("Kvco sweep at %.1f MHz: %d settings, |Kvco| targets %s MHz/V (table range %.0f-%.0f MHz/V)",
                 f_vco / 1e6, len(picks), ", ".join("{:.0f}".format(k / 1e6) for k in picks), k_min / 1e6, k_max / 1e6)

    csv_path = result_csv_path(sample)
    for i, k in enumerate(picks, 1):
        logging.info("=== Kvco sweep %d/%d: |Kvco| %.0f MHz/V ===", i, len(picks), k / 1e6)
        try:
            measure_pll_kvco(f_vco, k, sample=sample, lut=lut, csv_path=csv_path, supply=supply, **kwargs)
        except pyvisa.VisaIOError:
            raise  # instrument connection lost: stop, outputs off in the callers
        except Exception:
            logging.exception("Setting %d (|Kvco| %.0f MHz/V) failed, continuing", i, k / 1e6)
    logging.info("Kvco sweep written to %s", csv_path)
    return csv_path


def frequency_sweep(freqs=FREQ_SWEEP, kvco=2e9, sample=None, lut=None, supply=None, **kwargs):
    """measure_pll_kvco at every f_vco in `freqs` [Hz] with the same requested |Kvco| `kvco` [Hz/V], all into one CSV:
    the lookup table picks per frequency the setting closest to that Kvco (the log shows what it reached and the
    possible range). The reference follows (f_vco / FB_DIV), the output divider too (pad <= PAD_F_MAX; the band stops at
    pad / OUT_OFFSET_RATIO). A frequency that fails is recorded and the sweep continues; a VISA error stops it.
    `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`.
    `kwargs` go to measure_pll_kvco. Returns the CSV path.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample)
    csv_path = result_csv_path(sample, prefix="pll_spectrum_freq")
    logging.info("Frequency sweep at |Kvco| ~%.0f MHz/V: %s MHz", kvco / 1e6,
                 ", ".join("{:g}".format(f / 1e6) for f in freqs))
    for i, f in enumerate(freqs, 1):
        logging.info("=== Frequency sweep %d/%d: %.1f MHz ===", i, len(freqs), f / 1e6)
        try:
            measure_pll_kvco(f, kvco, sample=sample, lut=lut, csv_path=csv_path, supply=supply, **kwargs)
        except pyvisa.VisaIOError:
            raise  # instrument connection lost: stop, outputs off in the callers
        except Exception:
            logging.exception("%.1f MHz failed, continuing", f / 1e6)
    logging.info("Frequency sweep written to %s", csv_path)
    return csv_path


def result_csv_path(sample, prefix="pll_spectrum_kvco"):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / "{}_{}_{}.csv".format(prefix, sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def start_log_file():
    """Also write the log to results/logs/pll_spectrum_kvco_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_spectrum_kvco_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
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
            # 1 GHz (ref 7.8125 MHz), |Kvco| in the geometric middle of what the S5 table offers at 1 GHz
            # phase-noise markers + full curve with spur detection, averaged spectrum
            # pause=True: switch off the PCB 5 V after the PLL is configured, then press Enter
            # measure_pll_kvco(1e9, "middle", sample="S5", supply=supply, pause=True)

            # Kvco sweep at 1 GHz: 8 |Kvco| targets log-spaced over the S5 table's range, everything measured per
            # setting, one CSV for sw/tools/notebooks/pll_spectrum_kvco.ipynb (~2 min per setting)
            # kvco_sweep(1e9, n_kvco=8, sample="S5", supply=supply)

            # Frequency sweep at |Kvco| ~2 GHz/V: FREQ_SWEEP (300 MHz - 4 GHz), everything measured per frequency
            frequency_sweep(FREQ_SWEEP, kvco=2e9, sample="S5", supply=supply)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

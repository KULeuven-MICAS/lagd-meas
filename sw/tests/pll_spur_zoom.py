# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Close look at the ~1.95 MHz spur / bump. It is in every PLL and open-loop VCO measurement (2026-10-20/21),
# independent of the loop gain, the VCO codes, Vctrl, the Vctrl source and the reference, and it is not on the PCB,
# the FPGA board or the instruments: the suspect is the chip itself. The free-running VCO wanders too much for a
# narrow RBW, so the PLL is locked (carrier still) at settings where the spur is known, and the analyzer zooms into it
# on both sidebands of the carrier on the pad:
#   carrier   the carrier itself (span CARRIER_STEP): its exact frequency and width, the reference for dBc
#   zoom 1-3  ZOOM_STEPS, each centred on the peak of the previous one (the first at carrier +- SPUR_OFFSET): from the
#             whole bump down to the line, RBW 1 kHz -> 10 Hz. A line much wider than the carrier: the source itself
#             wanders (or is spread spectrum); a line as narrow as the carrier: a stable tone
#   sequence  SEQUENCE_N single sweeps (no averaging) around the upper spur: does it move with time?
# Two settings with a different VCO frequency, reference and pad divider (SPUR_POINTS): an offset that stays the same
# is independent of the PLL's own frequencies.
#
# Results (plotted in sw/tools/notebooks/pll_spur_zoom.ipynb):
#   results/pll/pll_spur_zoom_<sample>_<stamp>.csv          one row per capture: peak frequency, offset, level
#   results/pll/pll_spur_zoom_<sample>_<stamp>_traces.csv   the traces (one row per point)
#
# Tests:
#   spur_zoom(points, sample)    # every point of SPUR_POINTS: lock, carrier, zooms on both sidebands, sequence
#   spur_perturb(point, sample, chip)  # interactive: the hump and lines per chip condition you set (or !reset / !run /
#                                      # !clkoff), to see which change moves them
#   spur_supply_sweep(vdds, sample, chip)  # spur_perturb over the PLL supply voltages you set one by one
#   spur_showcase(points, sample)          # spectra for the plots: carrier, hump and lines in one trace per span
#   spur_supply_showcase(vdds, sample)     # the spur_showcase spectra per PLL supply voltage you set one by one
#

import csv
import logging
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pyvisa

from sw.lib import pll_setup
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import FILTER_FIELDS, LOOP_FILTER
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows, open_spectrum
from sw.lib.vco_lut import LUT_FIELDS
from sw.tests.pll_test_vctrl import loop_cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Locked settings with a strong ~1.95 MHz spur: c9 min 9 max 0 at 760 MHz with C1 7 and Icp 4 (loop-gain sweep
# pll_test_current_max_S5_20261020_200224: -22 dBc in the spur list) and c9 min 14 max 0 at 1 GHz with LOOP_FILTER
# (pll_test_current_max_S5_20261020_150031). Different f_vco, reference (f_vco / FB_DIV) and pad divider (/8, /16).
SPUR_POINTS = (
    dict(label="c9 min9 max0 760MHz", f_vco=760e6, codes=dict(vco_tune_coarse=9, vco_current_min=9, vco_current_max=0),
         loop_filter=dict(LOOP_FILTER, set_current=4, set_c1=7)),
    dict(label="c9 min14 max0 1GHz", f_vco=1e9, codes=dict(vco_tune_coarse=9, vco_current_min=14, vco_current_max=0),
         loop_filter=dict(LOOP_FILTER)),
)
SPUR_OFFSET = 1.95e6  # [Hz] where the first zoom is centred, on both sides of the carrier
# (span [Hz], RBW [Hz], averages): the carrier, and the zooms into the spur (each centred on the previous peak)
CARRIER_STEP = (2e3, 10.0, 5)
ZOOM_STEPS = ((1e6, 1e3, 10), (50e3, 100.0, 10), (2e3, 10.0, 5))
# Single sweeps around the upper spur, one after the other: (number, span [Hz], RBW [Hz])
SEQUENCE_N, SEQUENCE_SPAN, SEQUENCE_RBW = 30, 200e3, 1e3
LOCK_TIMEOUT = 3.0
LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

CAPTURE_COLUMNS = (["time", "label", "f_vco", "f_ref"] + list(LUT_FIELDS) + list(FILTER_FIELDS)
                   + ["set_div_freq", "total_div", "f_pad", "locked", "f_carrier", "carrier_dbm", "sideband", "step",
                      "index", "center", "span", "rbw", "averages", "peak_freq", "peak_offset", "peak_dbc"])
TRACE_COLUMNS = ["label", "sideband", "step", "index", "center", "span", "rbw", "freq", "level_dbm"]

# spur_perturb (interactive): the PLL locked once at PERTURB_POINT, then per condition you set on the chip (typed label,
# or a command below that the script sets itself) the same captures, so the conditions compare one to one:
#   carrier  CARRIER_STEP
#   wide     both sidebands over WIDE_OFFSETS [Hz] from the carrier, RBW WIDE_RBW, WIDE_AVERAGES sweeps: the whole
#            hump and every line; the floor (lower FLOOR_QUANTILE of FLOOR_BIN [Hz] bins, the lines left out) gives the
#            hump's peak
#   track    the upper sideband around each of TRACK_LINES [Hz] (span TRACK_SPAN, RBW TRACK_RBW): their exact offsets,
#            to see a line move by a few hundred Hz
PERTURB_POINT = SPUR_POINTS[0]  # c9 760 MHz: lines and hump strongest
WIDE_OFFSETS = (0.2e6, 3.0e6)
WIDE_RBW, WIDE_AVERAGES = 1e3, 10
WIDE_POINTS = 14001  # ~5 points per RBW over the wide span (also used by the other captures)
FLOOR_BIN, FLOOR_QUANTILE = 50e3, 0.2
TRACK_LINES = (556e3, 704e3, 1587e3, 1881e3, 1948e3, 2117e3, 2382e3)
TRACK_SPAN, TRACK_RBW, TRACK_AVERAGES = 20e3, 100.0, 5
# Commands at the prompt: the chip state the script sets (ChipDriver.hold_reset), with the label it records
CHIP_COMMANDS = {
    "!reset": (dict(held=True, chip_clk_en=1), "core in reset, chip clock on"),
    "!run": (dict(held=False, chip_clk_en=1), "core running"),
    "!clkoff": (dict(held=True, chip_clk_en=0), "core in reset, chip clock off"),
}
# spur_showcase: spectra for the plots, centred on the carrier (both sidebands): (span [Hz], RBW [Hz], averages).
# +-3 MHz at 1 kHz shows the hump and every line; +-10 MHz at 3 kHz the surroundings; +-1 MHz at 300 Hz the 556 / 704
# kHz lines.
SHOWCASE_CAPTURES = ((6e6, 1e3, 50), (20e6, 3e3, 30), (2e6, 300.0, 30))
MAX_SWEEP_POINTS = 32001  # the driver's limit (set_sweep_points)
# spur_supply_sweep: PLL supply voltages [V] to set one after the other (nominal 0.75 V first and last: drift check)
PLL_VDD_SWEEP = (0.75, 0.80, 0.85, 0.70, 0.675, 0.65, 0.625, 0.60, 0.75)
PERTURB_COLUMNS = CAPTURE_COLUMNS + ["condition", "condition_label", "hump_offset", "hump_dbc"]
PERTURB_TRACE_COLUMNS = ["condition", "condition_label"] + TRACE_COLUMNS


def peak_of(trace):
    """(frequency [Hz], level [dBm]) of the highest point of a trace."""
    i = int(np.argmax(trace["level"]))
    return trace["freq"][i], trace["level"][i]


def spur_zoom_point(point, csv_path):
    """Lock the PLL at `point` (SPUR_POINTS entry) and capture the carrier, the ZOOM_STEPS on both sidebands and the
    sequence of single sweeps; appends the rows and traces. Reference off and every connection closed at the end,
    also on an error."""
    cfg = dict(loop_cfg(point["f_vco"], loop_filter=point["loop_filter"]), **point["codes"])
    _, total_div = calculate_div_factor(cfg)
    f_ref, f_pad = point["f_vco"] / FB_DIV, point["f_vco"] / total_div
    base = dict(time=datetime.now().isoformat(timespec="seconds"), label=point["label"], f_vco=point["f_vco"],
                f_ref=f_ref, set_div_freq=cfg["set_div_freq"], total_div=total_div, f_pad=f_pad,
                **point["codes"], **{k: cfg[k] for k in FILTER_FIELDS})
    rows, traces = [], []

    def record(step, sideband, index, t, f_carrier, carrier_dbm, averages):
        f_peak, l_peak = peak_of(t)
        rows.append(dict(base, f_carrier=f_carrier, carrier_dbm=carrier_dbm, sideband=sideband, step=step,
                         index=index, center=t["center"], span=t["span"], rbw=t["rbw"], averages=averages,
                         peak_freq=f_peak, peak_offset=f_peak - f_carrier, peak_dbc=l_peak - carrier_dbm))
        traces.extend(dict(label=point["label"], sideband=sideband, step=step, index=index, center=t["center"],
                           span=t["span"], rbw=t["rbw"], freq=f, level_dbm=l) for f, l in zip(t["freq"], t["level"]))
        return f_peak, l_peak

    fg = pll = spectrum = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=LOCK_TIMEOUT)
        base["locked"] = int(locked)
        logging.info("=== %s: PLL %s at %.1f MHz (ref %.4f MHz), pad %.4f MHz (/%d) ===", point["label"],
                     "LOCKED" if locked else "NOT LOCKED", point["f_vco"] / 1e6, f_ref / 1e6, f_pad / 1e6, total_div)
        if not locked:
            append_rows(csv_path, CAPTURE_COLUMNS, [dict(base, step="not_locked")])
            return

        spectrum = open_spectrum()
        spectrum.center_on_fundamental(center_freq=f_pad)  # reference level above the carrier
        span, rbw, avg = CARRIER_STEP
        f_carrier, carrier_dbm = peak_of(spectrum.averaged_trace(f_pad, span, averages=avg, rbw=rbw))
        t = spectrum.averaged_trace(f_carrier, span, averages=avg, rbw=rbw)
        record("carrier", 0, 0, t, f_carrier, carrier_dbm, avg)
        logging.info("carrier %.6f MHz, %.1f dBm", f_carrier / 1e6, carrier_dbm)

        for sideband in (1, -1):
            center = f_carrier + sideband * SPUR_OFFSET
            for i, (span, rbw, avg) in enumerate(ZOOM_STEPS, 1):
                t = spectrum.averaged_trace(center, span, averages=avg, rbw=rbw)
                center, level = record("zoom%d" % i, sideband, i, t, f_carrier, carrier_dbm, avg)
                logging.info("  %s sideband, zoom %d (span %g Hz, RBW %g Hz): peak at offset %+.3f kHz, %.1f dBc",
                             "upper" if sideband > 0 else "lower", i, span, rbw, (center - f_carrier) / 1e3,
                             level - carrier_dbm)

        upper = next(r["peak_freq"] for r in reversed(rows) if r["sideband"] == 1)
        for i in range(1, SEQUENCE_N + 1):
            t = spectrum.averaged_trace(upper, SEQUENCE_SPAN, averages=1, rbw=SEQUENCE_RBW)
            record("sequence", 1, i, t, f_carrier, carrier_dbm, 1)
        seq = [r["peak_offset"] for r in rows if r["step"] == "sequence"]
        logging.info("  sequence of %d single sweeps: spur offset %.3f-%.3f kHz (spread %.3f kHz)", len(seq),
                     min(seq) / 1e3, max(seq) / 1e3, (max(seq) - min(seq)) / 1e3)
    finally:
        if spectrum is not None:
            spectrum.set_sweep_mode(continuous=True)  # screen live again
            spectrum.close()
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
        append_rows(csv_path, CAPTURE_COLUMNS, rows)
        append_rows(csv_path.with_name(csv_path.stem + "_traces.csv"), TRACE_COLUMNS, traces)


def spur_zoom(points=SPUR_POINTS, sample=None):
    """spur_zoom_point for every point of `points`, all into one results/pll/pll_spur_zoom_<sample>_<stamp>.csv
    (+ _traces.csv). Returns the CSV path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_spur_zoom_{}_{}.csv".format(sample or "nosample",
                                                              datetime.now().strftime("%Y%m%d_%H%M%S"))
    for point in points:
        try:
            spur_zoom_point(point, csv_path)
        except pyvisa.VisaIOError:
            raise  # instrument connection lost: stop (reference off in spur_zoom_point)
        except Exception:
            logging.exception("%s failed, continuing", point["label"])
    logging.info("Spur zoom written to %s", csv_path)
    return csv_path


def hump_of(trace, f_carrier, sideband):
    """(offset [Hz], level [dBm]) of the floor's maximum in a wide trace: per FLOOR_BIN bin of the offset the lower
    FLOOR_QUANTILE of the points (the lines left out), the bin with the highest value."""
    offset = (np.asarray(trace["freq"], dtype=float) - f_carrier) * sideband
    level = np.asarray(trace["level"], dtype=float)
    bins = np.floor(offset / FLOOR_BIN)
    floors = [(b, np.percentile(level[bins == b], 100 * FLOOR_QUANTILE)) for b in np.unique(bins)]
    b, floor = max(floors, key=lambda x: x[1])
    return (b + 0.5) * FLOOR_BIN, floor


def ask_condition(last):
    """Wait for the next condition: a label for what you changed on the chip, a CHIP_COMMANDS command (the script
    sets that chip state; text after it is added to the label), Enter (the same label again: a repeat) or q (stop).
    Returns (label, chip state dict or None) or None to stop."""
    while True:
        answer = input("\n>>> Set the next condition, then type its label (or %s; Enter = repeat '%s', q = stop): "
                       % (" / ".join(CHIP_COMMANDS), last)).strip()
        if answer.lower() == "q":
            return None
        if answer == "":
            if last:
                return last, None
            print("No previous label: type one")
            continue
        command, _, extra = answer.partition(" ")
        if command in CHIP_COMMANDS:
            state, label = CHIP_COMMANDS[command]
            return (label + (", " + extra if extra else "")), state
        return answer, None


def ask_planned(label):
    """Wait until the user has set the planned condition `label`. Returns (label, None), "skip" or None to stop."""
    answer = input("\n>>> Set: %s, then press Enter (s = skip, q = stop): " % label).strip().lower()
    if answer == "q":
        return None
    if answer == "s":
        return "skip"
    return label, None


def spur_perturb(point=PERTURB_POINT, sample=None, chip=None, planned=None, prefix="pll_spur_perturb", csv_path=None):
    """Interactive: which changes on the chip move the ~2 MHz hump and lines? The PLL is locked once at `point`
    (SPUR_POINTS entry, Vctrl pad off) and stays locked; then, per condition (ask_condition: you change one thing on
    the chip and type a label, or a CHIP_COMMANDS command that `chip`, the ChipDriver of pll_setup.core_in_reset,
    sets), the carrier, the wide captures on both sidebands (WIDE_OFFSETS) and the tracked lines (TRACK_LINES) are
    taken. The first condition is the reference: leave everything as it is. The PLL lock is checked per condition
    (not locked: the config is loaded again). `planned`: a list of condition labels to go through in order instead
    (ask_planned: you set each and press Enter), e.g. spur_supply_sweep. `prefix`: the CSV name. `csv_path`: an earlier
    run's CSV to add these conditions to (numbered on after its last condition, so they plot on top of it); None =
    a new CSV.
    One row per capture in results/pll/pll_spur_perturb_<sample>_<stamp>.csv (condition number and label, the hump's
    floor maximum for the wide captures), traces in <stem>_traces.csv. Reference off and every connection closed at
    the end, also on an error. Returns the CSV path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if csv_path is None:
        csv_path = RESULTS_DIR / "{}_{}_{}.csv".format(prefix, sample or "nosample",
                                                       datetime.now().strftime("%Y%m%d_%H%M%S"))
        n_before = 0
    else:
        csv_path = Path(csv_path)
        with open(csv_path, newline="") as f:
            n_before = max(int(row["condition"]) for row in csv.DictReader(f))
        logging.info("Adding to %s after its condition %d", csv_path, n_before)
    trace_path = csv_path.with_name(csv_path.stem + "_traces.csv")
    cfg = dict(loop_cfg(point["f_vco"], loop_filter=point["loop_filter"]), **point["codes"])
    _, total_div = calculate_div_factor(cfg)
    f_ref, f_pad = point["f_vco"] / FB_DIV, point["f_vco"] / total_div
    base = dict(label=point["label"], f_vco=point["f_vco"], f_ref=f_ref, set_div_freq=cfg["set_div_freq"],
                total_div=total_div, f_pad=f_pad, **point["codes"], **{k: cfg[k] for k in FILTER_FIELDS})
    wide_span = WIDE_OFFSETS[1] - WIDE_OFFSETS[0]
    wide_mid = (WIDE_OFFSETS[0] + WIDE_OFFSETS[1]) / 2

    fg = pll = spectrum = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        pll = pll_setup.open_pll(cfg)  # stays open: the lock is checked per condition
        logging.info("=== %s: PLL %s at %.1f MHz (ref %.4f MHz), pad %.4f MHz (/%d) ===", point["label"],
                     "LOCKED" if pll.wait_lock(timeout=LOCK_TIMEOUT) else "NOT LOCKED", point["f_vco"] / 1e6,
                     f_ref / 1e6, f_pad / 1e6, total_div)
        spectrum = open_spectrum()
        spectrum.center_on_fundamental(center_freq=f_pad)  # reference level above the carrier
        spectrum.set_sweep_points(WIDE_POINTS)
        last, n = "", n_before
        todo = list(planned) if planned is not None else None
        while True:
            spectrum.live_view(f_pad, 2 * WIDE_OFFSETS[1])  # the screen live while you change things
            if todo is None:
                answer = ask_condition(last or "reference")
            elif todo:
                answer = ask_planned(todo.pop(0))
                if answer == "skip":
                    continue
            else:
                answer = None
            if answer is None:
                break
            label, state = answer
            if state is not None:
                if chip is None:
                    logging.warning("No chip driver: '%s' not set, skipped", label)
                    continue
                chip.hold_reset(**state)
                time.sleep(1.0)
            n, last = n + 1, label
            locked = pll.wait_lock(timeout=LOCK_TIMEOUT)
            if not locked:  # e.g. after a supply step: load the config again
                pll_setup.load_config(pll, cfg)
                locked = pll.wait_lock(timeout=LOCK_TIMEOUT)
                logging.info("Config reloaded: PLL %s", "locked" if locked else "NOT LOCKED")
            rows, traces = [], []
            cond = dict(base, time=datetime.now().isoformat(timespec="seconds"), locked=int(locked), condition=n,
                        condition_label=label)

            def record(step, sideband, index, t, f_carrier, carrier_dbm, averages, **extra):
                f_peak, l_peak = peak_of(t)
                rows.append(dict(cond, f_carrier=f_carrier, carrier_dbm=carrier_dbm, sideband=sideband, step=step,
                                 index=index, center=t["center"], span=t["span"], rbw=t["rbw"], averages=averages,
                                 peak_freq=f_peak, peak_offset=f_peak - f_carrier, peak_dbc=l_peak - carrier_dbm,
                                 **extra))
                traces.extend(dict(condition=n, condition_label=label, label=point["label"], sideband=sideband,
                                   step=step, index=index, center=t["center"], span=t["span"], rbw=t["rbw"], freq=f,
                                   level_dbm=l) for f, l in zip(t["freq"], t["level"]))
                return f_peak, l_peak

            span, rbw, avg = CARRIER_STEP
            t = spectrum.averaged_trace(f_pad, span, averages=avg, rbw=rbw)
            f_carrier, carrier_dbm = peak_of(t)
            record("carrier", 0, 0, t, f_carrier, carrier_dbm, avg)
            logging.info("--- condition %d '%s': PLL %s, carrier %.6f MHz, %.1f dBm", n, label,
                         "locked" if locked else "NOT LOCKED", f_carrier / 1e6, carrier_dbm)
            for sideband in (1, -1):
                t = spectrum.averaged_trace(f_carrier + sideband * wide_mid, wide_span, averages=WIDE_AVERAGES,
                                            rbw=WIDE_RBW)
                hump_offset, hump_level = hump_of(t, f_carrier, sideband)
                record("wide", sideband, 0, t, f_carrier, carrier_dbm, WIDE_AVERAGES, hump_offset=hump_offset,
                       hump_dbc=hump_level - carrier_dbm)
                logging.info("  %s sideband: hump (floor) maximum at %.0f kHz, %.1f dBc in %g Hz",
                             "upper" if sideband > 0 else "lower", hump_offset / 1e3, hump_level - carrier_dbm,
                             WIDE_RBW)
            for i, line in enumerate(TRACK_LINES, 1):
                t = spectrum.averaged_trace(f_carrier + line, TRACK_SPAN, averages=TRACK_AVERAGES, rbw=TRACK_RBW)
                f_peak, level = record("track", 1, i, t, f_carrier, carrier_dbm, TRACK_AVERAGES)
                logging.info("  line ~%.0f kHz: %.3f kHz, %.1f dBc", line / 1e3, (f_peak - f_carrier) / 1e3,
                             level - carrier_dbm)
            append_rows(csv_path, PERTURB_COLUMNS, rows)  # saved per condition
            append_rows(trace_path, PERTURB_TRACE_COLUMNS, traces)
    finally:
        if chip is not None:
            chip.hold_reset(True)  # back to the default: core in reset, chip clock on
        if spectrum is not None:
            spectrum.set_sweep_mode(continuous=True)
            spectrum.close()
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
    logging.info("Spur perturbation written to %s", csv_path)
    return csv_path


def showcase_traces(spectrum, f_pad, captures=SHOWCASE_CAPTURES):
    """On a locked PLL: the carrier near `f_pad` [Hz] (CARRIER_STEP, the dBc reference) and one averaged trace per
    (span, RBW, averages) of `captures` centred on it (~5 points per RBW, at most MAX_SWEEP_POINTS). The analyzer's
    reference level is set above the carrier first. Returns (f_carrier [Hz], carrier [dBm], traces: the driver's
    averaged_trace dicts plus 'averages')."""
    spectrum.center_on_fundamental(center_freq=f_pad)
    span, rbw, avg = CARRIER_STEP
    spectrum.set_sweep_points(WIDE_POINTS)
    f_carrier, carrier_dbm = peak_of(spectrum.averaged_trace(f_pad, span, averages=avg, rbw=rbw))
    traces = []
    for span, rbw, avg in captures:
        spectrum.set_sweep_points(min(MAX_SWEEP_POINTS, int(5 * span / rbw) + 1))
        traces.append(spectrum.averaged_trace(f_carrier, span, averages=avg, rbw=rbw))
        logging.info("  spectrum: span %g MHz, RBW %g Hz, %d averages", span / 1e6, traces[-1]["rbw"], avg)
    return f_carrier, carrier_dbm, traces


def spur_showcase(points=SPUR_POINTS, captures=SHOWCASE_CAPTURES, sample=None):
    """Spectra for the plots: per point of `points` the PLL locked and per (span, RBW, averages) of `captures` one
    averaged trace centred on the carrier (both sidebands, hump and lines in one picture), ~5 points per RBW (at most
    MAX_SWEEP_POINTS). Into results/pll/pll_spur_showcase_<sample>_<stamp>.csv (one row per capture, the carrier as the
    dBc reference) and <stem>_traces.csv. Reference off and every connection closed after each point, also on an
    error. Returns the CSV path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_spur_showcase_{}_{}.csv".format(sample or "nosample",
                                                                  datetime.now().strftime("%Y%m%d_%H%M%S"))
    for point in points:
        cfg = dict(loop_cfg(point["f_vco"], loop_filter=point["loop_filter"]), **point["codes"])
        _, total_div = calculate_div_factor(cfg)
        f_ref, f_pad = point["f_vco"] / FB_DIV, point["f_vco"] / total_div
        base = dict(time=datetime.now().isoformat(timespec="seconds"), label=point["label"], f_vco=point["f_vco"],
                    f_ref=f_ref, set_div_freq=cfg["set_div_freq"], total_div=total_div, f_pad=f_pad,
                    **point["codes"], **{k: cfg[k] for k in FILTER_FIELDS})
        rows, traces = [], []
        fg = pll = spectrum = None
        try:
            fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
            pll = pll_setup.open_pll(cfg)
            base["locked"] = int(pll.wait_lock(timeout=LOCK_TIMEOUT))
            logging.info("=== %s: PLL %s, pad %.4f MHz (/%d) ===", point["label"],
                         "LOCKED" if base["locked"] else "NOT LOCKED", f_pad / 1e6, total_div)
            spectrum = open_spectrum()
            spectrum.center_on_fundamental(center_freq=f_pad)  # reference level above the carrier
            span, rbw, avg = CARRIER_STEP
            f_carrier, carrier_dbm = peak_of(spectrum.averaged_trace(f_pad, span, averages=avg, rbw=rbw))
            for i, (span, rbw, avg) in enumerate(captures, 1):
                spectrum.set_sweep_points(min(MAX_SWEEP_POINTS, int(5 * span / rbw) + 1))
                t = spectrum.averaged_trace(f_carrier, span, averages=avg, rbw=rbw)
                rows.append(dict(base, f_carrier=f_carrier, carrier_dbm=carrier_dbm, sideband=0, step="showcase",
                                 index=i, center=t["center"], span=t["span"], rbw=t["rbw"], averages=avg))
                traces.extend(dict(label=point["label"], sideband=0, step="showcase", index=i, center=t["center"],
                                   span=t["span"], rbw=t["rbw"], freq=f, level_dbm=l)
                              for f, l in zip(t["freq"], t["level"]))
                logging.info("  span %g MHz, RBW %g Hz, %d averages: %d points", span / 1e6, t["rbw"], avg,
                             len(t["freq"]))
        except pyvisa.VisaIOError:
            raise  # instrument connection lost: stop (reference off below)
        except Exception:
            logging.exception("%s failed, continuing", point["label"])
        finally:
            if spectrum is not None:
                spectrum.set_sweep_mode(continuous=True)
                spectrum.close()
            if pll is not None:
                pll.close()
            if fg is not None:
                fg.close()  # reference off
            append_rows(csv_path, CAPTURE_COLUMNS, rows)
            append_rows(csv_path.with_name(csv_path.stem + "_traces.csv"), TRACE_COLUMNS, traces)
    logging.info("Spur showcase written to %s", csv_path)
    return csv_path


def spur_supply_showcase(vdds=PLL_VDD_SWEEP, point=PERTURB_POINT, captures=SHOWCASE_CAPTURES, sample=None):
    """The spur_showcase spectra over the PLL supply: the PLL locked once at `point`, then per voltage of `vdds` [V]
    (you set it on the PLL supply and press Enter; s = skip, q = stop) the carrier and every (span, RBW, averages) of
    `captures`, centred on the carrier (the config is loaded again when the PLL lost lock). Into
    results/pll/pll_spur_vdd_showcase_<sample>_<stamp>.csv (condition label "PLL VDD x.xxx V") and <stem>_traces.csv,
    saved per voltage. Reference off and every connection closed at the end, also on an error. Returns the CSV path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_spur_vdd_showcase_{}_{}.csv".format(sample or "nosample",
                                                                      datetime.now().strftime("%Y%m%d_%H%M%S"))
    trace_path = csv_path.with_name(csv_path.stem + "_traces.csv")
    cfg = dict(loop_cfg(point["f_vco"], loop_filter=point["loop_filter"]), **point["codes"])
    _, total_div = calculate_div_factor(cfg)
    f_ref, f_pad = point["f_vco"] / FB_DIV, point["f_vco"] / total_div
    base = dict(label=point["label"], f_vco=point["f_vco"], f_ref=f_ref, set_div_freq=cfg["set_div_freq"],
                total_div=total_div, f_pad=f_pad, **point["codes"], **{k: cfg[k] for k in FILTER_FIELDS})
    fg = pll = spectrum = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        pll = pll_setup.open_pll(cfg)  # stays open: the lock is checked per voltage
        logging.info("=== %s: PLL %s, pad %.4f MHz (/%d) ===", point["label"],
                     "LOCKED" if pll.wait_lock(timeout=LOCK_TIMEOUT) else "NOT LOCKED", f_pad / 1e6, total_div)
        spectrum = open_spectrum()
        spectrum.center_on_fundamental(center_freq=f_pad)  # reference level above the carrier
        n = 0
        for vdd in vdds:
            spectrum.live_view(f_pad, 2 * WIDE_OFFSETS[1])  # the screen live while you change the supply
            label = "PLL VDD %.3f V" % vdd
            answer = ask_planned(label)
            if answer is None:
                break
            if answer == "skip":
                continue
            n += 1
            locked = pll.wait_lock(timeout=LOCK_TIMEOUT)
            if not locked:  # after a supply step: load the config again
                pll_setup.load_config(pll, cfg)
                locked = pll.wait_lock(timeout=LOCK_TIMEOUT)
            cond = dict(base, time=datetime.now().isoformat(timespec="seconds"), locked=int(locked), condition=n,
                        condition_label=label)
            span, rbw, avg = CARRIER_STEP
            spectrum.set_sweep_points(WIDE_POINTS)
            f_carrier, carrier_dbm = peak_of(spectrum.averaged_trace(f_pad, span, averages=avg, rbw=rbw))
            logging.info("--- %s: PLL %s, carrier %.6f MHz, %.1f dBm", label, "locked" if locked else "NOT LOCKED",
                         f_carrier / 1e6, carrier_dbm)
            rows, traces = [], []
            for i, (span, rbw, avg) in enumerate(captures, 1):
                spectrum.set_sweep_points(min(MAX_SWEEP_POINTS, int(5 * span / rbw) + 1))
                t = spectrum.averaged_trace(f_carrier, span, averages=avg, rbw=rbw)
                rows.append(dict(cond, f_carrier=f_carrier, carrier_dbm=carrier_dbm, sideband=0, step="showcase",
                                 index=i, center=t["center"], span=t["span"], rbw=t["rbw"], averages=avg))
                traces.extend(dict(condition=n, condition_label=label, label=point["label"], sideband=0,
                                   step="showcase", index=i, center=t["center"], span=t["span"], rbw=t["rbw"],
                                   freq=f, level_dbm=l) for f, l in zip(t["freq"], t["level"]))
                logging.info("  span %g MHz, RBW %g Hz, %d averages", span / 1e6, t["rbw"], avg)
            append_rows(csv_path, PERTURB_COLUMNS, rows)  # saved per voltage
            append_rows(trace_path, PERTURB_TRACE_COLUMNS, traces)
    finally:
        if spectrum is not None:
            spectrum.set_sweep_mode(continuous=True)
            spectrum.close()
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
    logging.info("Spur showcase over the PLL supply written to %s", csv_path)
    return csv_path


def spur_supply_sweep(vdds=PLL_VDD_SWEEP, point=PERTURB_POINT, sample=None, chip=None):
    """spur_perturb over the PLL supply: you set each voltage of `vdds` [V] on the PLL supply and press Enter; per
    voltage the carrier, the wide captures and the tracked lines (the config is loaded again when the PLL lost lock).
    Into results/pll/pll_spur_vdd_<sample>_<stamp>.csv (condition label "PLL VDD x.xxx V"). Returns the CSV path."""
    return spur_perturb(point, sample=sample, chip=chip, planned=["PLL VDD %.3f V" % v for v in vdds],
                        prefix="pll_spur_vdd")


def start_log_file():
    """Also write the log to results/logs/pll_spur_zoom_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_spur_zoom_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset() as chip:  # core in reset: no pollution
        # PLL supply: fixed on the board, always on. Vctrl pad off (the pin header disturbs the loop).
        # Zoom into the lines at two settings (done 2026-10-21 16:08, pll_spur_zoom_S5_20261021_160853)
        # spur_zoom(sample="S5")

        # Interactive: per condition you set on the chip (label, or !reset / !run / !clkoff) the wide capture and
        # the tracked lines; the first condition is the reference (change nothing). ~1 min per condition
        # (done 2026-10-21 16:53, pll_spur_perturb_S5_20261021_165336). Now: more conditions (other PSU, ...) added to
        # that run, so they plot on top of it
        spur_perturb(sample="S5", chip=chip, csv_path=RESULTS_DIR / "pll_spur_perturb_S5_20261021_165336.csv")

        # Spectra for the plots at both SPUR_POINTS (done 2026-10-21 17:31, pll_spur_showcase_S5_20261021_173106)
        # spur_showcase(sample="S5")

        # PLL supply sweep: set each voltage of PLL_VDD_SWEEP by hand, Enter; ~1 min per voltage
        # (done 2026-10-21 17:32, pll_spur_vdd_S5_20261021_173215)
        # spur_supply_sweep(sample="S5", chip=chip)

        # The showcase spectra (SHOWCASE_CAPTURES, 50 averages) over the PLL supply: set each voltage of PLL_VDD_SWEEP
        # by hand, Enter; ~20 s per voltage
        # spur_supply_showcase(sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

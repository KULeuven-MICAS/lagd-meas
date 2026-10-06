# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Spectrum, phase noise and jitter of the locked PLL's output pad on the R&S FSV, shared by the PLL test scripts
# (sw/tests/pll_spectrum_kvco.py, sw/tests/pll_spectrum_div.py). measure_output() does everything after lock:
# carrier search and check, phase-noise markers (CALC:DELT2:FUNC:PNO:RES?, default detector), the full phase-noise
# curve from the exported traces (RMS detector, power averaging) with spur detection, and an averaged spectrum.
#
# Three points along the output chain (named so in every log line, column and plot):
#   VCO          f_vco, before any divider;
#   PLL output   f_vco / 2**set_div_freq, after the divider inside the PLL (pll_div), before the external divider;
#   pad          the PLL output / the external divider (ext_div = total_div / pll_div; 1 when pll_clk_o_en = 1):
#                what the analyzer measures.
# Phase noise and phase jitter scale with the division (+20 log10 N, x N) when referred back to the PLL output or the
# VCO; the time jitter stays the same (assuming the dividers add none). Spurs are only given on the pad.

import csv
import logging
import math
from pathlib import Path

import numpy as np

from sw.lib import vco_measure
from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.rohde_schwarz_fsv_spectrum import RohdeSchwarzFSVSpectrum
from sw.lib.pll_util import (LOG_AVG_CORR_DB, calculate_integrated_jitter, integrate_phase_noise,
                             phase_noise_from_traces, split_jitter)

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "pll"

FB_DIV = 128  # f_vco = FB_DIV * f_ref, fixed feedback ratio (pll_settings: CFG_REF8, 8 MHz -> 1024 MHz)
# Offset [Hz] -> analyzer span [Hz] for the phase-noise markers; the offsets are also the integration band of the
# jitter: 1 kHz - 50 MHz (above the 50 Hz mains harmonics; includes the reference spurs at n x f_ref and the board
# converter spurs). Above 50 MHz there is < 0.1 % of the phase variance (Kvco sweep 2026-10-05: 250 MHz pad,
# 100 MHz band).
OFFSET_SPAN_MAP = {
    1e3: 21e3,
    1e4: 21e3,
    1e5: 210e3,
    1e6: 2.1e6,
    1e7: 21e6,
    5e7: 105e6,
}
# Offsets are only measured up to f_out / OUT_OFFSET_RATIO: a digital divider passes the phase only at its output
# edges, so offsets above f_pad / 2 fold back and are not the VCO's noise (2.5: some margin below f_pad / 2).
OUT_OFFSET_RATIO = 2.5
# Highest pad frequency: above it the pad does not drive a full-swing carrier (divider sweep 2026-10-05: 125 MHz and
# below -5..+1 dBm, 250 MHz -16 dBm, 500 MHz / 1 GHz no carrier). pad_divider picks the divider from it.
PAD_F_MAX = 125e6
# RBW = span / RBW_SPAN_RATIO (1-2-3-5 steps), VBW = 3 RBW, 2 sweep points per RBW (driver set_bandwidths_for_span):
# 21 kHz -> 30 Hz, 210 kHz -> 300 Hz, 2.1 MHz -> 3 kHz, 21 MHz -> 30 kHz, 105 MHz -> 100 kHz, 5 MHz spectrum -> 5 kHz.
# The lowest offset of each span's band (1 kHz, 10 kHz, 100 kHz, 1 MHz, 10 MHz) is then >= ~33 RBW from the carrier.
RBW_SPAN_RATIO = 700
# Trace detector and averaging for the full curve and the spectrum: RMS detector + power (linear) averaging, so every
# trace point is the true noise power in the RBW (no log-average correction). The markers are read with the
# analyzer's default detector and averaging (with RMS + power they read 3-7 dB high at wide RBWs).
DETECTOR, AVERAGE_TYPE = "RMS", "POWer"
# Spur detection on the full curve (pll_util.find_spurs): points more than SPUR_THRESHOLD_DB above the median of L
# within +-SPUR_WINDOW_DECADES/2 around them, over at least SPUR_MIN_POINTS neighbouring points, are spurs; the jitter
# is split into noise and spur parts. Spurs are reported on the pad (where they are measured). The divider sweep of
# 2026-10-05 shows they coincide across dividers after +20 log10(N): phase modulation of the VCO, divided like its noise.
SPUR_THRESHOLD_DB, SPUR_WINDOW_DECADES, SPUR_MIN_POINTS = 10.0, 0.2, 2
# A carrier on the pad below this level is not measured (status "no_carrier"): no carrier at all (noise or a spur), or
# a pad that does not drive this frequency (full swing is about -5..+1 dBm).
MIN_CARRIER_DBM = -10.0

# Columns written by measure_output (the scripts add their own setting columns in front).
#   on the pad:              f_out, f_out_meas, carrier_dbm, L_out_*, phase_jitter_out_mrad,
#                            phase_jitter_trace_out_mrad, spurs;
#   referred to the PLL output: f_pll_out, L_pll_*, phase_jitter_pll_mrad;
#   referred to the VCO:     f_vco_meas, L_vco_*, phase_jitter_vco_mrad;
#   time_jitter_*:           the same at all three points.
OUTPUT_COLUMNS = (["f_out", "f_pll_out", "pll_div", "ext_div", "offset_max", "f_out_meas", "f_vco_meas",
                   "n_meas", "divider_ok",
                   "carrier_dbm", "n_averages", "time_jitter_ps", "phase_jitter_out_mrad", "phase_jitter_pll_mrad",
                   "phase_jitter_vco_mrad", "time_jitter_trace_ps",
                   "phase_jitter_trace_out_mrad", "time_jitter_noise_ps", "time_jitter_spur_ps", "n_spurs", "spurs",
                   "common_band", "time_jitter_common_ps", "time_jitter_trace_common_ps", "detector",
                   "average_type"]
                  + ["L_out_{:.0f}".format(f) for f in OFFSET_SPAN_MAP]
                  + ["L_pll_{:.0f}".format(f) for f in OFFSET_SPAN_MAP]
                  + ["L_vco_{:.0f}".format(f) for f in OFFSET_SPAN_MAP] + ["status"])
# Traces: one row per point. kind = "spectrum" (averaged wide trace) or "phase_noise" (one per span): freq [Hz],
# level [dBm]; "L_trace": the full phase-noise curve, freq = offset from the carrier [Hz], level = L(f) on the pad
# [dBc/Hz]; "L_noise": the same with the spurs replaced by the local noise floor; "spur": one row per spur,
# freq = offset of its peak [Hz], level = spur power on the pad [dBc, single sideband].
TRACE_FIELDS = ["kind", "center", "span", "rbw", "averages", "freq", "level_dbm"]


def open_spectrum():
    """The FSV from meas_setup.yaml (`spectrum_analyzer`); opening it resets the analyzer."""
    return RohdeSchwarzFSVSpectrum(
        inst.BaseSpectrumAnalyzerData.from_mapping(vco_measure.load_instr_cfg()["spectrum_analyzer"]))


def pad_divider(f_vco, pad_f_max=PAD_F_MAX):
    """Smallest 2**n (n = 0..7, set_div_freq) bringing f_vco / 2**n at or below pad_f_max."""
    return next((n for n in range(8) if f_vco / 2 ** n <= pad_f_max), 7)


def offsets_for(f_out, offset_span_map=None, out_offset_ratio=OUT_OFFSET_RATIO):
    """The part of `offset_span_map` that fits on a carrier at `f_out` [Hz] (offset <= f_out / out_offset_ratio)."""
    offset_span_map = offset_span_map or OFFSET_SPAN_MAP
    return {o: s for o, s in offset_span_map.items() if o * out_offset_ratio <= f_out}


def kvco_target_for(lut, f_vco, kvco):
    """|Kvco| to request from the lookup table `lut` (vco_lut.VcoLUT): `kvco` as is, or for "middle" the geometric
    middle of the |Kvco| range it offers at f_vco (inside the Vctrl window). Returns (target, kvco_min, kvco_max)."""
    kvco_min, kvco_max = lut.kvco_range(f_vco)  # raises when f_vco is unreachable
    target = math.sqrt(kvco_min * kvco_max) if kvco == "middle" else kvco
    logger.info("%.1f MHz: possible |Kvco| %.0f-%.0f MHz/V -> requesting %.0f MHz/V%s", f_vco / 1e6,
                kvco_min / 1e6, kvco_max / 1e6, target / 1e6, " (geometric middle)" if kvco == "middle" else "")
    return target, kvco_min, kvco_max


def measure_output(f_vco, total_div, offset_span_map, n_averages=10, span=5e6, spectrum_averages=20,
                   common_band=None, pll_div=None):
    """Measure the locked PLL's output pad at f_vco / total_div on the FSV. Returns (row, traces).

    `pll_div`: the divider inside the PLL (2**set_div_freq); the PLL output is f_vco / pll_div, the external divider
    total_div / pll_div. None: no external divider (pad = PLL output).

    1. Carrier search (center_on_fundamental); below MIN_CARRIER_DBM: status "no_carrier", nothing else measured.
    2. Phase-noise markers (PNO:RES?) at the offsets of `offset_span_map`, default detector, `n_averages` sweeps
       per span; RMS jitter over the offsets (pll_util.calculate_integrated_jitter).
    3. The full curve: the same spans with the RMS detector + power averaging, traces exported, L(f) built from
       them and integrated with the spurs split off (pll_util.split_jitter).
    4. An averaged spectrum over `span` (`spectrum_averages` sweeps).
    `common_band` (lo, hi) [Hz]: also integrate the markers and the full curve over only that band, to compare
    settings whose bands differ (e.g. dividers: the band is limited by the pad frequency).
    row: the OUTPUT_COLUMNS values; n_meas = f_vco / measured carrier checks the divider (a digital divider is exact,
    so it only catches a wrong N: divider_ok when within 0.1 % of total_div; the ppm-level rest is the reference
    generator's clock against the analyzer's). traces: list of dicts with the TRACE_FIELDS (freq/level as lists).
    The analyzer is closed at the end, also on an error.
    """
    pll_div = pll_div or total_div
    ext_div = total_div / pll_div
    f_out = f_vco / total_div
    row = dict(f_out=f_out, f_pll_out=f_vco / pll_div, pll_div=pll_div, ext_div=ext_div,
               offset_max=max(offset_span_map),
               n_averages=n_averages, detector=DETECTOR,
               average_type=AVERAGE_TYPE, common_band="{:g}-{:g}".format(*common_band) if common_band else "",
               status="error")
    traces = []
    n_db = 20 * math.log10(total_div)  # pad -> VCO
    ext_db = 20 * math.log10(ext_div)  # pad -> PLL output
    spectrum = open_spectrum()  # reset: default detector and averaging
    try:
        spectrum.center_on_fundamental(center_freq=f_out, search_span=2.1e3)
        f_meas = float(spectrum.query("FREQ:CENT?").strip())
        carrier_dbm = spectrum.get_marker_y_value(marker=1)  # peak found by center_on_fundamental
        row.update(f_out_meas=f_meas, f_vco_meas=f_meas * total_div, carrier_dbm=carrier_dbm,
                   n_meas=f_vco / f_meas, divider_ok=int(abs(f_vco / f_meas / total_div - 1) < 1e-3))
        if carrier_dbm < MIN_CARRIER_DBM:
            logger.warning("No carrier on the pad near %.4f MHz (peak %.1f dBm < %.0f dBm): not measured",
                           f_out / 1e6, carrier_dbm, MIN_CARRIER_DBM)
            row["status"] = "no_carrier"
            return row, traces

        # 1. Markers with the default detector and averaging
        profile = spectrum.measure_phase_noise_profile(averages=n_averages, offset_span_map=offset_span_map,
                                                       rbw_span_ratio=RBW_SPAN_RATIO)
        # 2. Full curve: RMS detector + power averaging, traces exported
        pn_traces = []
        spectrum.measure_phase_noise_profile(averages=n_averages, offset_span_map=offset_span_map, traces=pn_traces,
                                             rbw_span_ratio=RBW_SPAN_RATIO, detector=DETECTOR,
                                             average_type=AVERAGE_TYPE)
        traces += [dict(t, kind="phase_noise", averages=n_averages) for t in pn_traces]
        # 3. Averaged wide spectrum around the carrier
        t = spectrum.averaged_trace(f_meas, span, averages=spectrum_averages, rbw_span_ratio=RBW_SPAN_RATIO,
                                    detector=DETECTOR, average_type=AVERAGE_TYPE)
        traces.append(dict(t, kind="spectrum"))
    finally:
        spectrum.set_sweep_mode(continuous=True)  # screen live again
        spectrum.close()

    t_jit, phi_out = calculate_integrated_jitter(f_meas, list(profile), list(profile.values()))
    row.update(time_jitter_ps=t_jit * 1e12, phase_jitter_out_mrad=phi_out * 1e3,
               phase_jitter_pll_mrad=phi_out * ext_div * 1e3, phase_jitter_vco_mrad=phi_out * total_div * 1e3,
               status="ok")
    for f, l in profile.items():
        row["L_out_{:.0f}".format(f)] = l
        row["L_pll_{:.0f}".format(f)] = l + ext_db
        row["L_vco_{:.0f}".format(f)] = l + n_db
    logger.info("Carrier on the pad %.6f MHz, %.1f dBm (/%g outside the PLL) <- PLL output %.4f MHz (/%g inside) <- "
                "VCO %.4f MHz (divider check: f_vco / carrier = %.3f, set %d)", f_meas / 1e6, carrier_dbm, ext_div,
                f_meas * ext_div / 1e6, pll_div, f_meas * total_div / 1e6, row["n_meas"], total_div)
    for where, add_db in (("on the pad", 0.0), ("at the PLL output", ext_db), ("at the VCO", n_db)):
        if where == "at the PLL output" and ext_div == 1:
            continue  # same as the pad
        logger.info("Phase noise %s (markers): %s", where, ", ".join(
            "{:g} Hz: {:.1f} dBc/Hz".format(f, l + add_db) for f, l in profile.items()))
    logger.info("RMS jitter %g-%g Hz (markers): %.3f ps; phase %.3f mrad on the pad, %.3f mrad at the PLL output, "
                "%.3f mrad at the VCO", min(profile), max(profile), t_jit * 1e12, phi_out * 1e3,
                phi_out * ext_div * 1e3, phi_out * total_div * 1e3)

    o_tr, l_tr = phase_noise_from_traces(pn_traces, list(profile),
                                         log_avg_corr_db=LOG_AVG_CORR_DB if AVERAGE_TYPE is None else 0.0)
    if len(o_tr) > 1:
        jit = split_jitter(f_meas, o_tr, l_tr, threshold_db=SPUR_THRESHOLD_DB, window_decades=SPUR_WINDOW_DECADES,
                           min_points=SPUR_MIN_POINTS)
        spurs = jit["spurs"]
        row.update(time_jitter_trace_ps=jit["total"] * 1e12, phase_jitter_trace_out_mrad=jit["total_rad"] * 1e3,
                   time_jitter_noise_ps=jit["noise"] * 1e12, time_jitter_spur_ps=jit["spur"] * 1e12,
                   n_spurs=len(spurs), spurs="; ".join("{:.0f} Hz: {:.1f} dBc".format(s["offset"], s["power"])
                                                      for s in spurs))
        traces += [dict(kind="L_trace", center=f_meas, span=None, rbw=None, averages=n_averages,
                        freq=list(o_tr), level=list(l_tr)),
                   dict(kind="L_noise", center=f_meas, span=None, rbw=None, averages=n_averages,
                        freq=list(o_tr), level=list(jit["L_noise"])),
                   dict(kind="spur", center=f_meas, span=None, rbw=None, averages=n_averages,
                        freq=[s["offset"] for s in spurs], level=[s["power"] for s in spurs])]
        logger.info("RMS jitter %g-%g Hz (full curve on the pad, %d points): %.3f ps total = %.3f ps noise + %.3f ps "
                    "from %d spurs (%.3f mrad on the pad)", o_tr[0], o_tr[-1], len(o_tr), jit["total"] * 1e12,
                    jit["noise"] * 1e12, jit["spur"] * 1e12, len(spurs), jit["total_rad"] * 1e3)
        for s in spurs:
            logger.info("  spur at %.0f Hz offset (%.0f-%.0f Hz): %.1f dBc on the pad, peak %.1f dB above the noise "
                        "floor", s["offset"], s["f_lo"], s["f_hi"], s["power"], s["above_floor"])
        logger.info("Full curve vs marker L(f) on the pad: %s", ", ".join(
            "{:g} Hz: {:.1f} / {:.1f} dBc/Hz".format(f, float(np.interp(f, o_tr, l_tr)), l)
            for f, l in profile.items()))

    if common_band:
        lo, hi = common_band
        marks = {f: l for f, l in profile.items() if lo <= f <= hi}
        if len(marks) > 1:
            row["time_jitter_common_ps"] = calculate_integrated_jitter(f_meas, list(marks),
                                                                      list(marks.values()))[0] * 1e12
        keep = (o_tr >= lo) & (o_tr <= hi) if len(o_tr) else np.array([], dtype=bool)
        if keep.sum() > 1:
            row["time_jitter_trace_common_ps"] = integrate_phase_noise(f_meas, o_tr[keep], l_tr[keep])[0] * 1e12
        logger.info("RMS jitter over the common band %g-%g Hz: %s ps (markers), %s ps (full curve)", lo, hi,
                    "{:.3f}".format(row["time_jitter_common_ps"]) if "time_jitter_common_ps" in row else "-",
                    "{:.3f}".format(row["time_jitter_trace_common_ps"]) if "time_jitter_trace_common_ps" in row
                    else "-")
    return row, traces


def trace_rows(traces, **key):
    """CSV rows (one per trace point) for `traces` from measure_output, each with the `key` columns in front."""
    return [dict(key, kind=t["kind"], center=t["center"], span=t["span"], rbw=t["rbw"], averages=t.get("averages"),
                 freq=f, level_dbm=l) for t in traces for f, l in zip(t["freq"], t["level"])]


def trace_csv_path(csv_path):
    return Path(csv_path).with_name(Path(csv_path).stem + "_traces.csv")


def append_rows(csv_path, columns, rows):
    """Append rows to a CSV (header written when the file is new)."""
    new = not Path(csv_path).exists() or Path(csv_path).stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerows(rows)

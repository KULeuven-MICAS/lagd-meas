# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Spectrum, phase noise and jitter of the locked PLL's output pad on the R&S FSV, shared by the PLL test scripts
# (sw/tests/pll_spectrum_kvco.py, sw/tests/pll_spectrum_div.py). measure_output() does everything after lock:
# carrier search and check, the full phase-noise curve from averaged traces (RMS detector, power averaging) with spur
# detection, and an averaged spectrum.
# measure_phase_noise_mode() measures the same pad in the analyzer's Phase Noise application (FSW K40) for a
# comparison, log_method_comparison() logs the methods side by side.
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
import time
from pathlib import Path

import numpy as np

from sw.lib import vco_measure
from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.rohde_schwarz_fsv_spectrum import PNO_MAX_SPOT_MARKERS, RohdeSchwarzFSVSpectrum
from sw.lib.pll_util import integrate_phase_noise, phase_noise_from_traces, split_jitter

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "pll"

FB_DIV = 128  # f_vco = FB_DIV * f_ref, fixed feedback ratio (pll_settings: CFG_REF8, 8 MHz -> 1024 MHz)
# Offset [Hz] -> analyzer span [Hz] of the trace covering the curve up to that offset; the offsets are also the
# integration band of the jitter: 1 kHz - 20 MHz (above the 50 Hz mains harmonics; includes the reference spurs at
# n x f_ref and the board converter spurs). 20 MHz is the most a pad of PAD_F_MAX / 2 = 50 MHz shows
# (OUT_OFFSET_RATIO); above 50 MHz there is < 0.1 % of the phase variance (Kvco sweep 2026-10-05: 250 MHz pad).
OFFSET_SPAN_MAP = {
    1e3: 21e3,
    1e4: 21e3,
    1e5: 210e3,
    1e6: 2.1e6,
    1e7: 21e6,
    2e7: 42e6,
}
# Offsets are only measured up to f_out / OUT_OFFSET_RATIO: a digital divider passes the phase only at its output
# edges, so offsets above f_pad / 2 fold back and are not the VCO's noise (2.5: some margin below f_pad / 2).
OUT_OFFSET_RATIO = 2.5
# Usable pad frequencies (2026-10-20): the pad's bandwidth ends at PAD_F_MAX, and the DC blocker at the analyzer
# input cuts the carrier below PAD_F_MIN. pad_divider picks the internal divider from PAD_F_MAX, which puts the pad
# at PAD_F_MAX / 2 - PAD_F_MAX; the divider sweep skips settings outside the band.
PAD_F_MIN, PAD_F_MAX = 20e6, 100e6
# RBW = span / RBW_SPAN_RATIO (1-2-3-5 steps), VBW = 3 RBW, 5 sweep points per RBW (driver set_bandwidths_for_span):
# 21 kHz -> 30 Hz, 210 kHz -> 300 Hz, 2.1 MHz -> 3 kHz, 21 MHz -> 30 kHz, 42 MHz -> 50 kHz, 5 MHz spectrum -> 5 kHz.
# The lowest offset of each span's band (1 kHz, 10 kHz, 100 kHz, 1 MHz, 10 MHz) is then >= ~33 RBW from the carrier.
RBW_SPAN_RATIO = 700
# Detector, averaging and video filter for the full curve and the spectrum: RMS detector
# + power (linear) averaging + linear video filter, so every trace point is the true noise power in the RBW (no
# log-average correction). The values the analyzer reports back are recorded per row (detector, average_type,
# video_filter).
DETECTOR, AVERAGE_TYPE, VIDEO_FILTER = "RMS", "POWer", "LINear"
# Spur detection on the full curve (pll_util.find_spurs): points more than SPUR_THRESHOLD_DB above the median of L
# within +-SPUR_WINDOW_DECADES/2 around them, over at least SPUR_MIN_POINTS neighbouring points, are spurs; the jitter
# is split into noise and spur parts. Spurs are reported on the pad (where they are measured). The divider sweep of
# 2026-10-05 shows they coincide across dividers after +20 log10(N): phase modulation of the VCO, divided like its noise.
SPUR_THRESHOLD_DB, SPUR_WINDOW_DECADES, SPUR_MIN_POINTS = 10.0, 0.2, 2
# A carrier on the pad below this level is not measured (status "no_carrier"): no carrier at all (noise or a spur), or
# a pad that does not drive this frequency (full swing is about -5..+1 dBm).
MIN_CARRIER_DBM = -10.0

# Columns written by measure_output (the scripts add their own setting columns in front).
#   on the pad:              f_out, f_out_meas, carrier_dbm, phase_jitter_trace_out_mrad, spurs;
#   referred to the PLL output: f_pll_out, phase_jitter_trace_pll_mrad;
#   referred to the VCO:     f_vco_meas, phase_jitter_trace_vco_mrad;
#   time_jitter_*:           the same at all three points.
#   analyzer_name:           the analyzer measured on (meas_setup.yaml name).
# L(f) itself is in the traces ("L_trace", on the pad; + 20 log10 N for the PLL output / VCO).
OUTPUT_COLUMNS = ["analyzer_name", "f_out", "f_pll_out", "pll_div", "ext_div", "offset_max", "f_out_meas",
                  "f_vco_meas", "n_meas", "divider_ok", "carrier_dbm", "n_averages", "time_jitter_trace_ps",
                  "phase_jitter_trace_out_mrad", "phase_jitter_trace_pll_mrad", "phase_jitter_trace_vco_mrad",
                  "time_jitter_noise_ps", "time_jitter_spur_ps", "n_spurs", "spurs", "common_band",
                  "time_jitter_trace_common_ps", "detector", "average_type", "video_filter", "rf_overload",
                  "if_overload", "status"]
# Traces: one row per point. kind = "spectrum" (averaged wide trace) or "phase_noise" (one per span): freq [Hz],
# level [dBm]; "L_trace": the full phase-noise curve, freq = offset from the carrier [Hz], level = L(f) on the pad
# [dBc/Hz]; "L_noise": the same with the spurs replaced by the local noise floor; "spur": one row per spur,
# freq = offset of its peak [Hz], level = spur power on the pad [dBc, single sideband].
TRACE_FIELDS = ["kind", "center", "span", "rbw", "vbw", "averages", "freq", "level_dbm"]

# Phase-noise mode (FSW K40, measure_phase_noise_mode), for a comparison with the full-curve method above:
# RBW as % of each half decade's start offset, measurement preset (FAST / NORMal / AVERage: averaging per half
# decade), trace averages over whole sweeps, spur removal off by default (the trace keeps its spurs, as our full curve
# does; the spur list and the discrete / random jitter split come either way), timeout of one averaged sweep.
PNM_RBW_PERCENT = 10.0
PNM_PRESET = "NORMal"
PNM_AVERAGES = 10
PNM_SWEEP_TIMEOUT_MS = 900000
# Columns written by measure_phase_noise_mode (pnm = phase-noise mode), all on the pad:
#   L_pnm_*:                  spot noise at the OFFSET_SPAN_MAP offsets (at most 5 spot markers: the rest empty);
#   time_jitter_pnm_ps:       the analyzer's residual RMS jitter over pnm_band (FETC:PNO:RMS?);
#   time_jitter_pnm_ipn_ps:   from its integrated phase noise (FETC:PNO:IPN?), phase_jitter_pnm_out_mrad likewise;
#   time_jitter_pnm_trace_ps: our integration (pll_util.integrate_phase_noise) of its trace over pnm_band;
#   time_jitter_pnm_random_ps / _discrete_ps: its split into noise and spurs; pnm_spurs: its spur list;
#   time_jitter_trace_pnm_band_ps: our full curve (measure_output) integrated over the same pnm_band.
PNM_COLUMNS = (["pnm_f_out_meas", "pnm_carrier_dbm", "pnm_band", "pnm_offset_stop", "pnm_rbw_percent", "pnm_preset",
                "pnm_averages", "pnm_spur_removal", "pnm_spur_threshold_db", "pnm_sweep_s", "time_jitter_pnm_ps",
                "time_jitter_pnm_ipn_ps", "phase_jitter_pnm_out_mrad", "time_jitter_pnm_trace_ps",
                "time_jitter_trace_pnm_band_ps",
                "time_jitter_pnm_random_ps", "time_jitter_pnm_discrete_ps", "pnm_residual_pm", "pnm_residual_fm_hz",
                "pnm_n_spurs", "pnm_spurs"]
               + ["L_pnm_{:.0f}".format(f) for f in OFFSET_SPAN_MAP] + ["pnm_status"])


def open_spectrum(analyzer="spectrum_analyzer"):
    """The analyzer `analyzer` from meas_setup.yaml: "spectrum_analyzer" (the one of every measurement, set there) or
    "spectrum_analyzer_fsv" (the FSV, for a comparison); opening it resets the analyzer."""
    return RohdeSchwarzFSVSpectrum(
        inst.BaseSpectrumAnalyzerData.from_mapping(vco_measure.load_instr_cfg()[analyzer]))


def pad_divider(f_vco, pad_f_max=PAD_F_MAX):
    """Smallest 2**n (n = 0..7, set_div_freq) bringing f_vco / 2**n at or below pad_f_max (so above pad_f_max / 2:
    inside PAD_F_MIN - PAD_F_MAX for f_vco from 2 PAD_F_MIN up)."""
    return next((n for n in range(8) if f_vco / 2 ** n <= pad_f_max), 7)


def offsets_for(f_out, offset_span_map=None, out_offset_ratio=OUT_OFFSET_RATIO):
    """The part of `offset_span_map` that fits on a carrier at `f_out` [Hz] (offset <= f_out / out_offset_ratio)."""
    offset_span_map = offset_span_map or OFFSET_SPAN_MAP
    return {o: s for o, s in offset_span_map.items() if o * out_offset_ratio <= f_out}


def kvco_target_for(lut, f_vco, kvco):
    """|Kvco| to request from the lookup table `lut` (vco_lut.VcoLUT) at f_vco, from the range it offers there (inside
    the Vctrl window): `kvco` [Hz/V] as is; "middle": the geometric middle of the range; "max" / "min": its highest /
    lowest |Kvco|; None: no preference (update_config then picks the Vctrl closest to the window centre).
    Returns (target, kvco_min, kvco_max); raises ValueError when no setting reaches f_vco."""
    kvco_min, kvco_max = lut.kvco_range(f_vco)
    if kvco == "middle":
        target = math.sqrt(kvco_min * kvco_max)
    elif kvco == "max":
        target = kvco_max
    elif kvco == "min":
        target = kvco_min
    else:
        target = kvco
    logger.info("%.1f MHz: possible |Kvco| %.0f-%.0f MHz/V -> requesting %s%s", f_vco / 1e6, kvco_min / 1e6,
                kvco_max / 1e6, "any (central Vctrl)" if target is None else "%.0f MHz/V" % (target / 1e6),
                " (%s)" % kvco if isinstance(kvco, str) else "")
    return target, kvco_min, kvco_max


def measure_output(f_vco, total_div, offset_span_map, n_averages=10, span=5e6, spectrum_averages=20,
                   common_band=None, pll_div=None, analyzer="spectrum_analyzer"):
    """Measure the locked PLL's output pad at f_vco / total_div on the analyzer `analyzer` (meas_setup.yaml key, see
    open_spectrum; default: the analyzer set in meas_setup.yaml). Returns (row, traces).

    `pll_div`: the divider inside the PLL (2**set_div_freq); the PLL output is f_vco / pll_div, the external divider
    total_div / pll_div. None: no external divider (pad = PLL output).

    1. Carrier search (center_on_fundamental); below MIN_CARRIER_DBM: status "no_carrier", nothing else measured.
    2. One averaged trace per span of `offset_span_map`, RMS detector + power averaging, `n_averages` sweeps per
       span: the full curve L(f) from these traces, integrated with the spurs split off (pll_util.split_jitter).
    3. An averaged spectrum over `span` (`spectrum_averages` sweeps), same detector and averaging.
    detector / average_type in the row: as the analyzer reports them after the sweeps.
    `common_band` (lo, hi) [Hz]: also integrate the full curve over only that band, to compare settings whose bands
    differ (e.g. dividers: the band is limited by the pad frequency).
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
               n_averages=n_averages, detector=DETECTOR, average_type=AVERAGE_TYPE, video_filter=VIDEO_FILTER,
               common_band="{:g}-{:g}".format(*common_band) if common_band else "",
               status="error")
    traces = []
    spectrum = open_spectrum(analyzer)  # reset: default detector and averaging
    row["analyzer_name"] = spectrum.info.name  # which analyzer (meas_setup.yaml)
    try:
        carrier_dbm = spectrum.center_on_fundamental(center_freq=f_out, search_span=2.1e3)  # peak of its search sweep
        f_meas = float(spectrum.query("FREQ:CENT?").strip())
        row.update(f_out_meas=f_meas, f_vco_meas=f_meas * total_div, carrier_dbm=carrier_dbm,
                   n_meas=f_vco / f_meas, divider_ok=int(abs(f_vco / f_meas / total_div - 1) < 1e-3))
        if carrier_dbm < MIN_CARRIER_DBM:
            logger.warning("No carrier on the pad near %.4f MHz (peak %.1f dBm < %.0f dBm): not measured",
                           f_out / 1e6, carrier_dbm, MIN_CARRIER_DBM)
            row["status"] = "no_carrier"
            return row, traces

        # Traces for the full curve: RMS detector + power averaging + linear video filter
        pn_traces = spectrum.phase_noise_traces(f_meas, list(offset_span_map.values()), averages=n_averages,
                                                rbw_span_ratio=RBW_SPAN_RATIO, detector=DETECTOR,
                                                average_type=AVERAGE_TYPE, video_filter=VIDEO_FILTER)
        row.update(detector=spectrum.get_detector(), average_type=spectrum.get_average_type(),
                   video_filter=spectrum.get_video_filter_type())
        traces += [dict(t, kind="phase_noise") for t in pn_traces]
        # Averaged wide spectrum around the carrier
        t = spectrum.averaged_trace(f_meas, span, averages=spectrum_averages, rbw_span_ratio=RBW_SPAN_RATIO,
                                    detector=DETECTOR, average_type=AVERAGE_TYPE, video_filter=VIDEO_FILTER)
        traces.append(dict(t, kind="spectrum"))
        overload = spectrum.read_overload()  # any overload during the sweeps above (the carrier search included)
        row.update(rf_overload=int(overload["rf_overload"]), if_overload=int(overload["if_overload"]))
    finally:
        spectrum.set_sweep_mode(continuous=True)  # screen live again
        spectrum.close()

    row["status"] = "overload" if row["rf_overload"] or row["if_overload"] else "ok"
    if row["status"] == "overload":
        logger.warning("Analyzer OVERLOAD during the measurement (RF %d, IF %d): the levels are not reliable, status "
                       "\"overload\"", row["rf_overload"], row["if_overload"])
    logger.info("Carrier on the pad %.6f MHz, %.1f dBm (/%g outside the PLL) <- PLL output %.4f MHz (/%g inside) <- "
                "VCO %.4f MHz (divider check: f_vco / carrier = %.3f, set %d)", f_meas / 1e6, carrier_dbm, ext_div,
                f_meas * ext_div / 1e6, pll_div, f_meas * total_div / 1e6, row["n_meas"], total_div)

    offsets = sorted(offset_span_map)
    o_tr, l_tr = phase_noise_from_traces(pn_traces, offsets)  # power-averaged: no log-average correction
    if len(o_tr) > 1:
        jit = split_jitter(f_meas, o_tr, l_tr, threshold_db=SPUR_THRESHOLD_DB, window_decades=SPUR_WINDOW_DECADES,
                           min_points=SPUR_MIN_POINTS)
        spurs = jit["spurs"]
        row.update(time_jitter_trace_ps=jit["total"] * 1e12, phase_jitter_trace_out_mrad=jit["total_rad"] * 1e3,
                   phase_jitter_trace_pll_mrad=jit["total_rad"] * ext_div * 1e3,
                   phase_jitter_trace_vco_mrad=jit["total_rad"] * total_div * 1e3,
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
                    "from %d spurs; phase %.3f mrad on the pad, %.3f mrad at the PLL output, %.3f mrad at the VCO",
                    o_tr[0], o_tr[-1], len(o_tr), jit["total"] * 1e12, jit["noise"] * 1e12, jit["spur"] * 1e12,
                    len(spurs), jit["total_rad"] * 1e3, jit["total_rad"] * ext_div * 1e3,
                    jit["total_rad"] * total_div * 1e3)
        for s in spurs:
            logger.info("  spur at %.0f Hz offset (%.0f-%.0f Hz): %.1f dBc on the pad, peak %.1f dB above the noise "
                        "floor", s["offset"], s["f_lo"], s["f_hi"], s["power"], s["above_floor"])

    if common_band:
        lo, hi = common_band
        keep = (o_tr >= lo) & (o_tr <= hi) if len(o_tr) else np.array([], dtype=bool)
        if keep.sum() > 1:
            row["time_jitter_trace_common_ps"] = integrate_phase_noise(f_meas, o_tr[keep], l_tr[keep])[0] * 1e12
        logger.info("RMS jitter over the common band %g-%g Hz (full curve): %s ps", lo, hi,
                    "{:.3f}".format(row["time_jitter_trace_common_ps"]) if "time_jitter_trace_common_ps" in row
                    else "-")
    return row, traces


def measure_phase_noise_mode(f_vco, total_div, offsets, carrier_dbm=None, averages=PNM_AVERAGES,
                             preset=PNM_PRESET, rbw_percent=PNM_RBW_PERCENT, spur_removal=False,
                             spur_threshold_db=SPUR_THRESHOLD_DB, our_traces=None, analyzer="spectrum_analyzer",
                             freq_tolerance_hz=10e3, level_tolerance_db=10.0):
    """Measure the locked PLL's pad (f_vco / total_div) in the analyzer's Phase Noise application (FSW option K40),
    for a comparison with measure_output on the same lock. Returns (row, traces).

    The analyzer verifies and tracks the carrier (expected level `carrier_dbm`, e.g. measure_output's; None: 0 dBm),
    sweeps the offsets from min(offsets) up to f_out / OUT_OFFSET_RATIO (it rounds the stop to a half decade) in one
    single averaged sweep (`averages` trace averages, `preset`, RBW `rbw_percent` % of the offset), then reads
    (RohdeSchwarzFSVSpectrum.read_phase_noise) over the band min(offsets)..max(offsets), the band of measure_output,
    cut at the analyzer's stop offset (pnm_band; `our_traces`, measure_output's traces: their full curve is integrated
    over the same band too, time_jitter_trace_pnm_band_ps):
    spot noise at the offsets, its residual jitter, integrated phase noise, spur list with the discrete / random jitter
    split, and the L(f) trace, which is integrated here too (pll_util.integrate_phase_noise).
    row: the PNM_COLUMNS values; traces: "L_pnmode" (its L(f) curve, freq = offset) and "pnm_spur" (its spur list,
    freq = offset, level = dBc), with the TRACE_FIELDS. The analyzer is left in single sweep and closed at the end,
    also on an error.
    `freq_tolerance_hz`, `level_tolerance_db`: how far the carrier may be from f_vco / total_div and from
    `carrier_dbm` (a locked PLL: 10 kHz, 10 dB; a free-running VCO wanders, so more).
    """
    offsets = sorted(offsets)
    f_out = f_vco / total_div
    spot = offsets[:PNO_MAX_SPOT_MARKERS]
    row = dict(pnm_rbw_percent=rbw_percent, pnm_preset=preset,
               pnm_averages=averages, pnm_spur_removal=int(spur_removal),
               pnm_spur_threshold_db=spur_threshold_db if spur_removal else None, pnm_status="error")
    spectrum = open_spectrum(analyzer)  # reset: also leaves a previous phase-noise channel
    try:
        spectrum.start_phase_noise_mode(f_out, offsets[0], f_out / OUT_OFFSET_RATIO,
                                        carrier_level_dbm=0.0 if carrier_dbm is None else round(carrier_dbm),
                                        freq_tolerance_hz=freq_tolerance_hz,
                                        level_tolerance_db=level_tolerance_db,
                                        tracking=True, rbw_percent=rbw_percent, preset=preset, averages=averages,
                                        spur_removal=spur_removal, spur_threshold_db=spur_threshold_db,
                                        continuous=False)
        spectrum.set_phase_noise_spot_offsets(spot)
        # The analyzer rounds the stop offset to a half decade (125 MHz pad: 50 MHz -> 30 MHz): integrate only up to
        # where it measured
        row["pnm_offset_stop"] = float(spectrum.query("FREQ:STOP?").strip())
        band = (offsets[0], min(offsets[-1], row["pnm_offset_stop"]))
        row["pnm_band"] = "{:g}-{:g}".format(*band)
        t0 = time.time()
        spectrum.trigger_single_sweep(wait=True, timeout_ms=PNM_SWEEP_TIMEOUT_MS)
        row["pnm_sweep_s"] = time.time() - t0
        res = spectrum.read_phase_noise(spot, band=band)
    finally:
        # Single sweep: in continuous sweep the phase-noise application keeps searching for the carrier once the
        # reference is switched off at the end, switching its input relays all the time
        spectrum.set_sweep_mode(continuous=False)
        spectrum.close()

    f_meas = res["f_carrier"]
    o, l = np.asarray(res["offset"], dtype=float), np.asarray(res["level"], dtype=float)
    keep = (o >= band[0]) & (o <= band[1])
    row.update(pnm_f_out_meas=f_meas, pnm_carrier_dbm=res["carrier_dbm"], time_jitter_pnm_ps=res["jitter_s"] * 1e12,
               time_jitter_pnm_ipn_ps=res["rms_phase_rad"] / (2 * math.pi * f_meas) * 1e12,
               phase_jitter_pnm_out_mrad=res["rms_phase_rad"] * 1e3,
               time_jitter_pnm_random_ps=res["jitter_random_s"] * 1e12,
               time_jitter_pnm_discrete_ps=res["jitter_discrete_s"] * 1e12, pnm_residual_pm=res["residual_pm"],
               pnm_residual_fm_hz=res["residual_fm_hz"], pnm_n_spurs=len(res["spurs"]),
               pnm_spurs="; ".join("{:.0f} Hz: {:.1f} dBc".format(f, p) for f, p in res["spurs"]), pnm_status="ok")
    if keep.sum() > 1:
        row["time_jitter_pnm_trace_ps"] = integrate_phase_noise(f_meas, o[keep], l[keep])[0] * 1e12
    curve = next((t for t in our_traces or [] if t["kind"] == "L_trace"), None)
    if curve is not None:
        o_c, l_c = np.asarray(curve["freq"], dtype=float), np.asarray(curve["level"], dtype=float)
        keep_c = (o_c >= band[0]) & (o_c <= band[1])
        if keep_c.sum() > 1:
            row["time_jitter_trace_pnm_band_ps"] = integrate_phase_noise(curve["center"], o_c[keep_c],
                                                                         l_c[keep_c])[0] * 1e12
    for f, v in res["spot"].items():
        row["L_pnm_{:.0f}".format(f)] = v
    traces = [dict(kind="L_pnmode", center=f_meas, span=None, rbw=None, averages=averages, freq=list(o), level=list(l)),
              dict(kind="pnm_spur", center=f_meas, span=None, rbw=None, averages=averages,
                   freq=[f for f, _ in res["spurs"]], level=[p for _, p in res["spurs"]])]
    logger.info("Phase-noise mode: carrier %.6f MHz, %.1f dBm; one sweep of %.0f s (%s, %d averages, RBW %g %%, spur "
                "removal %s); RMS jitter %g-%g Hz %.3f ps = %.3f ps random + %.3f ps discrete (%d spurs)",
                f_meas / 1e6, res["carrier_dbm"], row["pnm_sweep_s"], preset, averages, rbw_percent,
                "on" if spur_removal else "off", band[0], band[1], row["time_jitter_pnm_ps"],
                row["time_jitter_pnm_random_ps"], row["time_jitter_pnm_discrete_ps"], row["pnm_n_spurs"])
    return row, traces


def log_method_comparison(row, traces):
    """Log the full curve (measure_output) and the phase-noise mode (measure_phase_noise_mode) side by side: L(f) per
    offset on the pad and the RMS jitter of each, from a row with the OUTPUT_COLUMNS and PNM_COLUMNS and the traces of
    both (the "L_trace" curve)."""
    curve = next((t for t in traces if t["kind"] == "L_trace"), None)
    logger.info("Phase noise on the pad [dBc/Hz]:  offset  full curve  phase-noise mode")
    for f in OFFSET_SPAN_MAP:
        pnm = row.get("L_pnm_{:.0f}".format(f))
        on_curve = curve is not None and len(curve["freq"]) and curve["freq"][0] <= f <= curve["freq"][-1]
        full = float(np.interp(f, curve["freq"], curve["level"])) if on_curve else None
        if full is None and pnm is None:
            continue
        logger.info("  %10g Hz  %10s  %16s", f, *("-" if v is None else "{:.1f}".format(v) for v in (full, pnm)))

    def ps(key):
        return "-" if row.get(key) is None else "{:.3f} ps".format(row[key])

    logger.info("RMS jitter on the pad: full curve %s (noise %s + spurs %s); phase-noise mode %s (random "
                "%s + discrete %s; from its IPN %s, its trace integrated by us %s)",
                ps("time_jitter_trace_ps"), ps("time_jitter_noise_ps"), ps("time_jitter_spur_ps"),
                ps("time_jitter_pnm_ps"), ps("time_jitter_pnm_random_ps"), ps("time_jitter_pnm_discrete_ps"),
                ps("time_jitter_pnm_ipn_ps"), ps("time_jitter_pnm_trace_ps"))
    logger.info("Over the same band %s Hz: full curve %s, phase-noise mode %s", row.get("pnm_band", "-"),
                ps("time_jitter_trace_pnm_band_ps"), ps("time_jitter_pnm_ps"))


def trace_rows(traces, **key):
    """CSV rows (one per trace point) for `traces` from measure_output, each with the `key` columns in front."""
    return [dict(key, kind=t["kind"], center=t["center"], span=t["span"], rbw=t["rbw"], vbw=t.get("vbw"),
                 averages=t.get("averages"), freq=f, level_dbm=l)
            for t in traces for f, l in zip(t["freq"], t["level"])]


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

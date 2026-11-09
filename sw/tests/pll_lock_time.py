# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Lock time of the PLL: the settling of the VCO frequency after a step of the reference.
#
# The reference (33600A ch1) hops between f_ref and f_ref x (1 + step_rel) with FSK from its internal source at
# fsk_rate (each frequency 1 / (2 fsk_rate) long); the FG Sync output marks the hops (high on the hop frequency). The
# PLL output, divided down to ~SCOPE_PAD_F on the pad (external divider path, as the open-loop VCO bench of
# lib/vco_measure.py: a clean square on the RTB2004), is captured on the RTB2004 channel PAD_CH,
# triggered on the Sync output on channel SYNC_CH: rising Sync edge = the step to the hop frequency (up for
# step_rel > 0), falling = the step back. Per capture (window `window` [s], `pre` of it before the step):
#   - the rising crossings of the pad through its mid level (linear interpolation between samples);
#   - the cycle count against time at the edges of bins of `bin_s` [s], so the frequency per bin is
#     (cycles at the bin end - at its start) / bin_s x total_div: f_vco(t), t = 0 at the Sync edge;
# then the curves of all captures of a slope are averaged (the noise drops as 1 / sqrt(n_captures)). Per slope:
#   - f_before: median before the step, f_after: median of the last TAIL_FRAC of the window (the settled value);
#   - step_meas = f_after - f_before against step_expected = FB_DIV x (f_hop - f_ref) (status "step_mismatch" when
#     off by more than STEP_TOL: the scope does not see the divided VCO, or the PLL lost the lock);
#   - t_settle_<band>: time after the step from which the averaged f_vco stays within the band around f_after (end of
#     the last bin outside it; NaN when it is still outside in the tail: not settled inside the window), for the
#     bands of SETTLE_BANDS (a fraction of the step, or a fixed relative error);
#   - noise_ppm: RMS of the averaged curve in the tail around f_after, relative: a band below ~3x this is noise;
#   - t_settle_10pct per capture: median and spread over the captures (cycle slips show as outliers).
# The lock bit is read before the hopping (locked), while hopping (locked_fsk) and after (locked_end).
#
# Setup: pad on the RTB2004 PAD_CH (BNC cable 1:1, PROBE_ATT), FG Sync output to SYNC_CH (BNC, 1:1), FG ch1 the
# reference as for the other scripts. The analyzer is not used.
#
# Results (results/pll/):
#   pll_lock_time_<sample>_<stamp>.csv          one row per point and slope (up / down step)
#   pll_lock_time_<sample>_<stamp>_traces.csv   the averaged f_vco(t) per point and slope (t, mean, std, n)
#
# Tests:
#   lock_time_sweep(supply, points)    # every point of `points` (LOCK_POINTS, QUICK_POINTS), one CSV
#

import contextlib
import logging
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import FILTER_FIELDS
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows, kvco_target_for, trace_csv_path
from sw.tests.pll_range import filter_for, loop_cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"
# IC-LAB firewall login in main(): only for instruments on the IC-LAB network (10.91.16.x); False on the private
# network (10.88.18.x, meas_setup.yaml since 2026-11-09)
ICLAB_LOGIN = False

# Scope (RTB2004): pad on PAD_CH through a BNC cable (1:1) and a DC block with 50 Ohm termination at the scope
# (2026-11-09; usable from 10 MHz), the FG Sync output on SYNC_CH (BNC).
# CH1/CH2 and CH3/CH4 share an ADC pair: with one channel of each pair on, both keep the full sample rate.
PAD_CH = 1
PROBE_ATT = 1  # 10 with the 10:1 probe
SYNC_CH = 4
SYNC_LEVEL = 1.0  # [V] trigger level on the Sync output (~0 -> 3 V into 1 MOhm)
# Pad frequency on the scope: VCO / total_div ~ SCOPE_PAD_F through the external divider (scope_divider). 3x above
# the 10 MHz lower limit of the DC block (less droop on the flat parts of the square), but not at the reference
# frequency (f_vco / FB_DIV): its pickup would then look like the pad (point_cfg warns). The frequency resolution does
# not depend on it (only the crossings at the bin edges count), the time resolution is at least one pad period.
SCOPE_PAD_F = 30e6
# Highest input frequency of the external divider used here: the internal divider (2**set_div_freq) brings the VCO at
# or below it. vco_measure.divider_for goes up to its EXT_DIV_F_MAX (1.25 GHz, the most it was seen to work at, open
# loop); at 4.8 GHz that is /4 = 1.2 GHz, and on 2026-11-09 the pad stopped as soon as the PLL locked there (it ran
# unlocked at ~1.9 GHz, /4 = 475 MHz). Half the edge instead: 4.8 GHz /8 = 600 MHz, then /20 outside (30 MHz).
EXT_DIV_IN_MAX = 650e6
# Sample rate: the record length is chosen for SAMPLE_RATE_TARGET (the RTB2004 maximum) over the 12 divisions of the
# window; lower rates than MIN_SAMPLE_RATE are logged as a warning. The crossings are interpolated between samples,
# which needs samples on the edge: at 625 MSa/s (1.6 ns, the automatic record of 2026-11-09) the edge fell between two
# samples, the crossing times were quantized to the sample grid and the curve showed a +-10 MHz (2000 ppm) zigzag.
SAMPLE_RATE_TARGET = 2.5e9
MIN_SAMPLE_RATE = 1e9
# Pad check before the captures (the scope's FREQ / PEAK after the fit): within PAD_F_TOL of f_pad and at least
# PAD_MIN_VPP, else status "no_clock" and nothing captured (2026-11-09: no pad clock on CH1, the scope read 22 mV of
# 37.5 MHz reference pickup and the analysis turned noise into a 37-44 GHz "VCO").
PAD_F_TOL = 0.02
PAD_MIN_VPP = 0.1
# Wait for Enter at a failed pad check (status "no_clock"), with the PLL still locked, to look at the scope by hand.
PAUSE_ON_NO_CLOCK = True
# Starting view of the pad on PAD_CH (V/div, screen centre [V]): the pad through the DC block into 50 Ohm, around
# 0 V; 1.8 Vpp (2026-11-09, seen on the scope), so +-2 V on screen (at 0.2 V/div it clipped, PEAK unreadable);
# fit_to_signal then zooms in on it
PAD_VIEW = (0.5, 0.0)
# Input bandwidth of PAD_CH: the 20 MHz limit turns the 30 MHz square into a near sine, whose crossings interpolate
# well between samples at any sample rate (a constant delay, no effect on the frequency). With the full bandwidth the
# edges fell between the samples (833 MSa/s, the record length request was not taken, 2026-11-09): +-25 MHz zigzag
# on the up step. 'FULL' to switch it off.
PAD_BANDWIDTH = "B20"
RECORD_LENGTHS = (10e3, 20e3, 50e3, 100e3, 200e3, 500e3, 1e6, 2e6, 5e6, 10e6)  # the scope's record lengths [samples]

# Step and capture defaults (per point overridable). 1 % reference step: VCO 4.8 -> 4.848 GHz, well inside the lock
# range at the nominal supply (top edge 11.92 GHz at 0.75 V, pll_edges_S5_20261106_110104). FSK ~2 kHz: 250 us on each
# frequency, longer than the window, so every step starts from a settled loop. Not a divisor of the reference: with
# 2 kHz (37.5 MHz / 18750) every hop came at the same reference phase, so the pad had the same phase against the
# trigger in every capture and the sample-grid error of the crossings repeated instead of averaging out over the
# captures.
STEP_REL = 0.01
FSK_RATE = 1987.3
# [s] captured per step. 20 us: the PLL settles in ~0.2-0.5 us (2026-11-09, 4.8 GHz), and the scope keeps ~100 k
# samples per record whatever is asked, so a shorter window is a higher sample rate (100 us: 833 MSa/s)
WINDOW = 20e-6
PRE = 0.1  # fraction of the window before the step
BIN_S = 0.1e-6  # [s] frequency bin (3 periods of the 30 MHz pad)
N_CAPTURES = 32  # per slope
TRIGGER_TIMEOUT = 2.0  # [s] per single acquisition
TAIL_FRAC = 0.2  # last fraction of the window taken as settled (f_after, noise_ppm)
STEP_TOL = 0.2  # relative deviation of step_meas from step_expected above which the point is "step_mismatch"
# Settling bands: name -> ("step", fraction of the step) or ("rel", relative frequency error).
SETTLE_BANDS = {"10pct": ("step", 0.1), "1pct": ("step", 0.01), "1000ppm": ("rel", 1e-3), "100ppm": ("rel", 1e-4)}

# Points: f_vco [Hz], PLL supply vdd [V] (None: as it is), and optionally the loop filter (FILTER_FIELDS dict) and
# VCO codes (vco_lut.LUT_FIELDS dict; else the table's pick for the |Kvco| `kvco`); without them FILTER_SCHEDULE.
# Optional: step_rel, fsk_rate, window, n_captures.
# VCO 4.8 GHz (ref 37.5 MHz), coarse 0 min 8 max 8 (table at 0.75 V: 4.8 GHz at Vctrl ~0.51 V), Icp 7 C1 6 C2 0 R1 7,
# at the nominal supply (vdd None: the supply is not touched).
LOCK_F_VCO = 4.8e9
LOCK_CODES = dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=8)
LOCK_FILTER = dict(set_current=7, set_c1=6, set_c2=0, set_r1=7)
LOCK_POINTS = [dict(f_vco=LOCK_F_VCO, vdd=None, filter=LOCK_FILTER, codes=LOCK_CODES)]
# Quick check of the setup (cabling, trigger, analysis): the same at the nominal supply, 8 captures per slope (~1 min).
QUICK_POINTS = [dict(f_vco=LOCK_F_VCO, vdd=None, filter=LOCK_FILTER, codes=LOCK_CODES, n_captures=8)]

LOCK_COLUMNS = (["time", "label", "vdd_set", "f_ref", "f_hop", "step_rel", "fsk_rate", "f_vco", "kvco_request",
                 "vco_pick"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
                + ["vctrl_pred", "kvco_pred", "set_div_freq", "clk_div_val", "total_div", "f_pad", "pad_f_meas",
                   "pad_vpp", "pad_f_rec", "pad_f_rec_spread", "locked",
                   "locked_fsk", "locked_end", "slope", "direction", "n_captures", "n_valid", "sample_rate",
                   "record_points", "window", "pre", "bin_s", "f_before", "f_after", "step_meas", "step_expected",
                   "noise_ppm"] + ["t_settle_" + b for b in SETTLE_BANDS]
                + ["t_settle_10pct_capt_median", "t_settle_10pct_capt_std", "t_settle_10pct_capt", "status"]
                + list(pll_setup.SUPPLY_COLUMNS))
TRACE_COLUMNS = ["label", "vdd_set", "f_vco", "slope", "direction", "t", "f_vco_mean", "f_vco_std", "n"]


# ---------------------------------------------------------------------------------------------
# Analysis (no instruments)
# ---------------------------------------------------------------------------------------------
def crossing_times(t, v):
    """Times [s] of the rising crossings of `v` through its mid level (between the 5th and 95th percentile),
    interpolated between samples; crossings closer than half the median period to the previous one (noise on an
    edge) dropped. Empty when there is no clock (fewer than 3 crossings)."""
    lo, hi = np.percentile(v, [5, 95])
    th = (lo + hi) / 2
    idx = np.flatnonzero((v[:-1] < th) & (v[1:] >= th))
    if len(idx) < 3:
        return np.array([])
    tc = t[idx] + (th - v[idx]) / (v[idx + 1] - v[idx]) * (t[idx + 1] - t[idx])
    min_gap = 0.5 * np.median(np.diff(tc))
    keep = [0]
    for i in range(1, len(tc)):
        if tc[i] - tc[keep[-1]] >= min_gap:
            keep.append(i)
    return tc[keep]


def frequency_curve(tc, edges, total_div):
    """VCO frequency [Hz] per bin between `edges` [s] from the crossing times `tc` of the pad (VCO / total_div): the
    cycle count, interpolated at the bin edges, per bin length. NaN for bins not fully inside the crossings."""
    cycles = np.interp(edges, tc, np.arange(len(tc)))
    f = np.diff(cycles) / np.diff(edges) * total_div
    f[(edges[:-1] < tc[0]) | (edges[1:] > tc[-1])] = np.nan
    return f


def settled_value(edges, f, tail_frac=TAIL_FRAC):
    """(f_before, f_after, tail RMS) [Hz]: the median before t = 0, the median and RMS of the last `tail_frac` of
    the bins."""
    pre = edges[1:] <= 0
    n_tail = max(int(round(tail_frac * len(f))), 3)
    tail = f[-n_tail:]
    return np.nanmedian(f[pre]) if pre.any() else np.nan, np.nanmedian(tail), np.nanstd(tail)


def settle_time(edges, f, f_after, tol, tail_frac=TAIL_FRAC):
    """Time [s] after the step (t = 0) from which `f` stays within `tol` [Hz] of `f_after`: the end of the last bin
    outside it (0: never outside). NaN when that bin lies in the tail (the last `tail_frac`: not settled inside the
    window) or there is no valid bin after the step."""
    post = edges[:-1] >= 0
    fp, ends = f[post], edges[1:][post]
    valid = ~np.isnan(fp)
    if not valid.any() or np.isnan(f_after):
        return np.nan
    outside = np.flatnonzero(valid & (np.abs(fp - f_after) > tol))
    if not len(outside):
        return 0.0
    last = outside[-1]
    if last >= len(fp) - max(int(round(tail_frac * len(f))), 3):
        return np.nan
    return ends[last]


def band_tol(band, step, f_after):
    """Half width [Hz] of the band `band` (an entry of SETTLE_BANDS) for a step of `step` [Hz] settling at f_after."""
    kind, value = band
    return value * abs(step) if kind == "step" else value * f_after


# ---------------------------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------------------------
def open_scope():
    """The RTB2004 (pll_setup.open_rtb_scope) with the pad probe on PAD_CH and FREQ / PEAK / MEAN in slots 1-3 (for
    fit_to_signal)."""
    scope = pll_setup.open_rtb_scope()
    scope.set_probe_attenuation(PAD_CH, PROBE_ATT)
    scope.set_probe_attenuation(SYNC_CH, 1)
    return scope


def setup_capture(scope, f_pad, window, pre):
    """Scope on the pad (expected at `f_pad` [Hz]) of a locked PLL, without FSK: a fixed view for the pad
    (PAD_VIEW), then refined to what arrives (fit_to_signal); then only PAD_CH and SYNC_CH on, the window `window` [s]
    with `pre` of it before the trigger, a record long enough for SAMPLE_RATE_TARGET. Returns {pad_f_meas [Hz], pad_vpp
    [V]: the scope's own reading of the pad before the window is set (NaN: none), sample_rate [Sa/s]}. The trigger is
    set per slope (set_trigger).
    No autoscale: on 2026-11-09 it left CH1 at a few mV/div, the 1.8 V pad clipped (read as 23 mV) and the Sync output
    on CH4 (37.5 MHz, 3 V, while not hopping) coupled in."""
    for ch in range(1, 5):
        if ch not in (PAD_CH, SYNC_CH):
            scope.channel_off(ch)
    scale, offset = PAD_VIEW
    scope.set_channel(PAD_CH, scale=scale, offset=offset)
    scope.set_bandwidth_limit(PAD_CH, PAD_BANDWIDTH)
    scope.set_timebase(5 / f_pad / 10)
    scope.set_edge_trigger(PAD_CH, level=offset)  # auto mode: the pad is acquired without the Sync output
    for slot, meas in zip((1, 2, 3), ("FREQ", "PEAK", "MEAN")):
        scope.set_measurement(slot, PAD_CH, meas)
    scope.run()
    time.sleep(1.0)
    if not scope.fit_to_signal(PAD_CH, freq_slot=1, peak_slot=2, mean_slot=3, min_vpp=PAD_MIN_VPP):
        scope.set_channel(PAD_CH, scale=scale, offset=offset)  # back to the fixed view for the readings below
        time.sleep(1.0)
    pad = dict(pad_f_meas=scope.wait_valid(1), pad_vpp=scope.wait_valid(2))
    scope.set_channel(SYNC_CH, scale=1.0, offset=1.5)
    scope.set_timebase(window / 10)
    scope.set_horizontal_position(window / 2 - pre * window)  # the trigger at `pre` of the window
    points = next((n for n in RECORD_LENGTHS if n >= window * 1.2 * SAMPLE_RATE_TARGET), RECORD_LENGTHS[-1])
    try:
        scope.set_record_length(points)
    except ValueError as e:
        logging.warning("Record length %d refused, automatic record length (%s)", points, e)
        scope.tool.clear()
        scope.write("*CLS", check=False)
    rate = scope.sample_rate()
    if rate < MIN_SAMPLE_RATE:
        logging.warning("Sample rate %.0f MSa/s below %.0f MSa/s: the crossings are coarse", rate / 1e6,
                        MIN_SAMPLE_RATE / 1e6)
    pad.update(record_check(scope))
    return dict(pad, sample_rate=rate)


def record_check(scope):
    """The pad from one free-running record of the capture window (the same analysis as the captures, not the
    scope's FREQ readout, which here sees only ~5 periods: 28.7 and 31.7 MHz for a 30 MHz pad, 2026-11-09):
    {pad_f_rec [Hz]: crossings over the whole record, pad_f_rec_spread [Hz]: max - min of its 1 us averages
    (wide: the pad frequency wanders, e.g. not really locked)}; NaN when no record or no clock."""
    out = dict(pad_f_rec=np.nan, pad_f_rec_spread=np.nan)
    scope.set_trigger(PAD_CH, 0.0, mode="AUTO")
    if not scope.single(timeout=TRIGGER_TIMEOUT):
        return out
    t, v = scope.read_waveform(PAD_CH)
    tc = crossing_times(t, v)
    if len(tc) < 10:
        return out
    edges = np.arange(tc[0], tc[-1], 1e-6)
    f = np.diff(np.interp(edges, tc, np.arange(len(tc)))) / np.diff(edges)
    out.update(pad_f_rec=(len(tc) - 1) / (tc[-1] - tc[0]),
               pad_f_rec_spread=np.max(f) - np.min(f) if len(f) else np.nan)
    return out


def capture_slope(scope, slope, n_captures, total_div, edges):
    """`n_captures` single acquisitions triggered on the Sync edge `slope` ("POS" / "NEG"), each turned into f_vco
    per bin (frequency_curve). Returns (curves: list of arrays, record points of the last capture)."""
    scope.set_trigger(SYNC_CH, SYNC_LEVEL, slope=slope, mode="NORM")
    curves, n_points = [], 0
    for i in range(n_captures):
        if not scope.single(timeout=TRIGGER_TIMEOUT):
            logging.warning("Capture %d/%d (%s): no trigger on the Sync output within %.1f s", i + 1, n_captures,
                            slope, TRIGGER_TIMEOUT)
            continue
        t, v = scope.read_waveform(PAD_CH)
        n_points = len(t)
        tc = crossing_times(t, v)
        if len(tc) < 3:
            logging.warning("Capture %d/%d (%s): no clock on the pad", i + 1, n_captures, slope)
            continue
        curves.append(frequency_curve(tc, edges, total_div))
    return curves, n_points


# ---------------------------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------------------------
def scope_divider(f_vco, f_pad=SCOPE_PAD_F, f_in_max=EXT_DIV_IN_MAX):
    """{set_div_freq, clk_div_val} of the external divider path (pll_clk_o_en 0, clk_div_en 1; total division
    2**set_div_freq x 2 (clk_div_val + 1)): the smallest internal division bringing `f_vco` [Hz] at or below
    `f_in_max` at the external divider, which then brings it closest to `f_pad` on the pad."""
    set_div_freq = next((n for n in range(8) if f_vco / 2 ** n <= f_in_max), 7)  # 3-bit field
    clk_div_val = round(f_vco / (f_pad * 2 ** set_div_freq * 2)) - 1
    return dict(set_div_freq=set_div_freq, clk_div_val=min(max(clk_div_val, 0), 1023))  # 10-bit field


def point_cfg(lut, point):
    """(cfg, row fields) of a point: the loop config of pll_range.loop_cfg with the filter and VCO codes of the point
    (else FILTER_SCHEDULE and the table's pick), its output on the external divider at ~SCOPE_PAD_F."""
    f_vco = point["f_vco"]
    loop_filter, kvco = filter_for(f_vco / FB_DIV)
    loop_filter = point.get("filter", loop_filter)
    kvco = point.get("kvco", kvco)
    cfg = loop_cfg(f_vco, loop_filter)
    if "codes" in point:
        cfg.update(point["codes"])
        fields = dict(vco_pick="manual", kvco_request="")
    else:
        target, _, _ = kvco_target_for(lut, f_vco, kvco)
        cfg = lut.update_config(cfg, f_vco, target)
        fields = dict(vco_pick="lut", kvco_request=kvco)
    cfg.update(pll_clk_o_en=0, clk_div_en=1)
    cfg.update(scope_divider(f_vco))
    _, total_div = calculate_div_factor(cfg)
    if abs(f_vco / total_div / (f_vco / FB_DIV) - 1) < 0.1:
        logging.warning("Pad %.3f MHz within 10 %% of the reference %.3f MHz: reference pickup on the scope looks "
                        "like the pad, change SCOPE_PAD_F", f_vco / total_div / 1e6, f_vco / FB_DIV / 1e6)
    try:
        op = lut.predict(cfg, f_vco)
    except ValueError:  # the codes do not reach f_vco in the table
        op = dict(vctrl_pred=np.nan, kvco_pred=np.nan)
    fields.update(vco_lut.vco_codes(cfg), **{k: cfg[k] for k in FILTER_FIELDS}, **op, set_div_freq=cfg["set_div_freq"],
                  clk_div_val=cfg["clk_div_val"], total_div=total_div, f_pad=f_vco / total_div)
    return cfg, fields


def summarize(curves, edges, step_expected, f_before_expected):
    """Row fields of one slope from its per-capture curves, and the averaged curve (mean, std, n per bin). Status
    "wrong_frequency" when f_before is off f_before_expected [Hz] by more than PAD_F_TOL (not the divided VCO)."""
    stack = np.array(curves)
    with warnings.catch_warnings():  # all-NaN bins (outside a capture's crossings)
        warnings.simplefilter("ignore", RuntimeWarning)
        mean, std, n = np.nanmean(stack, axis=0), np.nanstd(stack, axis=0), np.sum(~np.isnan(stack), axis=0)
    f_before, f_after, tail_rms = settled_value(edges, mean)
    step = f_after - f_before
    fields = dict(n_valid=len(curves), f_before=f_before, f_after=f_after, step_meas=step, step_expected=step_expected,
                  direction="up" if step > 0 else "down", noise_ppm=tail_rms / f_after * 1e6)
    for name, band in SETTLE_BANDS.items():
        fields["t_settle_" + name] = settle_time(edges, mean, f_after, band_tol(band, step, f_after))
    per_capture = []
    for f in curves:
        fb, fa, _ = settled_value(edges, f)
        per_capture.append(settle_time(edges, f, fa, band_tol(SETTLE_BANDS["10pct"], fa - fb, fa)))
    per_capture = np.array(per_capture)
    fields.update(t_settle_10pct_capt_median=np.nanmedian(per_capture) if (~np.isnan(per_capture)).any() else np.nan,
                  t_settle_10pct_capt_std=np.nanstd(per_capture) if (~np.isnan(per_capture)).any() else np.nan,
                  t_settle_10pct_capt=" ".join("%.4g" % x for x in per_capture))
    if not abs(f_before / f_before_expected - 1) < PAD_F_TOL:
        fields["status"] = "wrong_frequency"
    elif band_tol(SETTLE_BANDS["10pct"], step, f_after) < 3 * tail_rms:
        fields["status"] = "too_noisy"  # the 10 % band is inside the noise: the settling times measure the noise
    elif np.isnan(fields["t_settle_10pct"]):
        fields["status"] = "not_settled"
    elif abs(step - step_expected) > STEP_TOL * abs(step_expected):
        fields["status"] = "step_mismatch"
    else:
        fields["status"] = "ok"
    return fields, (mean, std, n)


def lock_time_point(pll, fg, scope, lut, point, csv_path, supply=None, label=""):
    """One point: set the supply, lock at f_ref = f_vco / FB_DIV without FSK, set up the scope, FSK on, capture
    both slopes, FSK off. Appends one row per slope to `csv_path` and the averaged curves to its _traces.csv."""
    f_vco = point["f_vco"]
    f_ref = f_vco / FB_DIV
    step_rel = point.get("step_rel", STEP_REL)
    fsk_rate = point.get("fsk_rate", FSK_RATE)
    window = point.get("window", WINDOW)
    n_captures = point.get("n_captures", N_CAPTURES)
    f_hop = f_ref * (1 + step_rel)
    base = dict(time=datetime.now().isoformat(timespec="seconds"), label=label, vdd_set=point.get("vdd"), f_ref=f_ref,
                f_hop=f_hop, step_rel=step_rel, fsk_rate=fsk_rate, f_vco=f_vco, window=window, pre=PRE, bin_s=BIN_S,
                n_captures=n_captures, status="error")
    rows, traces = [], []
    try:
        if point.get("vdd") is not None:
            supply.set(point["vdd"])
        cfg, fields = point_cfg(lut, point)
        base.update(fields)
        fg.fsk_off(1)
        pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50, fg=fg)
        pll_setup.load_config(pll, cfg)
        base["locked"] = int(pll.wait_lock(timeout=3.0))
        logging.info("%s: VCO %.1f MHz (ref %.4f MHz), coarse %d min %d max %d, Icp %d C1 %d C2 %d R1 %d, /%d -> pad "
                     "%.3f MHz: %s", label, f_vco / 1e6, f_ref / 1e6, cfg["vco_tune_coarse"], cfg["vco_current_min"],
                     cfg["vco_current_max"], cfg["set_current"], cfg["set_c1"], cfg["set_c2"], cfg["set_r1"],
                     base["total_div"], base["f_pad"] / 1e6, "LOCKED" if base["locked"] else "NOT LOCKED")
        base.update(pll_setup.measure_pll_supply(supply, label=label))
        if not base["locked"]:
            base["status"] = "not_locked"
            rows = [base]
            return
        base.update(setup_capture(scope, base["f_pad"], window, PRE))
        if not (abs(base["pad_f_rec"] / base["f_pad"] - 1) < PAD_F_TOL and base["pad_vpp"] >= PAD_MIN_VPP):
            # also NaN: the scope found nothing; not analysed, the crossings would be noise
            logging.error("%s: no pad clock on CH%d: record %.4f MHz (1 us averages spread %.4f MHz), scope readout "
                          "%.4f MHz, %.3f Vpp; expected %.4f MHz, >= %.2f Vpp", label, PAD_CH, base["pad_f_rec"] / 1e6,
                          base["pad_f_rec_spread"] / 1e6, base["pad_f_meas"] / 1e6, base["pad_vpp"],
                          base["f_pad"] / 1e6, PAD_MIN_VPP)
            base["status"] = "no_clock"
            rows = [base]
            if PAUSE_ON_NO_CLOCK:
                input("\n>>> Stopped: PLL locked, reference on, no FSK, the scope as the script left it. Check CH%d "
                      "(expected %.4f MHz), then Enter to end this point: " % (PAD_CH, base["f_pad"] / 1e6))
            return
        logging.info("Pad on CH%d: %.4f MHz over the record (1 us averages spread %.4f MHz; scope readout %.4f MHz), "
                     "%.3f Vpp, %.0f MSa/s", PAD_CH, base["pad_f_rec"] / 1e6, base["pad_f_rec_spread"] / 1e6,
                     base["pad_f_meas"] / 1e6, base["pad_vpp"], base["sample_rate"] / 1e6)
        n_pre = int(round(PRE * window / BIN_S))
        n_post = int(round((1 - PRE) * window / BIN_S)) - 1  # one bin short of the record end
        edges = np.arange(-n_pre, n_post + 1) * BIN_S
        fg.set_fsk(1, f_hop, fsk_rate)
        fg.set_sync(1, True)
        time.sleep(0.5)
        base["locked_fsk"] = pll.read_lock()
        logging.info("FSK on: ref %.4f <-> %.4f MHz at %.0f Hz (VCO step %.2f MHz), lock bit while hopping: %s",
                     f_ref / 1e6, f_hop / 1e6, fsk_rate, FB_DIV * (f_hop - f_ref) / 1e6, base["locked_fsk"])
        for slope, step_expected in (("POS", FB_DIV * (f_hop - f_ref)), ("NEG", FB_DIV * (f_ref - f_hop))):
            row = dict(base, slope=slope, status="no_capture", n_valid=0)
            curves, row["record_points"] = capture_slope(scope, slope, n_captures, base["total_div"], edges)
            if curves:
                fields, (mean, std, n) = summarize(curves, edges, step_expected,
                                                   f_vco if slope == "POS" else FB_DIV * f_hop)
                row.update(fields)
                centres = (edges[:-1] + edges[1:]) / 2
                traces += [dict(label=label, vdd_set=base["vdd_set"], f_vco=f_vco, slope=slope,
                                direction=row["direction"], t=t, f_vco_mean=m, f_vco_std=s, n=k)
                           for t, m, s, k in zip(centres, mean, std, n)]
                logging.info("%s %s step (%d/%d captures): %.3f -> %.3f MHz (expected step %.3f MHz), noise %.0f ppm; "
                             "settled to 10 %% / 1 %% of the step in %.2f / %.2f us, 1000 / 100 ppm in %.2f / %.2f "
                             "us (per capture 10 %%: %.2f +- %.2f us): %s", label, row["direction"], len(curves),
                             n_captures, row["f_before"] / 1e6, row["f_after"] / 1e6, step_expected / 1e6,
                             row["noise_ppm"], *(row["t_settle_" + b] * 1e6 for b in SETTLE_BANDS),
                             row["t_settle_10pct_capt_median"] * 1e6, row["t_settle_10pct_capt_std"] * 1e6,
                             row["status"])
            rows.append(row)
        fg.fsk_off(1)
        time.sleep(0.5)
        locked_end = pll.read_lock()
        for row in rows:
            row["locked_end"] = locked_end
    except pyvisa.VisaIOError:
        raise  # instrument connection lost: stop
    except Exception:
        logging.exception("%s: point failed, continuing", label)
    finally:
        append_rows(csv_path, LOCK_COLUMNS, rows or [base])
        append_rows(trace_csv_path(csv_path), TRACE_COLUMNS, traces)


def lock_time_sweep(supply=None, points=LOCK_POINTS, sample="S5"):
    """Lock time (lock_time_point) at every point of `points`, one CSV results/pll/pll_lock_time_<sample>_<stamp>.csv
    (+ _traces.csv). `supply`: PllSupplyChannel, needed when a point has a vdd; back to its nominal at the end, also
    on an error. Returns the CSV path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_lock_time_{}_{}.csv".format(sample, datetime.now().strftime("%Y%m%d_%H%M%S"))
    lut = vco_lut.VcoLUT(sample=sample)
    fg = pll = scope = None
    try:
        fg = pll_setup.open_reference_generator()
        scope = open_scope()
        pll = pll_setup.connect()
        for i, point in enumerate(points, 1):
            label = "%d/%d %.3f GHz %s" % (i, len(points), point["f_vco"] / 1e9,
                                            "%.2f V" % point["vdd"] if point.get("vdd") is not None else "nominal")
            logging.info("=== Lock time %s ===", label)
            lock_time_point(pll, fg, scope, lut, point, csv_path, supply=supply, label=label)
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # FSK, Sync and the reference off with *RST at the next open; output off here
        if scope is not None:
            scope.close()
        if supply is not None and any(p.get("vdd") is not None for p in points):
            supply.set(supply.nominal)
    logging.info("Lock times written to %s (curves: %s)", csv_path, trace_csv_path(csv_path).name)
    return csv_path


def debug_hold(point=QUICK_POINTS[0], sample="S5"):
    """Manual debug, no scope control and nothing written: lock the PLL at the point (its config as lock_time_point
    loads it, reference without FSK) and wait for Enter, with the lock bit polled once per Enter; then the same with
    FSK and the Sync output on (the reference hopping as in the measurement), then FSK off. Look at the pad (PAD_CH,
    expected f_pad) and the Sync output (SYNC_CH, expected a FSK_RATE square while hopping) on the scope meanwhile.
    The reference is turned off at the end (the PLL then drifts to the slowest VCO frequency)."""
    lut = vco_lut.VcoLUT(sample=sample)
    cfg, fields = point_cfg(lut, point)
    f_vco = point["f_vco"]
    f_ref = f_vco / FB_DIV
    f_hop = f_ref * (1 + point.get("step_rel", STEP_REL))
    fsk_rate = point.get("fsk_rate", FSK_RATE)
    fg = pll = None
    try:
        fg = pll_setup.open_reference_generator()
        pll = pll_setup.connect()
        pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50, fg=fg)
        pll_setup.load_config(pll, cfg)
        locked = pll.wait_lock(timeout=3.0)
        logging.info("VCO %.1f MHz (ref %.4f MHz), coarse %d min %d max %d, Icp %d C1 %d C2 %d R1 %d: %s. Expected on "
                     "CH%d: %.4f MHz (VCO / %d)", f_vco / 1e6, f_ref / 1e6, cfg["vco_tune_coarse"],
                     cfg["vco_current_min"], cfg["vco_current_max"], cfg["set_current"], cfg["set_c1"], cfg["set_c2"],
                     cfg["set_r1"], "LOCKED" if locked else "NOT LOCKED", PAD_CH, fields["f_pad"] / 1e6,
                     fields["total_div"])
        while input("\n>>> Locked, no FSK (Sync follows the carrier). Check CH%d; Enter = read the lock bit, "
                    "'n' + Enter = next step: " % PAD_CH).strip().lower() != "n":
            logging.info("Lock bit: %s", pll.read_lock())
        fg.set_fsk(1, f_hop, fsk_rate)
        fg.set_sync(1, True)
        logging.info("FSK on: ref %.4f <-> %.4f MHz at %.0f Hz (VCO %.1f <-> %.1f MHz)", f_ref / 1e6, f_hop / 1e6,
                     fsk_rate, f_vco / 1e6, FB_DIV * f_hop / 1e6)
        while input("\n>>> Hopping. CH%d: the pad, CH%d: the Sync output (expected a %.0f Hz square). Enter = read the "
                    "lock bit, 'n' + Enter = end: " % (PAD_CH, SYNC_CH, fsk_rate)).strip().lower() != "n":
            logging.info("Lock bit: %s", pll.read_lock())
        fg.fsk_off(1)
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off


def start_log_file():
    """Also write the log to results/logs/pll_lock_time_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_lock_time_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    start_log_file()
    # IC-LAB firewall login: opens the lab network to the instruments. Not needed on the private network
    # (10.88.18.x since 2026-11-09, meas_setup.yaml), where the IC-LAB site may not be reachable at all.
    login = iclab_session(Parser().get_credentials()) if ICLAB_LOGIN else contextlib.ExitStack()
    with login, pll_setup.core_in_reset():  # core in reset: no pollution
        supply = pll_setup.PllSupplyChannel(channel=2)  # E36312A CH2; close() programs the nominal again
        try:
            # Manual debug: lock at 4.8 GHz and wait (Enter), then hop (Enter); the scope is left to you
            # debug_hold()
            # Quick check of the cabling, trigger and analysis: 4.8 GHz at the nominal supply, 8 captures per slope
            lock_time_sweep(supply, QUICK_POINTS)
            # 4.8 GHz (LOCK_CODES, LOCK_FILTER) at the nominal supply, N_CAPTURES per slope (~3 min)
            # lock_time_sweep(supply, LOCK_POINTS)
        finally:
            supply.close()


if __name__ == "__main__":
    main()

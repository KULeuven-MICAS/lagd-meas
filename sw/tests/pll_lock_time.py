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
# lib/vco_measure.py: a clean square on the MXR058A), is captured on the MXR058A (over LAN) channel PAD_CH,
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
# Setup: pad on the MXR058A PAD_CH (CH1, 50 Ohm input), FG Sync output to SYNC_CH (CH2, 1 MOhm input), FG ch1 the
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
from fractions import Fraction
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.lab_instruments.drivers.keysight_scope_mxr058a import CLOCK_MEASUREMENTS
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import FILTER_FIELDS
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows, kvco_target_for, trace_csv_path
from sw.tests.pll_range import filter_for, loop_cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"
# IC-LAB firewall login in main(): only for instruments on the IC-LAB network (10.91.16.x); False on the private
# network (10.88.18.x, meas_setup.yaml since 2026-11-09)
ICLAB_LOGIN = False

# Scope (Keysight MXR058A, LAN, meas_setup.yaml `scope_mxr`): pad on PAD_CH (CH1) into the 50 Ohm input, the FG Sync
# output on SYNC_CH (CH2, 1 MOhm input).
PAD_CH = 1
SYNC_CH = 2
SYNC_LEVEL = 1.0  # [V] trigger level on the Sync output (~0 -> 3 V into 1 MOhm)
# Pad frequency on the scope: VCO / total_div ~ SCOPE_PAD_F through the external divider (scope_divider), but not at
# the reference frequency (f_vco / FB_DIV): its pickup would then look like the pad (point_cfg warns). The time
# resolution of the curve is one pad period: 100 MHz = 10 ns (30 MHz, 33 ns, only just resolved the 35 ns rise of the
# response at 4.8 GHz, 2026-11-09). At 4.8 GHz: /8 internal, /2 x 3 external = 48 total, pad / reference = 8 / 3.
SCOPE_PAD_F = 100e6
# Shape of the reference from the FG ("square" as for the other scripts, or "sine": the same 0 -> 1.8 V swing with slower
# edges, to couple less into the pad path; the sine is tried from 2026-11-09, check that the PLL still locks)
REF_SHAPE = "sine"
# Highest input frequency of the external divider used here: the internal divider (2**set_div_freq) brings the VCO at
# or below it. vco_measure.divider_for goes up to its EXT_DIV_F_MAX (1.25 GHz, the most it was seen to work at, open
# loop); at 4.8 GHz that is /4 = 1.2 GHz, and on 2026-11-09 the pad stopped as soon as the PLL locked there (it ran
# unlocked at ~1.9 GHz, /4 = 475 MHz). Half the edge instead: 4.8 GHz /8 = 600 MHz, then /20 outside (30 MHz).
EXT_DIV_IN_MAX = 650e6
# Sample rate: left automatic on the MXR058A (16 GSa/s at these windows, read back); rates below MIN_SAMPLE_RATE are
# logged as a warning. The crossings are interpolated between samples,
# which needs samples on the edge: at 625 MSa/s (1.6 ns, the automatic record of 2026-11-09) the edge fell between two
# samples, the crossing times were quantized to the sample grid and the curve showed a +-10 MHz (2000 ppm) zigzag.
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
# Long free-running pad record without FSK for the distribution of the pad periods (long_pad_record): [s] and the file
# in RESULTS_DIR (overwritten by every run). 200 us = 6000 pad periods at 16 GSa/s = 3.2 M samples; 0 = no long record.
PAD_RECORD_S = 200e-6
PAD_RECORD_FILE = "pll_lock_time_pad_record.npz"
PAD_RECORD = {}  # the short record of record_check (t, v), for the file of long_pad_record

# Step and capture defaults (per point overridable). 3 % reference step: VCO 4.8 -> 4.944 GHz (a 144 MHz step: 3x the
# signal of the 1 % step against the same noise per bin, 2026-11-09; a large step also slews, so the lock time depends
# on its size: compare 1 / 3 / 5 % in LOCK_POINTS), well inside the lock
# range at the nominal supply (top edge 11.92 GHz at 0.75 V, pll_edges_S5_20261106_110104). FSK ~2 kHz: 250 us on each
# frequency, longer than the window, so every step starts from a settled loop. Not a divisor of the reference: with
# 2 kHz (37.5 MHz / 18750) every hop came at the same reference phase, so the pad had the same phase against the
# trigger in every capture and the sample-grid error of the crossings repeated instead of averaging out over the
# captures.
STEP_REL = 0.03
FSK_RATE = 1987.3
# [s] captured per step. 20 us: the PLL settles in ~0.2-0.5 us (2026-11-09, 4.8 GHz), and the scope keeps ~100 k
# samples per record whatever is asked, so a shorter window is a higher sample rate (100 us: 833 MSa/s)
WINDOW = 20e-6
PRE = 0.1  # fraction of the window before the step
# The reference couples into the pad (2026-11-09, at a 30 MHz pad): the pad periods repeat 32.4 / 32.5 / 34.5 / 33.9 ns
# (+-1 ns, the beat of the 37.5 MHz reference and the pad; the random jitter in each phase is only ~30 ps). The PLL
# locks the two, so the pattern repeats every pickup_periods(total_div) pad periods: the numerator of pad / reference
# = FB_DIV / total_div (30 MHz: 4/5, 4 periods = 5 reference periods = 133.3 ns; 100 MHz: 8/3, 8 periods = 80 ns).
# True: the pattern is estimated per capture from the crossings before the step (remove_pickup) and subtracted from all
# of them, so bins of any number of pad periods work (offline on the long record at 30 MHz: 2 periods gave 1.9 MHz
# noise on the VCO frequency per bin, 1 period 4.3 MHz; without it only multiples of the pattern length work: 3 periods
# gave a +-20 MHz zigzag from bin to bin). False: no correction, bins of one pattern length (it then counts out).
PICKUP_CORRECTION = True


def pickup_periods(total_div):
    """Pad periods after which the reference pickup repeats: the numerator of pad / reference = FB_DIV / total_div."""
    return Fraction(FB_DIV, int(total_div)).numerator


def default_bin(f_pad, total_div):
    """[s] frequency bin (per point: `bin_s`): one pad period with the correction, else one pickup pattern."""
    return (1 if PICKUP_CORRECTION else pickup_periods(total_div)) / f_pad
N_CAPTURES = 32  # per slope
TRIGGER_TIMEOUT = 2.0  # [s] per single acquisition
TAIL_FRAC = 0.2  # last fraction of the window taken as settled (f_after, noise_ppm)
STEP_TOL = 0.2  # relative deviation of step_meas from step_expected above which the point is "step_mismatch"
# Settling bands: name -> ("step", fraction of the step) or ("rel", relative frequency error).
SETTLE_BANDS = {"10pct": ("step", 0.1), "5pct": ("step", 0.05), "2pct": ("step", 0.02), "1pct": ("step", 0.01),
                "1000ppm": ("rel", 1e-3), "100ppm": ("rel", 1e-4)}

# Points: f_vco [Hz], PLL supply vdd [V] (None: as it is), and optionally the loop filter (FILTER_FIELDS dict) and
# VCO codes (vco_lut.LUT_FIELDS dict; else the table's pick for the |Kvco| `kvco`); without them FILTER_SCHEDULE.
# Optional: step_rel, fsk_rate, window, n_captures.
# VCO 4.8 GHz (ref 37.5 MHz), coarse 0 min 8 max 8 (table at 0.75 V: 4.8 GHz at Vctrl ~0.51 V), Icp 7 C1 6 C2 0 R1 7,
# at the nominal supply (vdd None: the supply is not touched).
LOCK_F_VCO = 4.8e9
LOCK_CODES = dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=8)
LOCK_FILTER = dict(set_current=7, set_c1=6, set_c2=0, set_r1=7)
LOCK_POINTS = [dict(f_vco=LOCK_F_VCO, vdd=None, filter=LOCK_FILTER, codes=LOCK_CODES, step_rel=step)
               for step in (0.01, 0.03, 0.05)]
# Data set (main): the lock-time number. One point: 4.8 GHz at the nominal supply, the loop filter LOCK_FILTER and the codes
# LOCK_CODES unchanged, a 5 % reference step (VCO 4.8 -> 5.04 GHz, 240 MHz: the best signal against the noise and still
# linear, 2026-11-09 sweeps of 0.5-5 % steps: fn, Q, overshoot and rise time do not depend on the step), 1000 captures per
# slope (the noise of the averaged curve is 14 MHz / sqrt(1000) = 0.45 MHz: the +-1 % band of the step, 2.4 MHz, is 5 sigma)
# in a 5 us window (the loop settles in < 1 us; 4x fewer samples per capture than 20 us: faster). Read the lock time as
# t_settle_2pct / t_settle_1pct (settling to +-2 % / +-1 % of the step, up and down) in the CSV / the log line.
DATA_POINTS = [dict(f_vco=LOCK_F_VCO, vdd=None, filter=LOCK_FILTER, codes=LOCK_CODES, step_rel=0.05, window=5e-6,
                    n_captures=1000, tag="step 5.0 %")]

# Quick check of the setup (cabling, trigger, analysis): the same at the nominal supply, 32 captures per slope (~1 min).
QUICK_POINTS = [dict(f_vco=LOCK_F_VCO, vdd=None, filter=LOCK_FILTER, codes=LOCK_CODES, n_captures=32)]

LOCK_COLUMNS = (["time", "label", "vdd_set", "f_ref", "f_hop", "step_rel", "fsk_rate", "f_vco", "kvco_request",
                 "vco_pick"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
                + ["vctrl_pred", "kvco_pred", "set_div_freq", "clk_div_val", "total_div", "f_pad", "pad_f_meas",
                   "pad_vpp", "pad_f_rec", "pad_f_rec_spread", "locked",
                   "locked_fsk", "locked_end", "slope", "direction", "n_captures", "n_valid", "sample_rate",
                   "record_points", "window", "pre", "bin_s", "f_before", "f_after", "step_meas", "step_expected",
                   "noise_ppm", "t_rise_10_90", "overshoot_pct", "t_peak"] + ["t_settle_" + b for b in SETTLE_BANDS]
                + ["t_settle_10pct_capt_median", "t_settle_10pct_capt_std", "t_settle_10pct_capt", "t50_capt_median",
                   "t50_capt_std", "t50_capt", "status"]
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


def remove_pickup(tc, periods, t_end=-0.1e-6, tail_frac=TAIL_FRAC):
    """The crossing times `tc` [s] with the repeating timing pattern of the reference pickup subtracted. The pattern
    differs at the two frequencies of the hop (the coupling delay is fixed in ns, the cycle is not), so there are two:
    the deviations from a straight line through the crossings before `t_end` (before the step, the PLL settled) and
    through the last `tail_frac` of the crossings (after it, settled), each averaged per position in the
    `periods`-period pattern. The first is subtracted from the crossings before the step (t < 0), the second from the
    rest. Unchanged when either has fewer than 3 crossings per position."""
    i = np.arange(len(tc))
    pre = tc < t_end
    tail = i >= len(tc) - int(round(tail_frac * len(tc)))
    if pre.sum() < 3 * periods or tail.sum() < 3 * periods:
        return tc

    def template(sel):
        slope, intercept = np.polyfit(i[sel], tc[sel], 1)
        res = tc[sel] - (intercept + slope * i[sel])
        t = np.array([res[i[sel] % periods == k].mean() for k in range(periods)])
        return t - t.mean()

    t_pre, t_post = template(pre), template(tail)
    return tc - np.where(tc < 0, t_pre[i % periods], t_post[i % periods])


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


def first_crossing(t, x, level):
    """Time [s] at which `x` (the step response normalised to 0 -> 1) first reaches `level`, interpolated between the
    bins; NaN when it does not."""
    ok = ~np.isnan(x)
    t, x = t[ok], x[ok]
    above = np.flatnonzero(x >= level)
    if not len(above):
        return np.nan
    k = above[0]
    return t[0] if k == 0 else t[k - 1] + (level - x[k - 1]) / (x[k] - x[k - 1]) * (t[k] - t[k - 1])


def step_shape(edges, mean, f_before, f_after):
    """{t_rise_10_90 [s]: from 10 % to 90 % of the step, overshoot_pct [%]: the peak beyond f_after in % of the step
    (0: none), t_peak [s]: its time} of the averaged curve after the step (t > 0), bins at their centres."""
    t = (edges[:-1] + edges[1:]) / 2
    post = t > 0
    x = (mean[post] - f_before) / (f_after - f_before)
    t = t[post]
    if not (~np.isnan(x)).any():
        return dict(t_rise_10_90=np.nan, overshoot_pct=np.nan, t_peak=np.nan)
    k = np.nanargmax(x)
    return dict(t_rise_10_90=first_crossing(t, x, 0.9) - first_crossing(t, x, 0.1),
                overshoot_pct=max(x[k] - 1, 0.0) * 100, t_peak=t[k])


def capture_t50(edges, f, smooth=3):
    """Time [s] after the step at which the curve of one capture first reaches half of its own step (normalised by its
    own f_before / f_after), after a moving average over `smooth` bins; NaN when it does not. Robust against the noise
    in the tail, unlike a settling time: the capture-to-capture spread of this is the spread of the dead time (the phase
    detector sees the new reference edge anywhere within one reference period)."""
    f_before, f_after, _ = settled_value(edges, f)
    if not np.isfinite(f_after - f_before) or f_after == f_before:
        return np.nan
    x = (f - f_before) / (f_after - f_before)
    ok = ~np.isnan(x)
    kernel = np.ones(smooth)
    num = np.convolve(np.where(ok, x, 0.0), kernel, mode="same")
    den = np.convolve(ok.astype(float), kernel, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.where(den > 0, num / den, np.nan)
    t = (edges[:-1] + edges[1:]) / 2
    post = t > 0
    return first_crossing(t[post], x[post], 0.5)


def band_tol(band, step, f_after):
    """Half width [Hz] of the band `band` (an entry of SETTLE_BANDS) for a step of `step` [Hz] settling at f_after."""
    kind, value = band
    return value * abs(step) if kind == "step" else value * f_after


# ---------------------------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------------------------
class MxrLockScope:
    """The MXR058A (KeysightScopeMXR058A, opened by pll_setup.open_mxr_scope) with the acquisition calls of this script
    (single, set_trigger, read_waveform, ...); everything else is the driver's."""

    def __init__(self, scope):
        self.scope = scope

    def __getattr__(self, name):
        return getattr(self.scope, name)

    def set_trigger(self, channel, level, slope="POS", mode="NORM"):
        """Edge trigger on `channel` at `level` [V]; slope "POS" / "NEG", mode "AUTO" (free-runs) / "NORM" (waits)."""
        self.scope.set_edge_trigger(channel, level, slope={"POS": "POSitive", "NEG": "NEGative"}[slope],
                                    sweep={"AUTO": "AUTO", "NORM": "TRIGgered"}[mode])

    def set_horizontal_position(self, position):
        """Time at the screen centre relative to the trigger [s]."""
        self.scope.write(":TIMebase:POSition {:g}".format(position))

    def sample_rate(self):
        return float(self.scope.query(":ACQuire:SRATe:ANALog?"))

    def single(self, timeout=2.0):
        """One acquisition; True when it finished (triggered) within `timeout` [s], else it is stopped and False."""
        self.scope.write(":SINGle")
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not int(float(self.scope.query(":OPERegister:CONDition?"))) & 8:  # bit 3: the scope is running
                return True
            time.sleep(0.002)
        self.scope.stop()
        return False

    def read_waveform(self, channel):
        """(time [s], voltage [V]) of the last acquisition of `channel`, time 0 at the trigger."""
        return self.scope.get_waveform(channel)

    def read_valid(self, channel, query, timeout=3.0):
        """Measurement `query` (CLOCK_MEASUREMENTS) on `channel`, repeated for up to `timeout` [s] until the scope has a
        valid result; NaN if it has none."""
        t0 = time.time()
        while True:
            value = self.scope.measure(channel, query)
            if not np.isnan(value) or time.time() - t0 > timeout:
                return value
            time.sleep(0.1)


def open_scope():
    """The MXR058A over LAN (pll_setup.open_mxr_scope): PAD_CH 50 Ohm (DC), SYNC_CH 1 MOhm, reset."""
    return MxrLockScope(pll_setup.open_mxr_scope())


def setup_capture(scope, f_pad, window, pre):
    """Scope on the pad (expected at `f_pad` [Hz]) of a locked PLL, without FSK: a fixed view for the pad
    (PAD_VIEW), then refined to what arrives (fit_to_signal); then only PAD_CH and SYNC_CH on, the window `window` [s]
    with `pre` of it before the trigger, the scope's automatic sample rate. Returns {pad_f_meas [Hz], pad_vpp
    [V]: the scope's own reading of the pad before the window is set (NaN: none), sample_rate [Sa/s]}. The trigger is
    set per slope (set_trigger).
    No autoscale: on 2026-11-09 it left CH1 at a few mV/div, the 1.8 V pad clipped (read as 23 mV) and the Sync output
    on CH4 (37.5 MHz, 3 V, while not hopping) coupled in."""
    for ch in range(1, 9):
        if ch not in (PAD_CH, SYNC_CH):
            scope.channel_off(ch)
    scale, offset = PAD_VIEW
    scope.set_channel(PAD_CH, scale=scale, offset=offset, impedance=50)
    scope.set_bandwidth("MAX")  # no bandwidth limit
    scope.set_timebase(5 / f_pad / 10)
    scope.set_edge_trigger(PAD_CH, level=offset)  # auto mode: the pad is acquired without the Sync output
    scope.run()
    time.sleep(1.0)
    if not scope.fit_to_signal(PAD_CH, n_periods=5, min_vpp=PAD_MIN_VPP):
        scope.set_channel(PAD_CH, scale=scale, offset=offset, impedance=50)  # back to the fixed view for the readings
        time.sleep(1.0)
    pad = dict(pad_f_meas=scope.read_valid(PAD_CH, CLOCK_MEASUREMENTS["freq"]),
               pad_vpp=scope.read_valid(PAD_CH, CLOCK_MEASUREMENTS["vpp"]))
    if PAD_RECORD_S:
        long_pad_record(scope)  # on its own timebase: before the capture window is set
    scope.set_channel(SYNC_CH, scale=1.0, offset=1.5, impedance=1e6)
    scope.set_timebase(window / 10)
    scope.set_horizontal_position(window / 2 - pre * window)  # the trigger at `pre` of the window
    # sample rate and record length: the scope's automatic ones (16 GSa/s, window x rate samples), read back below
    rate = scope.sample_rate()
    if rate < MIN_SAMPLE_RATE:
        logging.warning("Sample rate %.0f MSa/s below %.0f MSa/s: the crossings are coarse", rate / 1e6,
                        MIN_SAMPLE_RATE / 1e6)
    check = record_check(scope)
    vpp_rec = check.pop("pad_vpp_rec")
    if np.isnan(pad["pad_vpp"]):  # the scope's VPP readout can stay invalid: use the record's
        logging.warning("Scope VPP readout invalid, using the record's %.3f Vpp", vpp_rec)
        pad["pad_vpp"] = vpp_rec
    pad.update(check)
    save_pad_record()
    return dict(pad, sample_rate=rate)


def record_check(scope):
    """The pad from one free-running record of the capture window (the same analysis as the captures, not the
    scope's FREQ readout, which here sees only ~5 periods: 28.7 and 31.7 MHz for a 30 MHz pad, 2026-11-09):
    {pad_f_rec [Hz]: crossings over the whole record, pad_vpp_rec [V]: its peak-to-peak, pad_f_rec_spread [Hz]: max - min of its 1 us averages
    (wide: the pad frequency wanders, e.g. not really locked)}; NaN when no record or no clock."""
    out = dict(pad_f_rec=np.nan, pad_f_rec_spread=np.nan, pad_vpp_rec=np.nan)
    scope.set_trigger(PAD_CH, 0.0, mode="AUTO")
    if not scope.single(timeout=TRIGGER_TIMEOUT):
        return out
    t, v = scope.read_waveform(PAD_CH)
    out["pad_vpp_rec"] = np.percentile(v, 99.5) - np.percentile(v, 0.5)  # robust peak-to-peak of the record
    tc = crossing_times(t, v)
    PAD_RECORD.update(t=t, v=v)  # the short record, saved by save_pad_record
    if len(tc) < 10:
        return out
    per = np.diff(tc)
    logging.info("Pad periods over the record: mean %.4f ns, std %.1f ps, min/max %.3f / %.3f ns, mean(even) - "
                 "mean(odd) %.1f ps, %d crossings, %d samples at %.1f ps", per.mean() * 1e9, per.std() * 1e12,
                 per.min() * 1e9, per.max() * 1e9, (per[0::2].mean() - per[1::2].mean()) * 1e12, len(tc), len(t),
                 (t[1] - t[0]) * 1e12)
    edges = np.arange(tc[0], tc[-1], 1e-6)
    f = np.diff(np.interp(edges, tc, np.arange(len(tc)))) / np.diff(edges)
    out.update(pad_f_rec=(len(tc) - 1) / (tc[-1] - tc[0]),
               pad_f_rec_spread=np.max(f) - np.min(f) if len(f) else np.nan)
    return out


def long_pad_record(scope, length=PAD_RECORD_S):
    """One free-running record of `length` [s] of the pad (PLL locked, no FSK) and the rising / falling crossing times
    of it, kept in PAD_RECORD (rise, fall: crossing times [s]; save_pad_record writes them with the short record of
    record_check) for the notebook's period histograms. Logs the period statistics of each edge type. Leaves the scope on the timebase of `length`; setup_capture sets the capture window after it."""
    scope.set_timebase(length / 10)
    scope.set_trigger(PAD_CH, 0.0, mode="AUTO")
    if not scope.single(timeout=max(TRIGGER_TIMEOUT, 10 * length)):
        logging.warning("No long pad record")
        return
    t, v = scope.read_waveform(PAD_CH)
    lo, hi = np.percentile(v, [5, 95])
    mid = (lo + hi) / 2
    edges = {}
    for name, a, b in (("rise", v[:-1] < mid, v[1:] >= mid), ("fall", v[:-1] >= mid, v[1:] < mid)):
        i = np.flatnonzero(a & b)
        tc = t[i] + (mid - v[i]) / (v[i + 1] - v[i]) * (t[i + 1] - t[i])
        gap = 0.5 * np.median(np.diff(tc)) if len(tc) > 2 else 0.0
        keep = [0]
        for k in range(1, len(tc)):
            if tc[k] - tc[keep[-1]] >= gap:
                keep.append(k)
        edges[name] = tc[keep]
        per = np.diff(edges[name])
        if len(per):
            logging.info("Long pad record (%.0f us, %d samples), %s to %s: %d periods, mean %.4f ns, std %.1f ps, "
                         "min/max %.3f / %.3f ns", length * 1e6, len(t), name, name, len(per), per.mean() * 1e9,
                         per.std() * 1e12, per.min() * 1e9, per.max() * 1e9)
    PAD_RECORD.update(rise=edges["rise"], fall=edges["fall"])


def save_pad_record():
    """RESULTS_DIR / PAD_RECORD_FILE from PAD_RECORD: the short record (t, v) of record_check and the crossing times
    (rise, fall) of the long one."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RESULTS_DIR / PAD_RECORD_FILE, **PAD_RECORD)


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
        if PICKUP_CORRECTION:
            tc = remove_pickup(tc, pickup_periods(total_div))
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
    fields.update(step_shape(edges, mean, f_before, f_after))
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
    t50 = np.array([capture_t50(edges, f) for f in curves])
    fields.update(t50_capt_median=np.nanmedian(t50) if (~np.isnan(t50)).any() else np.nan,
                  t50_capt_std=np.nanstd(t50) if (~np.isnan(t50)).any() else np.nan,
                  t50_capt=" ".join("%.4g" % x for x in t50))
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
                f_hop=f_hop, step_rel=step_rel, fsk_rate=fsk_rate, f_vco=f_vco, window=window, pre=PRE, bin_s=point.get("bin_s", np.nan),
                n_captures=n_captures, status="error")
    rows, traces = [], []
    try:
        if point.get("vdd") is not None:
            supply.set(point["vdd"])
        cfg, fields = point_cfg(lut, point)
        base.update(fields)
        fg.fsk_off(1)
        pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50, fg=fg, shape=REF_SHAPE)
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
        bin_s = base["bin_s"] = point.get("bin_s", default_bin(base["f_pad"], base["total_div"]))
        n_pre = int(round(PRE * window / bin_s))
        n_post = int(round((1 - PRE) * window / bin_s)) - 1  # one bin short of the record end
        edges = np.arange(-n_pre, n_post + 1) * bin_s
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
                             "rise 10-90 %% %.1f ns, overshoot %.1f %% at %.1f ns; settled to 10 / 5 / 2 / 1 %% of the "
                             "step in %.1f / %.1f / %.1f / %.1f ns, 1000 / 100 ppm in %.1f / %.1f ns (per capture "
                             "10 %%: %.1f +- %.1f ns; 50 %% crossing per capture: %.1f +- %.1f ns): %s", label, row["direction"], len(curves), n_captures,
                             row["f_before"] / 1e6, row["f_after"] / 1e6, step_expected / 1e6, row["noise_ppm"],
                             row["t_rise_10_90"] * 1e9, row["overshoot_pct"], row["t_peak"] * 1e9,
                             *(row["t_settle_" + b] * 1e9 for b in SETTLE_BANDS),
                             row["t_settle_10pct_capt_median"] * 1e9, row["t_settle_10pct_capt_std"] * 1e9,
                             row["t50_capt_median"] * 1e9, row["t50_capt_std"] * 1e9, row["status"])
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
            label = "%d/%d %.3f GHz %s, step %.0f %%%s" % (
                i, len(points), point["f_vco"] / 1e9,
                "%.2f V" % point["vdd"] if point.get("vdd") is not None else "nominal",
                100 * point.get("step_rel", STEP_REL), " (%s)" % point["tag"] if point.get("tag") else "")
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
        pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50, fg=fg, shape=REF_SHAPE)
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
        # No E36312A for now (2026-11-09): the PLL supply stays as it is, the points must have vdd None
        supply = None
        # Manual debug: lock at 4.8 GHz and wait (Enter), then hop (Enter); the scope is left to you
        # debug_hold()
        # The lock-time number (DATA_POINTS): 5 % step, 1000 captures per slope, 5 us window
        lock_time_sweep(supply, DATA_POINTS)
        # 4.8 GHz (LOCK_CODES, LOCK_FILTER) at the nominal supply, N_CAPTURES per slope (~3 min)
        # lock_time_sweep(supply, LOCK_POINTS)
        # Quick check of the setup: lock_time_sweep(supply, QUICK_POINTS)


if __name__ == "__main__":
    main()

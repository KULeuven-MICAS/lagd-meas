# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Jitter in the time domain on the Keysight MXR058A (lib/lab_instruments/drivers/keysight_scope_mxr058a.py): the PLL
# locked at the lowest VCO frequency it locks at, the VCO brought straight out (pll_clk_o_en = 1, set_div_freq 0: pad =
# f_vco) into a 50 Ohm scope input. The lowest lock on record is 509.6 MHz (pll_range_S5_20261013_160525, default
# filter, |Kvco| 2 GHz/V; nothing locked at 454 MHz and below), just above the scope's 500 MHz bandwidth: the clock
# arrives as a near-sine, which is fine for edge timing.
#   1. find_lowest_lock: the VCO frequencies of F_VCO_SEARCH upwards (codes from the lookup table for |Kvco| `kvco`,
#      reference f_vco / FB_DIV from the 33600A), the first one whose lock bit is set and whose clock the scope
#      measures at f_vco / total_div (a "lock" on a wrong frequency is skipped);
#   2. N_ACQUISITIONS long records (RECORD_POINTS at SAMPLE_RATE, ~0.6 ms each) analysed here (edge_times,
#      analyse_edges): rising-edge times at the middle level (linear interpolation between samples), per record the
#      period jitter, cycle-to-cycle jitter and TIE (edge times minus the straight line through them: the mean
#      frequency removed), the TIE also over JITTER_BAND (the band of the spectrum analyzer comparisons) and a Gaussian
#      fitted to the TIE histogram (gauss_fit: a parabola through ln(counts) of the bins above 5 % of the peak). A
#      fitted sigma close to the RMS and an excess kurtosis near 0 mean random jitter; spurs (deterministic jitter)
#      flatten the histogram (negative kurtosis, RMS above the fitted sigma);
#   3. the scope's own statistics over every edge for SCOPE_ACCUMULATE s (jitter_statistics: period, and cycle-to-cycle
#      / TIE with its jitter histogram if the scope has the EZJIT option), plus a screenshot.
# The scope adds its own jitter (sample clock, vertical noise / edge slope): a few hundred fs, far below the ~10-100 ps
# of the PLL. A record of T s sees the TIE above ~1/T (~1.6 kHz for 0.6 ms).
#
# Results:
#   results/pll/pll_td_<sample>_<stamp>.csv         one row per record + one row "all" (every record together, and
#                                                   the scope's own statistics)
#   results/pll/pll_td_<sample>_<stamp>_hist.csv    TIE and period histograms of all records with the fitted Gaussian
#   results/pll/pll_td_<sample>_<stamp>_wave.csv    the first WAVE_PERIODS periods of the first record (t, v)
#   results/pll/pll_td_<sample>_<stamp>_edges.npz   per record the edge times, periods and TIE [s]
#   results/pll/pll_td_<sample>_<stamp>.png         scope screenshot (with its jitter histogram when available)
#
# Tests:
#   measure_td(sample)                        # lowest lock, straight out
#   measure_td(sample, f_vcos=(760e6,))       # one given VCO frequency
#

import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.lab_instruments.drivers.keysight_scope_mxr058a import CLOCK_MEASUREMENTS, JITTER_MEASUREMENTS, STAT_FIELDS
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8, DEFAULT_FILTER, FILTER_FIELDS
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows, kvco_target_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

SCOPE_CH = 1  # scope input the pad cable goes into (set to 50 Ohm)
# VCO frequencies find_lowest_lock tries, upwards: 460-800 MHz in 10 MHz steps (lowest lock on record 509.6 MHz)
F_VCO_SEARCH = tuple(np.arange(460e6, 800.1e6, 10e6))
KVCO = 2e9  # |Kvco| requested from the lookup table [Hz/V], as in the range sweep that locked at 509.6 MHz
SET_DIV_FREQ = 0  # divider inside the PLL: 0 = the VCO straight out
LOCK_TIMEOUT = 3.0  # [s]
FREQ_TOLERANCE = 1e-3  # relative deviation of the scope's frequency from f_vco / total_div accepted as locked
SAMPLE_RATE = 16e9  # [Sa/s], the MXR058A maximum
RECORD_POINTS = 10000000  # samples per record: 0.625 ms at SAMPLE_RATE
N_ACQUISITIONS = 5  # records analysed here
JITTER_BAND = (10e3, 10e6)  # [Hz] band of the band-limited TIE (as pll_battery.ipynb JITTER_BAND)
SCOPE_WINDOW = 1e-6  # [s/div] timebase for the scope's own statistics (10 us per acquisition)
SCOPE_ACCUMULATE = 10.0  # [s] of acquisitions the scope's statistics run over
N_BINS = 101  # histogram bins
WAVE_PERIODS = 20  # periods of the first record kept in _wave.csv
# Starting vertical setting before the fit: 0.1 V/div around 0.3 V (as pll_waveform.py)
START_SCALE, START_OFFSET = 0.1, 0.3

STATS = ("std", "pkpk", "robust_sigma", "gauss_mu", "gauss_sigma", "excess_kurtosis")
RESULT_COLUMNS = (["time", "record", "lut_csv", "f_vco", "f_ref", "kvco_target"] + list(vco_lut.LUT_FIELDS)
                  + list(FILTER_FIELDS) + ["vctrl_pred", "kvco_pred", "set_div_freq", "total_div", "f_pad", "locked",
                                           "locked_end", "sample_interval", "n_samples", "n_edges", "f_meas",
                                           "period_mean"]
                  + ["period_" + s for s in STATS] + ["ctc_std", "ctc_pkpk"] + ["tie_" + s for s in STATS]
                  + ["tie_band_rms", "jitter_band"] + list(CLOCK_MEASUREMENTS)
                  + ["scope_{}_{}".format(k, s) for k in JITTER_MEASUREMENTS for s in STAT_FIELDS]
                  + ["scope_results", "screenshot", "status"])
HIST_COLUMNS = ["kind", "bin_center", "count", "gauss"]
WAVE_COLUMNS = ["t", "v"]


def vco_config(lut, f_vco, kvco, loop_filter, set_div_freq):
    """Config locking the PLL at `f_vco` [Hz]: VCO codes from `lut` for |Kvco| `kvco`, `loop_filter`, the PLL output
    on the pad through the internal divider 2**set_div_freq. Returns (cfg, operating point {vctrl_pred, kvco_pred},
    |Kvco| requested, total division). Raises ValueError when the table has no setting for f_vco."""
    target, _, _ = kvco_target_for(lut, f_vco, kvco)
    cfg = lut.update_config(dict(CFG_REF8, **loop_filter, pll_clk_o_en=1), f_vco, target)
    cfg["set_div_freq"] = set_div_freq
    _, total_div = calculate_div_factor(cfg)
    return cfg, lut.predict(cfg, f_vco), target, total_div


def view_clock(scope, channel, f_pad):
    """Scope on `channel` (50 Ohm) at a fixed view for a clock at `f_pad` [Hz], then fitted to what arrives (vertical
    scale, offset, trigger at the middle). Returns True when the scope found a clock."""
    scope.set_channel(channel, scale=START_SCALE, offset=START_OFFSET, impedance=50)
    scope.set_timebase(5 / f_pad / 10)
    scope.set_edge_trigger(channel, level=START_OFFSET)
    scope.run()
    time.sleep(0.5)
    return scope.fit_to_signal(channel, n_periods=5)


def find_lowest_lock(f_vcos, lut, kvco, loop_filter, set_div_freq, fg, pll, scope, channel):
    """The lowest VCO frequency of `f_vcos` [Hz] (tried upwards) where the PLL locks and the scope measures the clock
    at f_vco / total_div (within FREQ_TOLERANCE). Leaves the PLL locked there (reference on `fg`, config on `pll`).
    Returns (f_vco, cfg, operating point, |Kvco| requested, total division); raises RuntimeError when none locks."""
    for f_vco in sorted(f_vcos):
        try:
            cfg, op, target, total_div = vco_config(lut, f_vco, kvco, loop_filter, set_div_freq)
        except ValueError as e:
            logging.info("%.1f MHz: no VCO setting (%s), skipped", f_vco / 1e6, e)
            continue
        f_pad = f_vco / total_div
        pll_setup.start_reference(f_vco / FB_DIV, vpp=1.8, channel=1, load=50, fg=fg)
        pll_setup.load_config(pll, cfg)
        if not pll.wait_lock(timeout=LOCK_TIMEOUT):
            logging.info("%.1f MHz: not locked", f_vco / 1e6)
            continue
        f_meas = scope.measure(channel, CLOCK_MEASUREMENTS["freq"]) if view_clock(scope, channel, f_pad) else np.nan
        if not abs(f_meas / f_pad - 1) < FREQ_TOLERANCE:
            logging.info("%.1f MHz: lock bit set but the scope measures %.4f MHz instead of %.4f MHz, skipped",
                         f_vco / 1e6, f_meas / 1e6, f_pad / 1e6)
            continue
        logging.info("Lowest lock: %.1f MHz (pad %.4f MHz, scope %.4f MHz)", f_vco / 1e6, f_pad / 1e6, f_meas / 1e6)
        return f_vco, cfg, op, target, total_div
    raise RuntimeError("No lock at any of %s MHz" % ", ".join("%.0f" % (f / 1e6) for f in sorted(f_vcos)))


def edge_times(t, v):
    """Rising-edge times [s] of the clock (t [s], v [V]) at the middle level (between the 1st and 99th percentile),
    linearly interpolated between the samples around each crossing; crossings closer than a third of the median
    spacing (noise around the threshold) are dropped."""
    level = (np.percentile(v, 1) + np.percentile(v, 99)) / 2
    i = np.nonzero((v[:-1] < level) & (v[1:] >= level))[0]
    edges = t[i] + (level - v[i]) / (v[i + 1] - v[i]) * (t[i + 1] - t[i])
    if len(edges) > 2:
        keep = np.concatenate(([True], np.diff(edges) > np.median(np.diff(edges)) / 3))
        edges = edges[keep]
    return edges


def gauss_fit(x, n_bins=N_BINS):
    """Histogram of `x` in `n_bins` bins and the Gaussian fitted to it: a parabola through ln(count) of the bins with at
    least 5 % of the peak count. Returns (bin centers, counts, mu, sigma, fitted counts per bin); mu / sigma NaN when
    the fit fails (fewer than 3 such bins or no maximum)."""
    counts, bins = np.histogram(x, bins=n_bins)
    centers = (bins[:-1] + bins[1:]) / 2
    use = counts >= 0.05 * counts.max()
    if use.sum() < 3:
        return centers, counts, np.nan, np.nan, np.full(len(centers), np.nan)
    scale = np.std(x) or 1.0  # fit on normalised x for a well-conditioned polynomial
    a, b, c = np.polyfit(centers[use] / scale, np.log(counts[use]), 2)
    if a >= 0:
        return centers, counts, np.nan, np.nan, np.full(len(centers), np.nan)
    mu, sigma = -b / (2 * a) * scale, np.sqrt(-1 / (2 * a)) * scale
    fitted = np.exp(c - b ** 2 / (4 * a)) * np.exp(-(centers - mu) ** 2 / (2 * sigma ** 2))
    return centers, counts, mu, sigma, fitted


def jitter_stats(x):
    """Spread of `x` [s]: RMS about the mean, peak-peak, robust sigma (interquartile range / 1.349, insensitive to
    tails), the fitted Gaussian (gauss_fit) and the excess kurtosis (0 for a Gaussian, < 0 flattened by spurs)."""
    x = np.asarray(x, dtype=float)
    _, _, mu, sigma, _ = gauss_fit(x)
    std = np.std(x)
    q1, q3 = np.percentile(x, [25, 75])
    kurt = np.mean((x - x.mean()) ** 4) / std ** 4 - 3 if std > 0 else np.nan
    return dict(std=std, pkpk=np.ptp(x), robust_sigma=(q3 - q1) / 1.349, gauss_mu=mu, gauss_sigma=sigma,
                excess_kurtosis=kurt)


def band_rms(tie, f_edge, band=JITTER_BAND):
    """RMS [s] of the TIE (one value per edge, edges at about `f_edge` [Hz]) within `band` [Hz]: FFT, the bins outside
    the band zeroed, back. NaN when the record is too short for the band's lower edge."""
    n = len(tie)
    if n < 4 or n / f_edge < 2 / band[0]:
        return np.nan
    freq = np.fft.rfftfreq(n, d=1 / f_edge)
    spec = np.fft.rfft(tie - np.mean(tie))
    spec[(freq < band[0]) | (freq > band[1])] = 0
    return np.std(np.fft.irfft(spec, n))


def analyse_edges(edges, f_pad):
    """Period, cycle-to-cycle and TIE jitter of one record's edge times [s]. Returns (stats dict with the
    RESULT_COLUMNS names, periods, TIE)."""
    n = np.arange(len(edges))
    tie = edges - np.polyval(np.polyfit(n, edges, 1), n)  # minus the straight line: the mean frequency removed
    periods = np.diff(edges)
    ctc = np.diff(periods)
    row = dict(n_edges=len(edges), period_mean=periods.mean(), f_meas=1 / periods.mean(),
               ctc_std=np.std(ctc), ctc_pkpk=np.ptp(ctc), tie_band_rms=band_rms(tie, f_pad),
               jitter_band="%g-%g Hz" % JITTER_BAND)
    row.update({"period_" + k: v for k, v in jitter_stats(periods).items()})
    row.update({"tie_" + k: v for k, v in jitter_stats(tie).items()})
    return row, periods, tie


def log_jitter(label, row):
    logging.info("%s: %d edges, %.4f MHz; period %.2f ps RMS (Gauss %.2f ps), cycle-cycle %.2f ps RMS, TIE %.2f ps "
                 "RMS / %.1f ps pk-pk (Gauss %.2f ps, robust %.2f ps, excess kurtosis %.2f), TIE %s %.2f ps RMS",
                 label, row["n_edges"], row["f_meas"] / 1e6, row["period_std"] * 1e12,
                 row["period_gauss_sigma"] * 1e12, row["ctc_std"] * 1e12, row["tie_std"] * 1e12,
                 row["tie_pkpk"] * 1e12, row["tie_gauss_sigma"] * 1e12, row["tie_robust_sigma"] * 1e12,
                 row["tie_excess_kurtosis"], row["jitter_band"], row["tie_band_rms"] * 1e12)


def measure_td(sample=None, f_vcos=F_VCO_SEARCH, kvco=KVCO, loop_filter=DEFAULT_FILTER, set_div_freq=SET_DIV_FREQ,
               n_acquisitions=N_ACQUISITIONS, record_points=RECORD_POINTS, channel=SCOPE_CH, lut=None):
    """Lock the PLL at the lowest of `f_vcos` [Hz] that locks (find_lowest_lock), the pad clock (VCO / 2**set_div_freq)
    on the MXR058A (50 Ohm input `channel`): `n_acquisitions` records of `record_points` samples analysed here, then the
    scope's own jitter statistics and a screenshot. The reference and the FPGA link are closed at the end, also on an
    error. `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`. Returns the CSV path."""
    lut = lut or vco_lut.VcoLUT(sample=sample)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_td_{}_{}.csv".format(sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))
    stem = csv_path.with_name(csv_path.stem)
    fg = pll = scope = None
    try:
        fg = pll_setup.open_reference_generator()
        pll = pll_setup.connect()  # one link; every tried frequency loads its own config on it
        scope = pll_setup.open_mxr_scope()
        scope.set_bandwidth("MAX")
        f_vco, cfg, op, target, total_div = find_lowest_lock(f_vcos, lut, kvco, loop_filter, set_div_freq, fg, pll,
                                                             scope, channel)
        f_pad = f_vco / total_div
        base = dict(lut_csv=lut.path.name, f_vco=f_vco, f_ref=f_vco / FB_DIV, kvco_target=target,
                    set_div_freq=set_div_freq, total_div=total_div, f_pad=f_pad, locked=1, **vco_lut.vco_codes(cfg),
                    **{k: cfg[k] for k in FILTER_FIELDS}, **op)

        # Long records: the whole record on screen, so the waveform holds record_points samples
        scope.set_acquisition(sample_rate=SAMPLE_RATE, points=record_points)
        scope.set_timebase(record_points / SAMPLE_RATE / 10)
        rows, all_periods, all_tie, arrays = [], [], [], {}
        for k in range(1, n_acquisitions + 1):
            scope.digitize(channel)
            t, v = scope.get_waveform(channel)
            edges = edge_times(t, v)
            row, periods, tie = analyse_edges(edges, f_pad)
            row.update(base, time=datetime.now().isoformat(timespec="seconds"), record=k, n_samples=len(t),
                       sample_interval=t[1] - t[0], status="ok")
            log_jitter("record %d/%d" % (k, n_acquisitions), row)
            rows.append(row)
            all_periods.append(periods)
            all_tie.append(tie)
            arrays.update({"edges_%d" % k: edges, "periods_%d" % k: periods, "tie_%d" % k: tie})
            if k == 1:
                n_wave = int(min(len(t), WAVE_PERIODS / f_pad / (t[1] - t[0])))
                append_rows(stem.with_name(stem.name + "_wave.csv"), WAVE_COLUMNS,
                            [dict(t=ti, v=vi) for ti, vi in zip(t[:n_wave], v[:n_wave])])
        np.savez_compressed(str(stem.with_name(stem.name + "_edges.npz")), **arrays)

        # Every record together: the TIE of each record is about its own line, so they can be pooled
        periods, tie = np.concatenate(all_periods), np.concatenate(all_tie)
        ctc = np.concatenate([np.diff(p) for p in all_periods])
        total = dict(base, time=datetime.now().isoformat(timespec="seconds"), record="all",
                     n_edges=sum(r["n_edges"] for r in rows), period_mean=periods.mean(), f_meas=1 / periods.mean(),
                     ctc_std=np.std(ctc), ctc_pkpk=np.ptp(ctc),
                     tie_band_rms=np.sqrt(np.mean([r["tie_band_rms"] ** 2 for r in rows])),
                     jitter_band=rows[0]["jitter_band"], sample_interval=rows[0]["sample_interval"],
                     n_samples=sum(r["n_samples"] for r in rows))
        total.update({"period_" + k: v for k, v in jitter_stats(periods).items()})
        total.update({"tie_" + k: v for k, v in jitter_stats(tie).items()})
        hist = []
        for kind, x in (("tie", tie), ("period", periods)):
            centers, counts, _, _, fitted = gauss_fit(x)
            hist += [dict(kind=kind, bin_center=c, count=n, gauss=g) for c, n, g in zip(centers, counts, fitted)]
        append_rows(stem.with_name(stem.name + "_hist.csv"), HIST_COLUMNS, hist)
        log_jitter("all %d records" % n_acquisitions, total)

        # The scope's own view: clock measurements, jitter statistics over every edge, screenshot
        scope.set_acquisition(sample_rate=SAMPLE_RATE, points="AUTO")
        scope.set_timebase(SCOPE_WINDOW)
        scope.digitize(channel)
        total.update(scope.measure_clock(channel))
        scope_stats = scope.jitter_statistics(channel, SCOPE_ACCUMULATE)
        total.update({"scope_" + k: v for k, v in scope_stats.items() if k != "scope_results"},
                     scope_results=scope_stats["scope_results"])
        png = stem.with_name(stem.name + ".png")
        scope.screenshot(png)
        total.update(screenshot=png.name, locked_end=int(pll.read_lock() == 1), status="ok")
        if not total["locked_end"]:
            logging.warning("The PLL lost lock during the measurement")
        append_rows(csv_path, RESULT_COLUMNS, rows + [total])
    except pyvisa.VisaIOError:
        raise  # instrument connection lost: stop, outputs off in the finally block below
    finally:
        if scope is not None:
            scope.close()
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
    logging.info("Time-domain jitter written to %s", csv_path)
    return csv_path


def start_log_file():
    """Also write the log to results/logs/pll_td_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_td_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():  # core in reset: no pollution
        # Lowest lock (expected ~510 MHz), VCO straight out into the MXR058A CH1 (50 Ohm), 5 records of 0.6 ms
        measure_td(sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

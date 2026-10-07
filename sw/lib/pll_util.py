# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

# Various utility functions for the PLL measurements

import numpy as np

def     calculate_integrated_jitter(fc, offsets, L_f):
    """
    Calculates the integrated RMS jitter from discrete phase noise measurements.

    Parameters:
    fc (float): Carrier frequency of the clock signal in Hz.
    offsets (array-like): Offset frequencies from the carrier in Hz.
    L_f (array-like): Single-sideband phase noise at the given offsets in dBc/Hz.

    Returns:
    tuple: (rms_time_jitter_seconds, rms_phase_jitter_radians)
    """
    offsets = np.array(offsets, dtype=float)
    L_f = np.array(L_f, dtype=float)

    if len(offsets) != len(L_f):
        raise ValueError("Offsets and phase noise arrays must be the same length.")

    if np.any(offsets <= 0):
        raise ValueError("Offset frequencies must be strictly greater than zero.")

    total_integral = 0.0

    # Iterate through adjacent pairs of measurement points
    for i in range(len(offsets) - 1):
        f1, f2 = offsets[i], offsets[i+1]
        L1, L2 = L_f[i], L_f[i+1]

        # Slope of the log-log segment (dB / decade)
        slope = (L2 - L1) / (np.log10(f2) - np.log10(f1))
        a = slope / 10.0

        # Linear power at the start of the interval
        P1 = 10.0 ** (L1 / 10.0)

        # Integrate the power-law profile over the interval
        if np.isclose(a, -1.0):
            A = P1 * f1 * np.log(f2 / f1)
        else:
            A = P1 * f1 * ((f2 / f1)**(a + 1.0) - 1.0) / (a + 1.0)

        total_integral += A

    # Double sideband phase variance (multiply by 2)
    phi_variance = 2.0 * total_integral

    # RMS Phase Jitter (in radians)
    rms_phase_radians = np.sqrt(phi_variance)

    # RMS Time Jitter (in seconds)
    rms_time_seconds = rms_phase_radians / (2.0 * np.pi * fc)

    return rms_time_seconds, rms_phase_radians


# Trace-based phase noise: the analyzer trace is the power in the RBW filter. The measurements take it with the RMS
# detector and power averaging (true noise power, no correction). ENBW_FACTOR: noise bandwidth / RBW of the analyzer's
# Gaussian RBW filter. LOG_AVG_CORR_DB: only for traces averaged as dB values (log / video averaging), which read noise
# 2.51 dB low (Rayleigh statistics). Compare the trace result with the marker values at the same offsets to check.
ENBW_FACTOR = 1.065
LOG_AVG_CORR_DB = 2.51


def phase_noise_from_traces(traces, offsets, enbw_factor=ENBW_FACTOR, log_avg_corr_db=0.0, min_rbw_offset=10.0):
    """Single-sideband phase noise L(f) [dBc/Hz] from analyzer traces centered on the carrier.

    traces: list of {'center', 'rbw', 'freq', 'level'} (dBm), e.g. one per span from
        RohdeSchwarzFSVSpectrum.measure_phase_noise_profile(..., traces=[]). Each trace covers the offset band
        from the previous trace's top offset (or offsets[0]) up to the highest offset in `offsets` it can show
        (< half its span), so narrow spans (small RBW) cover the close-in part.
    offsets: the integration limits / marker offsets [Hz] (sorted).
    Per trace: carrier = trace maximum; L = mean of both sidebands (linear) - carrier - 10 log10(ENBW)
        + log_avg_corr_db; points closer than `min_rbw_offset` * RBW to the carrier are skipped.
    log_avg_corr_db: 0 for power-averaged traces (the default measurement); LOG_AVG_CORR_DB for log-averaged ones.

    Returns (offset [Hz], L [dBc/Hz]) arrays, sorted, from offsets[0] to offsets[-1].
    """
    offsets = sorted(offsets)
    out_f, out_l = [], []
    lo = offsets[0]
    for t in sorted(traces, key=lambda t: (max(t["freq"]) - min(t["freq"]))):
        f = np.asarray(t["freq"], dtype=float) - t["center"]
        p = np.asarray(t["level"], dtype=float)
        half_span = (f.max() - f.min()) / 2
        covered = [o for o in offsets if o < half_span]
        if not covered or covered[-1] <= lo:
            continue
        hi = covered[-1]
        p_carrier = p.max()
        up = (f >= max(lo, min_rbw_offset * t["rbw"])) & (f <= hi)
        o = f[up]
        lsb = np.interp(-o, f, p)  # lower sideband at the same offsets (f is increasing)
        p_ssb = 10 * np.log10((10 ** (p[up] / 10) + 10 ** (lsb / 10)) / 2)
        out_f.append(o)
        out_l.append(p_ssb - p_carrier - 10 * np.log10(enbw_factor * t["rbw"]) + log_avg_corr_db)
        lo = hi
    if not out_f:
        return np.array([]), np.array([])
    f, l = np.concatenate(out_f), np.concatenate(out_l)
    order = np.argsort(f)
    return f[order], l[order]


def integrate_phase_noise(fc, offsets, L_f):
    """RMS jitter from a densely sampled L(f) [dBc/Hz] (e.g. phase_noise_from_traces): phase variance =
    2 * integral of 10^(L/10) df (trapezoid, double sideband). Returns (rms_time_jitter_s, rms_phase_rad)."""
    offsets = np.asarray(offsets, dtype=float)
    lin = 10.0 ** (np.asarray(L_f, dtype=float) / 10.0)
    phi_variance = 2.0 * np.sum((lin[1:] + lin[:-1]) / 2 * np.diff(offsets))
    rms_phase = np.sqrt(phi_variance)
    return rms_phase / (2.0 * np.pi * fc), rms_phase


def find_spurs(offsets, L_f, threshold_db=10.0, window_decades=0.2, min_points=2):
    """Discrete spurs in a densely sampled L(f) [dBc/Hz] (e.g. phase_noise_from_traces).

    The local noise floor at each point is the median of L over offsets within +-window_decades/2 (log scale);
    points more than `threshold_db` above it are spur points, and neighbouring spur points form one spur. A spur
    needs at least `min_points` points (a real tone is about as wide as the RBW: >= ~2 points at 2 sweep points per
    RBW, more at the measurements' 5 per RBW; single points are noise spikes and stay in the noise part).
    Returns (spurs, L_noise):
      spurs: list of {offset (peak) [Hz], f_lo, f_hi [Hz], peak (L at the peak) [dBc/Hz], above_floor [dB],
             power [dBc] (single sideband, integral of 10^(L/10) over the spur's points)};
      L_noise: L with the spur points replaced by the local floor (the random-noise part, for integrate_phase_noise).
    """
    f = np.asarray(offsets, dtype=float)
    l = np.asarray(L_f, dtype=float)
    logf = np.log10(f)
    floor = np.array([np.median(l[np.abs(logf - x) <= window_decades / 2]) for x in logf])
    is_spur = l > floor + threshold_db
    spurs = []
    i = 0
    while i < len(f):
        if not is_spur[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(f) and is_spur[j + 1]:
            j += 1
        if j - i + 1 < min_points:
            is_spur[i:j + 1] = False  # too narrow for a tone: noise
            i = j + 1
            continue
        lo, hi = max(i - 1, 0), min(j + 1, len(f) - 1)  # include the flanks next to the spur points
        seg = slice(lo, hi + 1)
        lin = 10.0 ** (l[seg] / 10.0)
        power = np.sum((lin[1:] + lin[:-1]) / 2 * np.diff(f[seg])) if hi > lo else lin[0]
        k = i + int(np.argmax(l[i:j + 1]))
        spurs.append(dict(offset=float(f[k]), f_lo=float(f[i]), f_hi=float(f[j]), peak=float(l[k]),
                          above_floor=float(l[k] - floor[k]), power=float(10 * np.log10(power))))
        i = j + 1
    return spurs, np.where(is_spur, floor, l)


def split_jitter(fc, offsets, L_f, **spur_kwargs):
    """RMS jitter of a dense L(f) split into the random-noise part and the spur part (find_spurs).
    Returns dict(total, noise, spur: rms time jitter [s]; total_rad, noise_rad, spur_rad [rad]; spurs: list),
    with spur = sqrt(total^2 - noise^2) (uncorrelated parts add in power)."""
    spurs, l_noise = find_spurs(offsets, L_f, **spur_kwargs)
    t_tot, p_tot = integrate_phase_noise(fc, offsets, L_f)
    t_noise, p_noise = integrate_phase_noise(fc, offsets, l_noise)
    t_spur, p_spur = (np.sqrt(max(t_tot ** 2 - t_noise ** 2, 0.0)), np.sqrt(max(p_tot ** 2 - p_noise ** 2, 0.0)))
    return dict(total=t_tot, noise=t_noise, spur=t_spur, total_rad=p_tot, noise_rad=p_noise, spur_rad=p_spur,
                spurs=spurs, L_noise=l_noise)


if __name__ == "__main__":
    carrier_freq = 37499975

    # Frequency offsets: 10 kHz, 100 kHz, 1 MHz, 10 MHz, 100 MHz
    #offsets_hz = [10e3, 100e3, 532e3, 857e3, 1e6]
    offsets_hz = [100, 1e3, 10e3, 100e3, 500e3, 1e6]

    # Phase noise in dBc/Hz at the given offsets
    #phase_noise_dBc = [-106, -105, -94]
    #phase_noise_dBc = [-106, -105, -107, -94,-95]
    #phase_noise_dBc = [-104.11, -115.6, -120.2, -119.9, -132.1, -142.4]
    phase_noise_dBc = [-103.2, -102.4, -106.9, -105.8, -100.6, -85.6]

    t_jitter, phase_jitter = calculate_integrated_jitter(
        carrier_freq,
        offsets_hz,
        phase_noise_dBc
    )

    print(f"Integration Bandwidth: {offsets_hz[0]/1e3:.0f} kHz to {offsets_hz[-1]/1e6:.0f} MHz")
    print(f"RMS Time Jitter:       {t_jitter * 1e12:.3f} ps  ({t_jitter * 1e15:.1f} fs)")
    print(f"RMS Phase Jitter:      {phase_jitter * 1e3:.3f} mrad")

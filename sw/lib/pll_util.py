# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

# Various utility functions for the PLL measurements

import numpy as np

def calculate_integrated_jitter(fc, offsets, L_f):
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


if __name__ == "__main__":
    carrier_freq = 0.1e9  # 1 GHz Clock

    # Frequency offsets: 10 kHz, 100 kHz, 1 MHz, 10 MHz, 100 MHz
    offsets_hz = [10e3, 100e3, 1e6, 10e6, 20e6]
    
    # Phase noise in dBc/Hz at the given offsets
    phase_noise_dBc = [-140, -149, -153, -156, -157.0]

    t_jitter, phase_jitter = calculate_integrated_jitter(
        carrier_freq, 
        offsets_hz, 
        phase_noise_dBc
    )

    print(f"Integration Bandwidth: {offsets_hz[0]/1e3:.0f} kHz to {offsets_hz[-1]/1e6:.0f} MHz")
    print(f"RMS Time Jitter:       {t_jitter * 1e12:.3f} ps  ({t_jitter * 1e15:.1f} fs)")
    print(f"RMS Phase Jitter:      {phase_jitter * 1e3:.3f} mrad")
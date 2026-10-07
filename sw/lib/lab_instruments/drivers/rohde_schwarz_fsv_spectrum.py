# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

import socket
import subprocess
import pyvisa
import logging
import math
import time
from typing import Union, Dict, List

from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)

# Bandwidth rules of the measurement methods: VBW = VBW_RBW_RATIO x RBW, so the video filter does (almost) no
# averaging and the trace averaging (power) does the smoothing; POINTS_PER_RBW sweep points per RBW, so the RMS bin
# around the carrier covers only the top of the RBW filter (carrier ~0.04 dB low; 2 points per RBW: ~0.26 dB).
VBW_RBW_RATIO = 3.0
POINTS_PER_RBW = 5.0


class RohdeSchwarzFSVSpectrum(inst.BaseSpectrumAnalyzer):
    """
    Class for the Rohde & Schwarz FSVA/FSV spectrum analyzer.
    Implements specific resource management and high-level compound measurement workflows.
    """
    def __init__(self, info: inst.BaseSpectrumAnalyzerData, verbose: bool = False):
       self._num_traces = 6
       self._num_markers = 16
       super().__init__(info, verbose)

    def _open_resource(self):
        """
        Open the resource for the R&S FSV spectrum analyzer.
        Utilizes the HiSLIP protocol (hislip0) as recommended by the LXI standard
        for improved performance and data transfer rates compared to inst0.
        """
        rm = pyvisa.ResourceManager()
        resource_string = f"TCPIP::{self.info.IP}::inst0::INSTR"
        logger.info(f"Reaching {self.info.name} at: {resource_string}")
        return rm.open_resource(resource_string)

    def _init_instrument(self):
        """
        Initialize the instrument to a default, clean state.
        """
        logger.info(f"Initializing {self.info.name}")
        self.write('*RST', check=False)               # Reset to default state[cite: 3]
        self.write('SYST:ERR:CLE:ALL', check=False)   # Clear the error queue
        _ = self.status()
        logger.info(f"{self.info.name} initialized successfully.")

    def center_on_fundamental(self, center_freq: float, search_span: float = 2.1e3):
        """
        Start measurement by centering on the oscillator frequency.

        Args:
            center_freq: Coarse estimate of the fundamental frequency (Hz).
            search_span: The span used to search for the exact peak (Hz).
        """
        logger.info(f"[{self.info.name}] Centering on fundamental frequency near {center_freq} Hz...")

        # Initial coarse centering
        self.set_center_frequency(center_freq)

        # Prepare for the search
        self.set_sweep_mode(continuous=False)
        self.set_trace_mode(trace=1, mode='WRITe')
        self.set_rbw(1.0)
        self.set_vbw(1.0)
        self.set_span(search_span)
        self.set_display_range(150.0)

        # Execute sweep and wait for completion
        logger.info("Triggering single sweep for peak search...")
        self.trigger_single_sweep(wait=True)
        logger.info("Sweep complete")

        # Find exact peak and set as new center and reference level
        self.peak_search(marker=1)
        self.marker_to_reference_level(marker=1)
        self.marker_to_center(marker=1)

    def set_display_update(self, on: bool = True):
        """Keep the screen updating while under remote control (pyvisa-py over LAN cannot send go-to-local;
        press LOCAL on the front panel to take over)."""
        self.write(f'SYST:DISP:UPD {"ON" if on else "OFF"}')

    def _close(self):
        """Release the VISA session (the analyzer has no outputs to switch off)."""
        self.tool.close()
        self.tool = None

    def get_trace(self, trace: int = 1) -> Dict[str, List[float]]:
        """
        Read a full trace as displayed (all sweep points, in the current unit, e.g. dBm).

        The trace data has no x values: the sweep points are spread evenly over center +- span / 2.

        Returns:
            Dictionary with 'center', 'span', 'rbw', 'vbw' (Hz) and the lists 'freq' (Hz) and 'level'.
        """
        trace = self._validate_trace(trace)
        self.write('FORM ASC')
        level = [float(x) for x in self.query(f'TRAC:DATA? TRACE{trace}').strip().split(',')]
        center = float(self.query('FREQ:CENT?').strip())
        span = float(self.query('FREQ:SPAN?').strip())
        rbw = float(self.query('BAND:RES?').strip())
        vbw = float(self.query('BAND:VID?').strip())
        n = len(level)
        freq = [center - span / 2 + span * i / (n - 1) for i in range(n)] if n > 1 else [center]
        return {'center': center, 'span': span, 'rbw': rbw, 'vbw': vbw, 'freq': freq, 'level': level}

    @staticmethod
    def snap_bandwidth(bw: float) -> float:
        """Largest analyzer RBW/VBW setting (1-2-3-5 steps, >= 1 Hz) not above `bw` [Hz]."""
        steps = [m * 10 ** e for e in range(0, 8) for m in (1, 2, 3, 5)]
        return max([s for s in steps if s <= bw] or [1.0])

    def set_detector(self, detector: str, trace: int = 1):
        """Trace detector: how the readings inside one trace point become its value: 'RMS' (true average power,
        the right one for noise), 'SAMPle', 'POSitive' (max peak), 'NEGative', 'AVERage' (voltage), 'APEak'
        (auto peak, the default)."""
        trace = self._validate_trace(trace)
        self.write(f'DET{trace}:FUNC {detector}')

    def set_average_type(self, average_type: str):
        """How trace averaging (trace mode AVERage) combines the sweeps: 'POWer' (linear power, unbiased for noise)
        or 'VIDeo' / 'LOGarithmic' (averages the dB values: noise reads 2.51 dB low). The accepted keywords
        differ between R&S models: a wrong one raises the instrument error from write()."""
        self.write(f'AVER:TYPE {average_type}')

    def get_detector(self, trace: int = 1) -> str:
        """Trace detector as the analyzer reports it (e.g. 'RMS', 'SAMP', 'APE')."""
        trace = self._validate_trace(trace)
        return self.query(f'DET{trace}:FUNC?').strip()

    def get_average_type(self) -> str:
        """Trace averaging type as the analyzer reports it (e.g. 'POW', 'VID', 'LOG')."""
        return self.query('AVER:TYPE?').strip()

    def set_video_filter_type(self, kind: str):
        """Where the video filter acts: 'LINear' (on the linear power, so any video filtering averages power) or
        'LOGarithmic' (on the dB values: noise reads low when VBW < RBW)."""
        self.write(f'BAND:VID:TYPE {kind}')

    def get_video_filter_type(self) -> str:
        """Video filter type as the analyzer reports it (e.g. 'LIN', 'LOG')."""
        return self.query('BAND:VID:TYPE?').strip()

    def set_bandwidths_auto(self):
        """RBW and VBW back to the analyzer's auto coupling (undoes a manual RBW/VBW, e.g. center_on_fundamental's)."""
        self.write('BAND:RES:AUTO ON')
        self.write('BAND:VID:AUTO ON')

    def set_sweep_points(self, points: int):
        """Number of trace points per sweep (101 .. 32001)."""
        self.write(f'SWE:POIN {int(points)}')

    def set_bandwidths_for_span(self, span: float, rbw_span_ratio: float, vbw_rbw_ratio: float = VBW_RBW_RATIO,
                                points_per_rbw: float = POINTS_PER_RBW) -> float:
        """RBW = span / `rbw_span_ratio` (snapped down), VBW = `vbw_rbw_ratio` * RBW (snapped down, so the trace
        averaging rather than the video filter does the smoothing) and at least `points_per_rbw` sweep points per
        RBW (no spectrum between points; see POINTS_PER_RBW). Returns the RBW [Hz]."""
        rbw = self.snap_bandwidth(span / rbw_span_ratio)
        self.set_rbw(rbw)
        self.set_vbw(self.snap_bandwidth(vbw_rbw_ratio * rbw))
        self.set_sweep_points(min(max(101, math.ceil(points_per_rbw * span / rbw) + 1), 32001))
        return rbw

    def averaged_trace(self, center: float, span: float, averages: int = 20, rbw: float = None,
                       vbw: float = None, rbw_span_ratio: float = None, detector: str = 'RMS',
                       average_type: str = 'POWer', video_filter: str = 'LINear') -> Dict[str, List[float]]:
        """
        One averaged spectrum: `averages` single sweeps averaged on trace 1, then read with get_trace.

        Args:
            center, span: Frequency window (Hz).
            averages: Number of sweeps averaged (trace mode AVERage).
            rbw, vbw: Resolution / video bandwidth (Hz). vbw None with rbw given: VBW_RBW_RATIO x rbw. Both None
                      (and no rbw_span_ratio): the analyzer's auto coupling for both.
            rbw_span_ratio: When given (instead of rbw/vbw), set_bandwidths_for_span(span, rbw_span_ratio).
            detector, average_type: set_detector / set_average_type before the sweeps; default RMS detector +
                                    power averaging (every trace point is the true power in the RBW, also for
                                    noise); None leaves them as they are.
            video_filter: set_video_filter_type before the sweeps (default 'LINear'); None leaves it as it is.

        Returns:
            get_trace() dictionary, plus 'averages'.
        """
        self.set_center_frequency(center)
        self.set_span(span)
        if rbw_span_ratio is not None:
            self.set_bandwidths_for_span(span, rbw_span_ratio)
        elif rbw is None and vbw is None:
            self.set_bandwidths_auto()
        if rbw is not None:
            self.set_rbw(rbw)
            if vbw is None:
                vbw = self.snap_bandwidth(VBW_RBW_RATIO * rbw)
        if vbw is not None:
            self.set_vbw(vbw)
        if detector is not None:
            self.set_detector(detector)
        if average_type is not None:
            self.set_average_type(average_type)
        if video_filter is not None:
            self.set_video_filter_type(video_filter)
        self.set_sweep_mode(continuous=False)
        self.set_sweep_count(averages)
        self.set_trace_mode(trace=1, mode='WRITe')  # clears a previous average
        self.set_trace_mode(trace=1, mode='AVERage')
        logger.info(f"[{self.info.name}] Averaging {averages} sweeps at {center} Hz center, {span} Hz span...")
        self.trigger_single_sweep(wait=True)
        trace = self.get_trace(1)
        trace['averages'] = averages
        return trace

    def get_phase_noise_marker(self, marker: int = 2) -> float:
        """Phase-noise marker function result [dBc/Hz] of a delta marker (enable_phase_noise_marker): the noise
        at the marker relative to the carrier, normalized to 1 Hz with the analyzer's own RBW / detector
        corrections."""
        marker = self._validate_marker(marker)
        return float(self.query(f'CALC:DELT{marker}:FUNC:PNO:RES?').strip())

    def measure_phase_noise_profile(self,
                                    averages: int,
                                    offset_span_map: Dict[float, float],
                                    traces: List[Dict] = None,
                                    rbw_span_ratio: float = None,
                                    detector: str = 'RMS',
                                    average_type: str = 'POWer',
                                    video_filter: str = 'LINear') -> Dict[float, float]:
        """
        Execute phase noise measurements over a set of offset frequencies

        Args:
            averages: Number of sweeps to average before taking the measurement.
            offset_span_map: Dictionary mapping target offset frequencies (Hz)
                             to the required measurement span (Hz).
                             Example: {100: 2.1e3, 1000: 2.1e3, 10000: 21e3}
            traces: Optional list; when given, the averaged trace of every span (get_trace) is appended to it.
            rbw_span_ratio: Optional; RBW, VBW and sweep points per span from set_bandwidths_for_span(span,
                            rbw_span_ratio) instead of the fixed 1 Hz / 10 Hz RBW (VBW = VBW_RBW_RATIO x RBW).
            detector, average_type: set_detector / set_average_type before the sweeps; default RMS detector +
                                    power averaging, for the markers and the traces alike (each trace point is then
                                    the true noise power in the RBW, no log-average bias); None leaves them as they
                                    are. Read back with get_detector / get_average_type to record them.
            video_filter: set_video_filter_type before the sweeps (default 'LINear'); None leaves it as it is.

        Returns:
            Dictionary mapping the evaluated offsets to their phase noise in dBc/Hz: the phase-noise marker
            function result (CALC:DELT2:FUNC:PNO:RES?, normalized to 1 Hz by the analyzer, independent of the RBW).
        """

        results = {}

        # Activate phase noise measurement
        self.set_delta_marker_state(marker=2, state=True)
        self.enable_phase_noise_marker(marker=2, state=True)

        if detector is not None:
            self.set_detector(detector)
        if average_type is not None:
            self.set_average_type(average_type)
        if video_filter is not None:
            self.set_video_filter_type(video_filter)

        # Enable trace averaging
        self.set_sweep_count(averages)
        self.set_trace_mode(trace=1, mode='AVERage')

        # Iterate through required spans and evaluate offsets
        current_span = None

        for offset, required_span in offset_span_map.items():
            logger.info(f"[{self.info.name}] Evaluating Phase Noise at {offset} Hz offset...")

            # Only trigger a new averaged sweep sequence if the span needs to change
            if required_span != current_span:
                self.set_span(required_span)

                if rbw_span_ratio is not None:
                    rbw = self.set_bandwidths_for_span(required_span, rbw_span_ratio)
                    logger.info(f"[{self.info.name}] RBW {rbw} Hz for {required_span} Hz span")
                # Dynamically adjust RBW to prevent timeout on wide spans
                else:
                    if required_span > 1e6:
                        logger.info(f"[{self.info.name}] Span > 1 MHz detected. Increasing RBW to 10 Hz.")
                    rbw = 10.0 if required_span > 1e6 else 1.0
                    self.set_rbw(rbw)
                    self.set_vbw(self.snap_bandwidth(VBW_RBW_RATIO * rbw))  # not the 1 Hz of center_on_fundamental

                # To clear the previous average buffer, toggle trace mode
                self.set_trace_mode(trace=1, mode='WRITe')
                self.set_trace_mode(trace=1, mode='AVERage')

                logger.info(f"[{self.info.name}] Acquiring {averages} sweeps at {required_span} Hz span...")
                self.trigger_single_sweep(wait=True)
                current_span = required_span
                if traces is not None:
                    traces.append(self.get_trace(1))

            # Move the marker to the specific offset frequency.
            self.set_delta_marker_x(marker=2, offset=offset)

            # Allow a brief moment for the instrument to calculate the marker function result
            time.sleep(0.1)

            # Phase noise in dBc/Hz: the phase-noise function result. (CALC:DELT2:Y? is the plain delta level in the
            # RBW; it only equals dBc/Hz at 1 Hz RBW: verified on 2026-10-05 by scaling the RBW x1..x30.)
            pno_val = self.get_phase_noise_marker(marker=2)
            results[offset] = pno_val
            logger.info(f"[{self.info.name}] Phase noise at {offset:g} Hz: {pno_val:.1f} dBc/Hz")

        return results

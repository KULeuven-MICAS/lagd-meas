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
# Overload protection (the FSW43 showed IF overload, IFOVL, with the reference level at the carrier peak): the
# reference level sets the IF gain and, with auto attenuation, the RF attenuation, so the strongest signal must stay
# below it with margin. SAFE_REF_LEVEL_DBM after the reset, before any signal level is known (the PLL pad drives up
# to ~+2 dBm); REF_LEVEL_MARGIN_DB above the carrier once center_on_fundamental has found it (covers the square
# wave's harmonics, which share the IF path). A higher reference level raises the analyzer's own noise floor a little.
SAFE_REF_LEVEL_DBM = 10.0
REF_LEVEL_MARGIN_DB = 10.0
# STATus:QUEStionable:POWer bits (FSV / FSW): 0 = RF overload (OVLD), 2 = IF overload (IFOVL)
STAT_POW_RF_OVERLOAD = 1 << 0
STAT_POW_IF_OVERLOAD = 1 << 2
# Phase Noise application (FSW option K40): name of the channel start_phase_noise_mode creates, and how many user
# spot-noise markers it has.
PNO_CHANNEL_NAME = 'Phase Noise'
PNO_MAX_SPOT_MARKERS = 5


class RohdeSchwarzFSVSpectrum(inst.BaseSpectrumAnalyzer):
    """
    Class for the Rohde & Schwarz FSVA/FSV spectrum analyzer; also used for the FSW (same SCPI for these methods).
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
        # No overload before the signal level is known: reference level with headroom, RF attenuation coupled to it
        self.set_attenuation_auto()
        self.set_reference_level(SAFE_REF_LEVEL_DBM)
        self.read_overload()  # clear the overload events of the reset
        logger.info(f"{self.info.name} initialized successfully.")

    def center_on_fundamental(self, center_freq: float, search_span: float = 2.1e3,
                              ref_margin_db: float = REF_LEVEL_MARGIN_DB):
        """
        Start measurement by centering on the oscillator frequency.

        The search sweep runs at SAFE_REF_LEVEL_DBM; afterwards the reference level is set `ref_margin_db` above the
        carrier peak (not at the peak: that drives the IF into overload), with auto attenuation.

        Args:
            center_freq: Coarse estimate of the fundamental frequency (Hz).
            search_span: The span used to search for the exact peak (Hz).
            ref_margin_db: Reference level above the carrier peak (dB).

        Returns:
            The carrier peak level (dBm) of the search sweep. Use this, not a marker read afterwards: after the move
            to center (no new sweep) the FSW43 read the marker beside the carrier at 100-125 MHz (-13..-55 dBm for a
            -1 dBm carrier, 2026-10-19).
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
        self.set_attenuation_auto()
        self.set_reference_level(SAFE_REF_LEVEL_DBM)

        # Execute sweep and wait for completion
        logger.info("Triggering single sweep for peak search...")
        self.trigger_single_sweep(wait=True)
        logger.info("Sweep complete")

        # Find exact peak and set as new center; reference level with margin above it
        self.peak_search(marker=1)
        peak_dbm = self.get_marker_y_value(marker=1)
        self.set_reference_level(math.ceil(peak_dbm + ref_margin_db))
        self.marker_to_center(marker=1)
        logger.info(f"[{self.info.name}] Carrier peak {peak_dbm:.1f} dBm -> reference level "
                    f"{math.ceil(peak_dbm + ref_margin_db):.0f} dBm, RF attenuation {self.get_attenuation():g} dB")
        return peak_dbm

    def set_attenuation_auto(self):
        """RF attenuation coupled to the reference level (the analyzer picks it so the reference level does not
        overload the mixer)."""
        self.write('INP:ATT:AUTO ON')

    def get_attenuation(self) -> float:
        """RF attenuation [dB] as set on the analyzer."""
        return float(self.query('INP:ATT?').strip())

    def read_overload(self) -> Dict[str, bool]:
        """Overloads since the previous call (STATus:QUEStionable:POWer event register, cleared by reading):
        {'rf_overload': OVLD at the RF input, 'if_overload': IFOVL in the IF path}."""
        bits = int(float(self.query('STAT:QUES:POW?').strip()))
        return {'rf_overload': bool(bits & STAT_POW_RF_OVERLOAD), 'if_overload': bool(bits & STAT_POW_IF_OVERLOAD)}

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
                # Reference of the phase-noise marker: marker 1 on the carrier of this sweep, and the function switched
                # off and on so it takes its (fixed) reference level from there. It takes the reference when it is
                # switched on; at the start above, after center_on_fundamental's move to center without a new sweep,
                # the FSW43 read marker 1 beside the carrier at 100-125 MHz (-55 instead of -1 dBm), so every marker
                # read up to ~50 dB too high (2026-10-19).
                self.peak_search(marker=1)
                self.enable_phase_noise_marker(marker=2, state=False)
                self.enable_phase_noise_marker(marker=2, state=True)
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

    # --- Phase Noise application (FSW option K40) ---
    # A separate measurement channel: the analyzer finds the carrier, sweeps the offset range in half decades with an
    # RBW proportional to the offset, and shows L(f) [dBc/Hz] against the offset on a log axis.

    def has_phase_noise_option(self) -> bool:
        """True when the analyzer has the Phase Noise application (K40 in *OPT?)."""
        options = self.query('*OPT?').strip().upper().split(',')
        return any('K40' in o for o in options)

    def start_phase_noise_mode(self, f_carrier: float, offset_start: float, offset_stop: float,
                               carrier_level_dbm: float = 0.0, freq_tolerance_hz: float = 10e3,
                               level_tolerance_db: float = 10.0, tracking: bool = True,
                               rbw_percent: float = 10.0, preset: str = 'NORMal', averages: int = None,
                               spur_removal: bool = False, spur_threshold_db: float = None,
                               continuous: bool = True):
        """
        Switch to the Phase Noise application (channel PNO_CHANNEL_NAME, created when missing) and set it up.
        Commands from the R&S FSW-K40 user manual (doc/FSW_K40_Phase_Noise_UserManual_en_31.pdf, chapter 8).

        The analyzer checks the carrier against the expected frequency and level (verification, within the
        tolerances) and, with `tracking`, follows its frequency and level drift during the measurement.

        Args:
            f_carrier: Expected carrier frequency (Hz).
            offset_start, offset_stop: Offset range of the L(f) curve (Hz).
            carrier_level_dbm: Expected carrier level (dBm).
            freq_tolerance_hz: How far the carrier may be from f_carrier (Hz).
            level_tolerance_db: How far the carrier level may be from carrier_level_dbm (dB).
            tracking: Follow the carrier's frequency and level during the sweep.
            rbw_percent: RBW as a percentage of the start offset of each half decade (1..100 %, LIST:BWID:RAT).
            preset: Measurement configuration (SWE:MODE): 'FAST', 'NORMal' (default) or 'AVERage' (best quality);
                    sets the averaging per half decade.
            averages: Trace averaging over whole sweeps (SWE:COUN; a moving average in continuous sweep); None
                      leaves the analyzer's default (200 after a reset).
            spur_removal: Remove the spurs from all traces (SPUR:SUPP): points more than `spur_threshold_db` above
                          the analyzer's sliding-median trace are replaced by the median. The spurs stay listed
                          (spur list, read_phase_noise) and drawn as vertical lines; the trace data is spur-free.
            spur_threshold_db: Spur threshold above the median trace (0..50 dB, SPUR:THR; 0 after a reset); None
                               leaves it as it is. Only set with spur_removal (the analyzer refuses it otherwise).
            continuous: Continuous sweep (live on the screen) or single sweeps (trigger_single_sweep).
        """
        if not self.has_phase_noise_option():
            raise RuntimeError(f"{self.info.name} has no Phase Noise application (K40 not in *OPT?)")
        if PNO_CHANNEL_NAME in self.query('INST:LIST?'):
            self.write(f"INST:SEL '{PNO_CHANNEL_NAME}'")
        else:
            self.write(f"INST:CRE:NEW PNOise, '{PNO_CHANNEL_NAME}'")
        # Expected carrier: frequency and level, verified within the tolerances, tracked during the sweep
        self.write(f'FREQ:CENT {f_carrier}')
        self.write('FREQ:VER:STAT ON')
        self.write(f'FREQ:VER:TOL:ABS {freq_tolerance_hz}')
        self.write(f'POW:RLEV {carrier_level_dbm}')
        self.write('POW:RLEV:VER:STAT ON')
        self.write(f'POW:RLEV:VER:TOL {level_tolerance_db}')
        self.write(f'FREQ:TRAC {"ON" if tracking else "OFF"}')
        self.write(f'POW:TRAC {"ON" if tracking else "OFF"}')
        # Offset range and RBW
        self.write(f'FREQ:STAR {offset_start}')
        self.write(f'FREQ:STOP {offset_stop}')
        self.write(f'LIST:BWID:RAT {rbw_percent}')
        # Averaging: preset per half decade, optionally trace averaging over sweeps
        self.write(f'SWE:MODE {preset}')
        if averages is not None:
            self.write(f'SWE:COUN {int(averages)}')
        # Spur removal (all traces); the threshold is only available while the removal is on (else -200, "Function
        # not available")
        self.write(f'SPUR:SUPP {"ON" if spur_removal else "OFF"}')
        if spur_removal and spur_threshold_db is not None:
            self.write(f'SPUR:THR {spur_threshold_db}')
        self.set_sweep_mode(continuous=continuous)
        spurs = f"on, threshold {self.query('SPUR:THR?').strip()} dB" if spur_removal else "off"
        logger.info(f"[{self.info.name}] Phase noise mode: carrier {f_carrier / 1e6:.4f} MHz +- {freq_tolerance_hz:g} "
                    f"Hz, {carrier_level_dbm:g} dBm +- {level_tolerance_db:g} dB, tracking "
                    f"{'on' if tracking else 'off'}; offsets {offset_start:g}-{offset_stop:g} Hz, RBW "
                    f"{rbw_percent:g} % of the offset, preset {preset}, trace averages "
                    f"{self.query('SWE:COUN?').strip()}; spur removal {spurs}; "
                    f"{'continuous' if continuous else 'single'} sweep")

    def add_phase_noise_window(self, window_type: str, beside: str = '1', direction: str = 'RIGHt') -> str:
        """Add a result display to the phase-noise channel, next to window `beside`, e.g. 'SPURs' (spur list),
        'SNOise' (spot noise table), 'RNOise' (residual noise table), 'SRESults' (sweep result list), 'SPECtrum'
        (spectrum monitor); `direction` LEFT | RIGHt | ABOVe | BELow. Returns the new window's name."""
        return self.query(f"LAY:ADD? '{beside}',{direction},{window_type}").strip()

    def set_phase_noise_spot_offsets(self, offsets: List[float]):
        """User spot-noise markers at `offsets` (Hz), at most PNO_MAX_SPOT_MARKERS (shown on the screen, read with
        read_phase_noise); the other custom markers are switched off."""
        if len(offsets) > PNO_MAX_SPOT_MARKERS:
            raise ValueError(f"At most {PNO_MAX_SPOT_MARKERS} spot-noise offsets, got {len(offsets)}")
        for m in range(1, PNO_MAX_SPOT_MARKERS + 1):
            if m <= len(offsets):
                self.write(f'CALC:SNO{m}:STAT ON')
                self.write(f'CALC:SNO{m}:X {offsets[m - 1]}')
            else:
                self.write(f'CALC:SNO{m}:STAT OFF')

    def read_phase_noise(self, offsets: List[float], band: List[float] = None) -> Dict:
        """
        Results of the last phase-noise sweep (run trigger_single_sweep first in single-sweep mode).

        Args:
            offsets: The offsets of set_phase_noise_spot_offsets, in the same order (Hz).
            band: (start, stop) integration range of the residual noise (Hz); None: the whole measurement range.

        Returns:
            Dictionary with
              'f_carrier', 'carrier_dbm': carrier frequency (Hz) and level (dBm) as measured;
              'spot': {offset: L [dBc/Hz]} of the spot-noise markers;
              'band': the integration range (None: the measurement range);
              'integrated_dbc': integrated phase noise over the band (dBc), 'rms_phase_rad' derived from it
                                (sqrt(2 x 10^(dBc/10)), double sideband);
              'jitter_s': residual RMS jitter over the band (s), as the analyzer computes it;
              'residual_pm', 'residual_fm_hz': residual PM (as the analyzer reports it) and FM (Hz);
              'spurs': the analyzer's spur list, [(offset [Hz], level [dBc]), ...];
              'jitter_discrete_s': RMS of the spurs' jitter (s), 'jitter_random_s': sqrt(jitter^2 - discrete^2) (s);
              'offset' (Hz) / 'level' (dBc/Hz): the L(f) curve of trace 1 (spur-free with spur removal on).
        """
        result = {'f_carrier': float(self.query('FETC:PNO:MEAS:FREQ?').strip()),
                  'carrier_dbm': float(self.query('FETC:PNO:MEAS:LEV?').strip())}
        result['spot'] = {offset: float(self.query(f'CALC:SNO{m}:Y?').strip())
                          for m, offset in enumerate(offsets, 1)}
        if band is None:
            self.write('CALC:EVAL OFF')  # residual noise over the whole measurement range
        else:
            self.write('CALC:EVAL ON')
            self.write(f'CALC:EVAL:STAR {band[0]}')
            self.write(f'CALC:EVAL:STOP {band[1]}')
        result['band'] = band
        result['integrated_dbc'] = float(self.query('FETC:PNO:IPN?').strip())
        result['rms_phase_rad'] = math.sqrt(2 * 10 ** (result['integrated_dbc'] / 10))
        result['jitter_s'] = float(self.query('FETC:PNO:RMS?').strip())
        result['residual_pm'] = float(self.query('FETC:PNO:RPM?').strip())
        result['residual_fm_hz'] = float(self.query('FETC:PNO:RFM?').strip())
        spurs = [float(v) for v in self.query('FETC:PNO:SPUR?').strip().split(',') if v.strip()]
        result['spurs'] = list(zip(spurs[0::2], spurs[1::2]))  # offset / level pairs
        result['jitter_discrete_s'] = float(self.query('FETC:PNO:SPUR:DISC?').strip())
        result['jitter_random_s'] = float(self.query('FETC:PNO:SPUR:RAND?').strip())
        self.write('FORM ASC')
        xy = [float(v) for v in self.query('TRAC:DATA? TRACE1').strip().split(',')]
        result['offset'], result['level'] = xy[0::2], xy[1::2]  # offset / level pairs
        return result

    def list_scpi_commands(self, contains: str = '', timeout_ms: int = 60000) -> List[str]:
        """The SCPI headers the analyzer accepts in the active channel (SYST:HELP:HEAD?), only those containing
        `contains` (case-insensitive), e.g. list_scpi_commands('SNO') in the phase-noise channel."""
        original_timeout = self.tool.timeout
        self.tool.timeout = timeout_ms  # the full list is long
        try:
            self.tool.write('SYST:HELP:HEAD?')
            # read_raw: up to the end of the message (the list is one header per line: query() stops at the first)
            headers = self.tool.read_raw().decode('ascii', errors='replace').replace('\r', '').split('\n')
        finally:
            self.tool.timeout = original_timeout
        return [h.strip() for h in headers if h.strip() and contains.upper() in h.upper()]

    def stop_phase_noise_mode(self):
        """Back to the spectrum channel (the phase-noise channel stays until the next reset)."""
        self.write('INST:SEL SAN')

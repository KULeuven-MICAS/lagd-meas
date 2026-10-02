# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

import socket
import subprocess
import pyvisa
import logging
import time
from typing import Union, Dict, List

from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)

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

    def measure_phase_noise_profile(self,
                                    averages: int,
                                    offset_span_map: Dict[float, float]) -> Dict[float, float]:
        """
        Execute phase noise measurements over a set of offset frequencies

        Args:
            averages: Number of sweeps to average before taking the measurement.
            offset_span_map: Dictionary mapping target offset frequencies (Hz)
                             to the required measurement span (Hz).
                             Example: {100: 2.1e3, 1000: 2.1e3, 10000: 21e3}

        Returns:
            Dictionary mapping the evaluated offsets to their phase noise values in dBc/Hz.
        """

        results = {}

        # Activate phase noise measurement
        self.set_delta_marker_state(marker=2, state=True)
        self.enable_phase_noise_marker(marker=2, state=True)

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

                # Dynamically adjust RBW to prevent timeout on wide spans
                if required_span > 1e6:
                    logger.info(f"[{self.info.name}] Span > 1 MHz detected. Increasing RBW to 10 Hz.")
                    self.set_rbw(10.0)
                else:
                    self.set_rbw(1.0)

                # To clear the previous average buffer, toggle trace mode
                self.set_trace_mode(trace=1, mode='WRITe')
                self.set_trace_mode(trace=1, mode='AVERage')

                logger.info(f"[{self.info.name}] Acquiring {averages} sweeps at {required_span} Hz span...")
                self.trigger_single_sweep(wait=True)
                current_span = required_span

            # Move the marker to the specific offset frequency.
            self.set_delta_marker_x(marker=2, offset=offset)

            # Allow a brief moment for the instrument to calculate the marker function result
            time.sleep(0.1)

            # Fetch the phase noise marker value
            pno_val = self.get_delta_marker_y(marker=2)
            results[offset] = pno_val
            logger.info(f"[{self.info.name}] Phase Noise at {offset} Hz: {pno_val} dBc/Hz")

        return results

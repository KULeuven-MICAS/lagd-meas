# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

import pyvisa
import logging
from typing import Union

from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)

class RohdeSchwarzScopeRTB2004(inst.BaseOscilloscope):
    """
    Class for the Rohde & Schwarz RTB2004 oscilloscope.
    It implements the specific methods for this instrument.
    info: inst.BaseOscilloscopeData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Expects a list of channels

    """
    def __init__(self, info: inst.BaseOscilloscopeData, verbose: bool = False):
        self._num_channels = 4
        self._channel_names = ["CH1", "CH2", "CH3", "CH4"]
        self._lookup_channel = {
            "CH1": 1,
            "CH2": 2,
            "CH3": 3,
            "CH4": 4
        }
        super().__init__(info, verbose)

    def _open_resource(self):
        """
        Open the resource for the Rohde & Schwarz RTB2004 oscilloscope.
        """
        rm = pyvisa.ResourceManager()
        logger.info(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        return rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")

    def _init_instrument(self):
        logger.info(f"Initializing {self.info.name}")
        self.write('*RST', check=False)  # Reset the instrument to default settings
        _ = self.status()
        logger.info(f"{self.info.name} initialized successfully.")

    def _validate_channel(self, channel: Union[int, str]) -> Union[int, str]:
        """Validate a channel identifier for the oscilloscope."""
        if isinstance(channel, int):
            if channel < 1 or channel > self._num_channels:
                raise ValueError(f"Invalid channel {channel}. Valid range is 1..{self._num_channels}.")
            return channel
        if isinstance(channel, str):
            channel_name = channel.upper()
            if not channel_name.startswith('CH'):
                raise ValueError(f"Invalid channel '{channel}'. Expected names such as CH1 or CH2.")
            return channel_name
        raise TypeError(f"Unsupported channel type: {type(channel).__name__}")

    def fetch(self, channel: Union[int, str], measurement: str, measurement_id: int = 1):
        """
        Configure a measurement on the selected channel and return its result.
        """
        channel = self._validate_channel(channel)
        source = f"CH{channel}" if isinstance(channel, int) else channel
        self.set_measurement(measurement_id=measurement_id, main=measurement, source=source)
        return self.get_measurement_result(measurement_id=measurement_id)

    def measure_frequency(self, channel: Union[int, str], measurement_id: int = 1):
        """
        Measure the frequency on the selected channel.
        """
        return self.fetch(channel=channel, measurement='FREQ', measurement_id=measurement_id)

    def measure_period(self, channel: Union[int, str], measurement_id: int = 1):
        """
        Measure the period on the selected channel.
        """
        return self.fetch(channel=channel, measurement='PER', measurement_id=measurement_id)

    def measure_jitter(self, channel: Union[int, str], measurement_id: int = 1):
        """
        Measure the jitter on the selected channel.
        """
        channel = self._validate_channel(channel)
        source = f"CH{channel}" if isinstance(channel, int) else channel
        self.set_measurement(measurement_id=measurement_id, main='PER', source=source)
        return self.get_measurement_stddev(measurement_id=measurement_id)
    
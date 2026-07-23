# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import pyvisa
from statistics import mean
from typing import List, Union

from sw.lib.lab_instruments import instrument as inst

class KeysightPAN6700(inst.BasePowerSupply):
    """
    Class for the Keysight N6700 series power analyzer.
    It implements the specific methods for this instrument.
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Expects a list of channels

    """
    def __init__(self, info: inst.BaseInstrumentData):
        self._num_channels = 4
        self._channel_names = ["CH1", "CH2", "CH3", "CH4"]
        self._lookup_channel = {
            "CH1": 1,
            "CH2": 2,
            "CH3": 3,
            "CH4": 4
        }
        self._TINT_MIN = {
            "CH1": 1.024e-05,
            "CH2": 5.12e-06,
            "CH3": 5.12e-06,
            "CH4": 1.024e-05
        }  # Minimum integration time in seconds
        self._TINT_MAX = 40000  # Maximum integration time in seconds
        self._POIN_MAX = 524288  # Maximum number of points
        super().__init__(info)

    def _open_resource(self):
        """
        Open the resource for the Keysight N6700 series power analyzer.
        """
        rm = pyvisa.ResourceManager()
        print(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        return rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")

    def _init_instrument(self):
        self.tool.write('*RST')  # Reset the instrument to default settings

    def close(self):
        for ch in range(self._num_channels):
            if self._channel_state[ch]:
                self.write(f'OUTP OFF,(@{ch+1})')  # Turn off the output,

    def get_voltage(self, channel: Union[str, int]) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f"MEAS:VOLT? (@{channel})"))

    def set_voltage(self, channel: Union[str, int], voltage: float):
        channel = self._validate_channel(channel)
        self.write(f"VOLT {voltage},(@{channel})")

    def set_current_limit(self, channel: Union[str, int], current_limit: float):
        channel = self._validate_channel(channel)
        self.write(f"CURR:LIM {current_limit},(@{channel})")

    def turn_on_channels(self, channels: Union[int, str, List[Union[int, str]]]):
        if isinstance(channels, (int, str)):
            channels = [channels]
        elif not isinstance(channels, list):
            raise TypeError(f"Unsupported channels container type: {type(channels).__name__}")

        for channel in channels:
            channel = self._validate_channel(channel)
            self.write(f"OUTP ON,(@{channel})")
            self._channel_state[channel - 1] = True

    def set_current_meter(self, channel: int, auto_curr_range: int = 0,
        sample_int: float = 1.0, sample_points: int = 100) :
        """
        Integrate the current over a specified duration for a given channel.
        Args:
            channel (int): The channel number to measure.
            auto_curr_range (int): The auto current range to use.
            sample_int (float): The sampling interval. Default is 1.0.
            sample_points (int): The number of sample points. Default is 100.
        Returns:
            float: The integrated current value.
        """
        # Set the channel to measure
        self.write("SENS:FUNC:CURR ON,(@{channel})")

        self.write(f"SENS:CURR:RANG:AUTO {auto_curr_range},(@{channel})")
        if auto_curr_range == 0:
            raise Warning(
                "Auto current range is set to 0, no range selection supported.")

        self.write("SENS:SWE:TINT:RES RES20")  # Set the resolution to 20us

        self.write(f"SENS:SWE:TINT {sample_int},(@{channel})")
        self.write(f"SENS:SWE:POIN {sample_points},(@{channel})")

    def fetch(self, channel: int, what: str) -> Union[float, List[float]]:
        """
        Measure the current for a given channel.
        Args:
            channel (int): The channel number to measure.
            what (str): The type of measurement to fetch.
        Returns:
            float: The measured current value.
        """
        # Set the channel to measure
        self.write("INIT:IMM,(@{channel})")  # Start the measurement
        self.write("*WAI")  # Wait for the measurement to complete
        samples = self.query(f"FETC:{what}?,(@{channel})")  # Fetch the measurement data
        return mean(samples)  # Return the average of the measured samples

    def fetch_current(self, channel: int) -> float:
        return self.fetch(channel, "CURR")

    def fetch_rms_current(self, channel: int) -> float:
        return self.fetch(channel, "CURR:ACDC")

    def fetch_max_current(self, channel: int) -> float:
        return self.fetch(channel, "CURR:MAX")

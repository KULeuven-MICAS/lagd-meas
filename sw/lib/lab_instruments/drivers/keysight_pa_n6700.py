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

    def report_max_settings(self):
        """
        Report the maximum settings of the instrument.
        """
        self.write("SENS:SWE:TINT MIN")
        min_tint = self.query("SENS:SWE:TINT?")
        self.write("SENS:SWE:POIN MAX")
        max_points = self.query("SENS:SWE:POIN?")
        print(f"Minimum integration time: {min_tint} s")
        print(f"Maximum number of points: {max_points}")

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
        self.write("SENS:FUNC:CURR ON")

        self.write(f"SENS:CURR:RANG:AUTO {auto_curr_range}")
        if auto_curr_range == 0:
            raise Warning(
                "Auto current range is set to 0, no range selection supported.")

        self.write(f"SENS:SWE:TINT {sample_int}")
        self.write("SENS:SWE:TINT:RES RES20")  # Set the resolution to 20us
        self.write(f"SENS:SWE:POIN {sample_points}")

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
        self.write("INIT:IMM")  # Start the measurement
        self.write("*WAI")  # Wait for the measurement to complete
        samples = self.query(f"FETC:{what}?")  # Fetch the measurement data
        return mean(samples)  # Return the average of the measured samples

    def get_current(self, channel: int) -> float:
        return self.fetch(channel, "CURR")

    def get_rms_current(self, channel: int) -> float:
        return self.fetch(channel, "CURR:ACDC")

    def get_max_current(self, channel: int) -> float:
        return self.fetch(channel, "CURR:MAX")

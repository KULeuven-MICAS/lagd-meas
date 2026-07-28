# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import re
from dataclasses import dataclass, field
from typing import List, Union

@dataclass
class BaseInstrumentData:
    """
    Data class for the base instrument.
    It contains the common information that all instruments should have.
    :name: str: The name of the instrument.
        This should be unique for each instrument to identify it between two of the same type.
    :IP: str: The IP address of the instrument.
    :args: dict: Additional arguments for the instrument.
    """
    name: str
    IP: str
    args: dict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict):
        """Build an instrument description from a YAML mapping."""
        return cls(**data)

@dataclass
class BasePowerSupplyData(BaseInstrumentData):
    """
    Data class for the base power supply.
    It contains the common information that all power supplies should have.
    :channels: list: The list of channels of the power supply.
    """
    channels: list = field(default_factory=list)

class BaseInstrument:
    """
    Base class for all instruments.
    It defines the common interface and methods that all instruments should implement.
    :data: BaseInstrumentData: The data class containing the instrument's information.
    """
    def __init__(self, data: BaseInstrumentData, verbose: bool = False):
        self.info = data
        self._verbose = verbose
        self.tool = self._open_resource()
        self._init_instrument()

    def _open_resource(self): # Add return type hint
        """
        Open the resource for the instrument.
        This method should be implemented by the specific instrument class.
        """
        raise NotImplementedError

    def _init_instrument(self):
        """
        Initialize the instrument.
        This method should be implemented by the specific instrument class.
        """
        raise NotImplementedError

    def _close(self):
        """
        Close the resource for the instrument.
        This method should be implemented by the specific instrument class.
        """
        raise NotImplementedError

    @staticmethod
    def _ret_to_int(ret: str) -> int:
        """Convert a response like '+12' or '-3' into an integer."""
        # match requires string at the beginning, might change with search
        match = re.match(r"[+-]?\d+", ret)
        if match is None:
            raise ValueError(f"_ret_to_int failed: {ret}")

        return int(match.group(0)) #group(0) returns the entire match

    def set_verbose(self, verbose: bool):
        """Set the verbosity level for the instrument."""
        self._verbose = verbose

    def write(self, command: str, check: bool = True):
        """ Write a command to the instrument."""
        if self._verbose:
            print(f"\t{self.info.name}: {command}")
        self.tool.write(command)
        if check:
            ret = self.tool.query("SYST:ERR?")
            if self._ret_to_int(ret) != 0:
                raise ValueError(f'Instrument {self.info.name} error: {ret}')

    def query(self, command: str):
        """ Query the instrument and return the response."""
        if self._verbose:
            print(f"\t{self.info.name}: {command}")
        val = self.tool.query(command)
        return val

    def status(self):
        """ Get the status of the instrument."""
        idn = self.tool.query('*IDN?').strip()
        print(f"Instrument {self.info.name} ID: {idn}")
        return idn

    def close(self):
        """ Close the resource for the instrument."""
        if self.tool is not None:
            self._close()


class BasePowerSupply(BaseInstrument):
    """
    Base class for all power supplies.
    It defines the common interface and methods that all power supplies should implement.
    :data: BasePowerSupplyData: The data class containing the instrument's information.
    """
    def __init__(self, data: BasePowerSupplyData, verbose: bool = False):
        super().__init__(data, verbose=verbose)
        if not hasattr(self, '_num_channels'):
            raise NotImplementedError(
                "Channel count not set. Please set _num_channels in the subclass.")
        self._selected_channel = None
        # Track the state of each channel (on/off)
        self._channel_state = [False] * self._num_channels

    def _validate_channel(self, channel: Union[int, str]) -> int:
        """Validate channel number against configured channel count."""
        if isinstance(channel, str):
            if channel not in self._channel_names:
                raise ValueError(
                    f"Invalid channel name '{channel}'. Valid names are: {self._channel_names}.")
            return self._lookup_channel[channel]  # Return the corresponding index
        elif isinstance(channel, int):
            if channel > self._num_channels + 1:
                raise ValueError(
                    f"Invalid channel {channel}. Valid range is 1..{self._num_channels}.")
            return channel

    def _select_channel(self, channel: Union[int, str]):
        if channel == self._selected_channel:
            return  # Already selected
        else:
            if isinstance(channel, int):
                self.write(f'INST:NSEL {channel}')  # Select the channel by index
            elif isinstance(channel, str):
                self.write(f'INST:SEL {channel}')  # Select the channel by name
            else:
                raise TypeError(f"Unsupported channel type: {type(channel).__name__}")
            self._selected_channel = channel

    def _set_channel_from_dict(self, channel: Union[int, str], settings: dict):
        if 'voltage' in settings:
            self.set_voltage(channel, settings['voltage'])
        if 'current' in settings:
            self.set_current_limit(channel, settings['current'])

    def set_current_limit(self, channel: Union[int, str], current_limit: float):
        channel = self._validate_channel(channel)
        self._select_channel(channel)
        self.write(f'CURR {current_limit}')  # Set the current limit

    def set_voltage(self, channel: Union[int, str], voltage: float, current_limit: float = None):
        channel = self._validate_channel(channel)
        self._select_channel(channel)
        self.write(f'VOLT {voltage}')  # Set the voltage
        if current_limit is not None:
            self.set_current_limit(channel, current_limit)

    def set_channel(self, channel: Union[int, str], settings: dict = None):
        channel = self._validate_channel(channel)
        if settings is not None:
            self._set_channel_from_dict(channel, settings)
        else:
            # Get the channel settings from the instrument info
            self._set_channel_from_dict(channel, self.info.channels[channel - 1])

    def get_voltage(self, channel: Union[int, str]):
        channel = self._validate_channel(channel)
        self._select_channel(channel)
        return float(self.query('MEAS:VOLT?'))

    def get_current(self, channel: Union[int, str]):
        channel = self._validate_channel(channel)
        self._select_channel(channel)
        return float(self.query('MEAS:CURR?'))

    def turn_on_channels(self, channels: Union[int, str, List[Union[int, str]]]):
        """
        Turn on the specified channel of the Keysight N6700 series power analyzer.
        channel: str: The channel to turn on (e.g., '1', '2', '3', '4').
        If a list is provided, it will turn on all specified channels.
        """
        if isinstance(channels, (int, str)):
            channels = [channels]
        elif not isinstance(channels, list):
            raise TypeError(f"Unsupported channels container type: {type(channels).__name__}")

        for channel in channels:
            channel = self._validate_channel(channel)
            self._select_channel(channel)
            self.write('OUTP ON')  # Turn on the output for the selected channel
            self._channel_state[channel-1] = True  # Mark the channel as on

    def _close(self):
        """
        Close the resource for the instrument.
        This method should be implemented by the specific instrument class.
        """
        for ch in range(self._num_channels):
            if self._channel_state[ch]:
                self._select_channel(ch+1)
                self.write('OUTP OFF')  # Turn off the output

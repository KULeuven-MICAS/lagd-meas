# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

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
    def __init__(self, data: BaseInstrumentData):
        self.info = data
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
    def __init__(self, data: BasePowerSupplyData):
        super().__init__(data)
        self._num_channels = None
        self._channel_names = None

    def _validate_channel(self, channel: Union[int, str]):
        """Validate channel number against configured channel count."""
        if self._num_channels is None:
            raise NotImplementedError("Channel count not set. Please set _num_channels in the subclass.")
        if isinstance(channel, str):
            if channel not in self._channel_names:
                raise ValueError(f"Invalid channel name '{channel}'. Valid names are: {self._channel_names}.")
        elif isinstance(channel, int):
            if channel + 1 > self._num_channels:
                raise ValueError(
                    f"Invalid channel {channel}. Valid range is 1..{self._num_channels}."
                )

    def set_current_limit(self, channel: Union[int, str], current_limit: float):
        self._validate_channel(channel)
        if isinstance(channel, int):
            self.tool.write(f'CURR {current_limit}, (@{channel})') # Set the current limit
            return
        if isinstance(channel, str):
            self.tool.write(f'CURR {channel} {current_limit}') # Set the current limit
            return
        raise TypeError(f"Unsupported channel type: {type(channel).__name__}")

    def set_voltage(self, channel: Union[int, str], voltage: float, current_limit: float = None):
        self._validate_channel(channel)
        if isinstance(channel, int):
            self.tool.write(f'VOLT {voltage}, (@{channel})') # Set the voltage
        elif isinstance(channel, str):
            self.tool.write(f'VOLT {channel} {voltage}') # Set the voltage
        else:
            raise TypeError(f"Unsupported channel type: {type(channel).__name__}")
        if current_limit is not None:
            self.set_current_limit(channel, current_limit)

    def set_channel_from_dict(self, channel: Union[int, str], settings: dict):
        self._validate_channel(channel)
        if 'voltage' in settings:
            self.set_voltage(channel, settings['voltage'])
        if 'current' in settings:
            self.set_current_limit(channel, settings['current'])

    def set_channel(self, channel: Union[int, str], settings: dict = None):
        self._validate_channel(channel)
        if settings is not None:
            self.set_channel_from_dict(channel, settings)
        else:
            # Get the channel settings from the instrument info
            self.set_channel_from_dict(channel, self.info.channels[channel - 1])

    def get_voltage(self, channel: int):
        self._validate_channel(channel)
        # Query and return the measured voltage
        return float(self.tool.query(f'MEAS:VOLT? (@{channel})'))

    def get_current(self, channel: int):
        self._validate_channel(channel)
        # Query and return the measured current
        return float(self.tool.query(f'MEAS:CURR? (@{channel})'))

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

        channel_terms = []
        for channel in channels:
            self._validate_channel(channel)
            if isinstance(channel, int):
                channel_terms.append(f'(@{channel})')
            elif isinstance(channel, str):
                self.tool.write(f'OUTP {channel} ON')
            else:
                raise TypeError(f"Unsupported channel type: {type(channel).__name__}")
        if channel_terms:
            ch_str = ','.join(channel_terms)
            # Turn on the output for the specified channels
            self.tool.write(f'OUTP ON, {ch_str}')

    def _close(self):
        """
        Close the resource for the instrument.
        This method should be implemented by the specific instrument class.
        """
        ch_str = ','.join([f'(@{ch})' for ch in range(0, self._num_channels)])
        self.tool.write(f'OUTP OFF, {ch_str}')  # Turn off the output

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import pyvisa
from lib.lab_instruments import instrument as inst

class KeysightPSUE36300(inst.BaseInstrument):
    """
    Class for the Keysight E36300 series power supply.
    It implements the specific methods for this instrument.
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Expects a list of channels

    """
    def __init__(self, info: inst.BaseInstrumentData):
        super().__init__(info)

    def _open_resource(self):
        """
        Open the resource for the Keysight E36300 series power supply.
        """
        rm = pyvisa.ResourceManager()
        print(f"Reaching {self.info['name']} at: TCPIP::{self.info['IP']}::inst0::INSTR")
        return rm.open_resource(f"TCPIP::{self.info['IP']}::inst0::INSTR")

    def _init_instrument(self):
        """
        Initialize the Keysight E36300 series power supply.
        """
        self.tool.write('*RST')  # Reset the instrument to default settings
        self.tool.write('SYST:REM')  # Set to remote mode

    def set_current_limit(self, channel: str, current_limit: float):
        """
        Set the current limit for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:SEL {channel}')  # Select the channel
        self.tool.write(f'CURR {current_limit}')  # Set the current limit

    def set_voltage(self, channel: str, voltage: float, current_limit: float = None):
        """
        Set the voltage for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:SEL {channel}')  # Select the channel
        self.tool.write(f'VOLT {voltage}')  # Set the voltage

        if current_limit is not None:
            self.set_current_limit(channel, current_limit)

    def get_voltage(self, channel: str):
        """
        Get the voltage for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:SEL {channel}')  # Select the channel
        return float(self.tool.query('MEAS:VOLT?'))  # Query and return the measured voltage

    def get_current(self, channel: str):
        """
        Get the current for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:SEL {channel}')  # Select the channel
        return float(self.tool.query('MEAS:CURR?'))  # Query and return the measured current

    def get_channel_from_info(self, channel: str):
        """
        Get the channel settings from the instrument info.
        channel: str: The channel to get (e.g., 'CH1', 'CH2', 'CH3').
        Returns:
            dict: A dictionary containing the settings for the channel.
        """
        # Get the channel with the channel name from the instrument info channels list
        ret = None
        for ch in self.info.args['channels']:
            if ch['name'] == channel:
                ret = ch
                break
        return ret

    def turn_channel_on(self, channel: str):
        """
        Turn on the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:SEL {channel}')  # Select the channel
        self.tool.write('OUTP ON')  # Turn on the output

    def set_channel(self, channel: str, settings: dict = None):
        """
        Set the settings for the specified channel of the Keysight E36300 series power supply.
        channel: str: The channel to set (e.g., 'CH1', 'CH2', 'CH3').
        settings: dict: A dictionary containing the settings for the channel.
            Example: {'voltage': 5.0, 'current': 1.0}
        If settings is None, the default settings from the instrument info will be used.
        """
        self.tool.write(f'INST:SEL {channel}')  # Select the channel

        if settings is not None:
            if 'voltage' in settings:
                self.set_voltage(channel, settings['voltage'])  # Set the voltage
            if 'current_limit' in settings:
                self.set_current_limit(channel, settings['current'])  # Set the current limit
        else: # Use the default settings from the instrument info
            ch_info = self.get_channel_from_info(channel)
            if ch_info is not None:
                if 'voltage' in ch_info:
                    self.set_voltage(channel, ch_info['voltage'])  # Set the voltage
                if 'current' in ch_info:
                    self.set_current_limit(channel, ch_info['current'])  # Set the current limit
            else:
                raise ValueError(f"Channel {channel} not found in instrument info.")

    def _close(self):
        """
        Close the resource for the Keysight E36300 series power supply.
        """
        # TODO: iterate over all channels and turn them off before closing the resource
        self.tool.write('OUTP OFF')  # Turn off the output

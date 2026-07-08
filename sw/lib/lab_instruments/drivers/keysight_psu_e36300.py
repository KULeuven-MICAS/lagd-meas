# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import instrument as inst

class KeysightPSUE36300(inst.BaseInstrument):
    """
    Class for the Keysight E36300 series power supply.
    It implements the specific methods for this instrument.
    """
    def __init__(self, info):
        """
        Initialize the Keysight E36300 series power supply with the given instrument information.
        """
        super().__init__(info)
        self.tool = self._open_resource()
        self._init_instrument()

    def _open_resource(self):
        """
        Open the resource for the Keysight E36300 series power supply.
        """
        import pyvisa
        rm = pyvisa.ResourceManager()
        return rm.open_resource(f'TCPIP0::{self.info.IP}::inst0::INSTR')

    def _init_instrument(self):
        """
        Initialize the Keysight E36300 series power supply.
        """
        self.tool.write('*RST')  # Reset the instrument to default settings
        self.tool.write('SYST:REM')  # Set to remote mode
    
    def set_current_limit(self, channel, current_limit):
        """
        Set the current limit for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:NSEL {channel}')  # Select the channel
        self.tool.write(f'CURR {current_limit}')  # Set the current limit

    def set_voltage(self, channel, voltage, current_limit=None):
        """
        Set the voltage for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:NSEL {channel}')  # Select the channel
        self.tool.write(f'VOLT {voltage}')  # Set the voltage

        if current_limit is not None:
            self.set_current_limit(channel, current_limit)

    def get_voltage(self, channel):
        """
        Get the voltage for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:NSEL {channel}')  # Select the channel
        return float(self.tool.query('MEAS:VOLT?'))  # Query and return the measured voltage

    def get_current(self, channel):
        """
        Get the current for the specified channel of the Keysight E36300 series power supply.
        """
        self.tool.write(f'INST:NSEL {channel}')  # Select the channel
        return float(self.tool.query('MEAS:CURR?'))  # Query and return the measured current

    def _close(self):
        """
        Close the resource for the Keysight E36300 series power supply.
        """
        self.tool.close()
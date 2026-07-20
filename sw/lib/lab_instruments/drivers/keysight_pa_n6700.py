# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import pyvisa
from sw.lib.lab_instruments import instrument as inst

class KeysightPAN6700(inst.BaseInstrument):
    """
    Class for the Keysight N6700 series power analyzer.
    It implements the specific methods for this instrument.
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Expects a list of channels

    """
    def __init__(self, info: inst.BaseInstrumentData):
        super().__init__(info)
        self._num_channels = 4

    def _open_resource(self):
        """
        Open the resource for the Keysight N6700 series power analyzer.
        """
        rm = pyvisa.ResourceManager()
        print(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        return rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")

    def _init_instrument(self):
        self.tool.write('*RST')  # Reset the instrument to default settings



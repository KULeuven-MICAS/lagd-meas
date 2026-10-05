# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import logging
import time

import pyvisa
from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)

class KeysightPSUE36300(inst.BasePowerSupply):
    """
    Class for the Keysight E36300 series power supply.
    It implements the specific methods for this instrument.
    info: inst.BasePowerSupplyData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Expects a list of channels

    """
    def __init__(self, info: inst.BasePowerSupplyData, verbose: bool = False):
        self._num_channels = 3 # It has 3 channels
        self._channel_names = [
            "CH1", "P6V",  # Channel 1: 6V output
            "CH2", "P25V",  # Channel 2: 25V output
            "CH3", "N25V"]  # Channel 3: -25V output
        self._lookup_channel = {
            "CH1": 1, "P6V": 1,
            "CH2": 2, "P25V": 2,
            "CH3": 3, "N25V": 3}
        super().__init__(info, verbose=verbose)

    def _open_resource(self):
        """
        Open the resource for the Keysight E36300 series power supply.
        """
        rm = pyvisa.ResourceManager()
        logger.info(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        return rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")

    def _init_instrument(self):
        self.write('*RST')  # Reset the instrument to default settings
        self.write('SYST:REM')  # Set to remote mode

    def measure_current_stats(self, channel, n: int = 10) -> tuple:
        """Mean and standard deviation [A] of `n` current readings of one channel."""
        readings = [self.get_current(channel) for _ in range(n)]
        mean = sum(readings) / n
        std = (sum((x - mean) ** 2 for x in readings) / (n - 1)) ** 0.5 if n > 1 else 0.0
        return mean, std

    def measure(self, channel, n: int = 1, i_offset: float = 0.0) -> tuple:
        """Measured (voltage [V], current [A], power [W]) of one channel; the current is the mean of `n`
        readings minus `i_offset` (from zero_current)."""
        v = self.get_voltage(channel)
        i = self.measure_current_stats(channel, n)[0] - i_offset
        return v, i, v * i

    def zero_current(self, channel, n: int = 10, settle: float = 0.5) -> float:
        """Current readback offset [A] of one channel: the mean of `n` readings with the output on at 0 V
        (no current flows into an unpowered load). The voltage and output state are restored afterwards."""
        channel = self._validate_channel(channel)
        self._select_channel(channel)
        v_set = float(self.query('VOLT?'))
        was_on = self._channel_state[channel - 1]
        self.set_voltage(channel, 0.0)
        if not was_on:
            self.turn_on_channels(channel)
        time.sleep(settle)
        offset = self.measure_current_stats(channel, n)[0]
        if not was_on:
            self._select_channel(channel)
            self.write('OUTP OFF')
            self._channel_state[channel - 1] = False
        self.set_voltage(channel, v_set)
        logger.info(f"{self.info.name} CH{channel}: current offset {offset * 1e6:.2f} uA at 0 V ({n} readings)")
        return offset

    def _close(self):
        """Turn off every output that was turned on (BasePowerSupply), then release the VISA session."""
        try:
            super()._close()
        finally:
            self.tool.close()
            self.tool = None

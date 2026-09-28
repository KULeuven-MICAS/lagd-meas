# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

import logging

import pyvisa
from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)


class KeysightFG33600(inst.BaseInstrument):
    """
    Class for the Keysight 33600A series waveform generator (33611A/12A/21A/22A).
    It implements the specific methods for this instrument.
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Accepts
        channels: int, number of output channels (1 or 2, default 2).
    """
    def __init__(self, info: inst.BaseInstrumentData, verbose: bool = False):
        self._num_channels = info.args.get("channels", 2)
        self._channel_state = [False] * self._num_channels
        super().__init__(info, verbose=verbose)

    def _open_resource(self):
        """
        Open the resource for the Keysight 33600A series waveform generator.
        """
        rm = pyvisa.ResourceManager()
        logger.info(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        tool = rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")
        tool.timeout = 10000  # ms, *RST takes a moment
        return tool

    def _init_instrument(self):
        self.write('*RST', check=False)  # Reset to default settings (outputs off)
        self.query('*OPC?')  # Wait for the reset to finish before the next command
        self.write('*CLS')  # Clear the error queue

    def _validate_channel(self, channel: int) -> int:
        if channel not in range(1, self._num_channels + 1):
            raise ValueError(f"Invalid channel {channel}. Valid range is 1..{self._num_channels}.")
        return channel

    def set_load(self, channel: int, load: str = "INF"):
        """Set the expected load: 'INF' for high-Z, or a resistance in ohms (e.g. 50).
        The displayed/programmed amplitude assumes this load."""
        channel = self._validate_channel(channel)
        self.write(f'OUTP{channel}:LOAD {load}')

    def set_square(self, channel: int, freq: float, vpp: float, offset: float = 0.0, duty: float = 50.0):
        """Configure a square wave: frequency [Hz], amplitude [Vpp], offset [V], duty cycle [%]."""
        channel = self._validate_channel(channel)
        self.write(f'SOUR{channel}:FUNC SQU')
        self.write(f'SOUR{channel}:VOLT:UNIT VPP')
        self.write(f'SOUR{channel}:FREQ {freq}')
        self.write(f'SOUR{channel}:VOLT {vpp}')
        self.write(f'SOUR{channel}:VOLT:OFFS {offset}')
        self.write(f'SOUR{channel}:FUNC:SQU:DCYC {duty}')

    def set_frequency(self, channel: int, freq: float):
        channel = self._validate_channel(channel)
        self.write(f'SOUR{channel}:FREQ {freq}')

    def get_frequency(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f'SOUR{channel}:FREQ?'))

    def set_amplitude(self, channel: int, vpp: float, offset: float = None):
        channel = self._validate_channel(channel)
        self.write(f'SOUR{channel}:VOLT {vpp}')
        if offset is not None:
            self.write(f'SOUR{channel}:VOLT:OFFS {offset}')

    def get_amplitude(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f'SOUR{channel}:VOLT?'))

    def get_offset(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f'SOUR{channel}:VOLT:OFFS?'))

    def output_on(self, channel: int):
        channel = self._validate_channel(channel)
        self.write(f'OUTP{channel} ON')
        self._channel_state[channel - 1] = True

    def output_off(self, channel: int):
        channel = self._validate_channel(channel)
        self.write(f'OUTP{channel} OFF')
        self._channel_state[channel - 1] = False

    def _close(self):
        """Turn off every output that was turned on, then release the VISA session."""
        for ch in range(self._num_channels):
            if self._channel_state[ch]:
                self.output_off(ch + 1)
        self.tool.close()

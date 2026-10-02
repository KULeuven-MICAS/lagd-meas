# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

import logging
import math
import statistics
import time

import pyvisa
from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)

# The scope returns this for a measurement it cannot compute (no signal, clipped, ...).
INVALID_RESULT = 9.9e37


class RSScopeRTB2000(inst.BaseInstrument):
    """
    Class for the Rohde & Schwarz RTB2000 series oscilloscope (RTB2002/RTB2004).
    It implements the specific methods for this instrument. Inputs are 1 MOhm.
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Accepts
        channels: int, number of analog channels (default 4).
    """
    def __init__(self, info: inst.BaseInstrumentData, verbose: bool = False):
        self._num_channels = info.args.get("channels", 4)
        self._probe_att = {}  # channel -> attenuation factor, see set_probe_attenuation
        super().__init__(info, verbose=verbose)

    def _open_resource(self):
        """
        Open the resource for the R&S RTB2000 series oscilloscope.
        """
        rm = pyvisa.ResourceManager()
        logger.info(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        tool = rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")
        tool.timeout = 10000  # ms, *RST takes a moment
        return tool

    def _init_instrument(self):
        self.write('*RST', check=False)  # Reset to default settings
        self.query('*OPC?')  # Wait for the reset to finish before the next command
        self.write('*CLS')  # Clear the error queue

    def _validate_channel(self, channel: int) -> int:
        if channel not in range(1, self._num_channels + 1):
            raise ValueError(f"Invalid channel {channel}. Valid range is 1..{self._num_channels}.")
        return channel

    def set_channel(self, channel: int, scale: float, offset: float = 0.0):
        """Turn a channel on with DC coupling: scale [V/div], offset [V] (the value at screen center)."""
        channel = self._validate_channel(channel)
        self.write(f'CHAN{channel}:STAT ON')
        self.write(f'CHAN{channel}:COUP DCL')  # DC, 1 MOhm
        self.write(f'CHAN{channel}:SCAL {scale}')
        self.write(f'CHAN{channel}:POS 0')
        self.write(f'CHAN{channel}:OFFS {offset}')

    def set_probe_attenuation(self, channel: int, factor: float = 1):
        """Set the probe attenuation factor (1 for a direct BNC cable, 10 for a 10:1 probe)."""
        channel = self._validate_channel(channel)
        self.write(f'PROB{channel}:SET:ATT:UNIT V')
        self.write(f'PROB{channel}:SET:ATT:MAN {factor}')
        self._probe_att[channel] = factor

    def set_timebase(self, scale: float):
        """Set the horizontal scale [s/div]."""
        self.write(f'TIM:SCAL {scale}')

    def set_edge_trigger(self, channel: int, level: float):
        """Rising-edge trigger on a channel at `level` [V], auto mode (free-runs without a trigger)."""
        channel = self._validate_channel(channel)
        self.write('TRIG:A:MODE AUTO')
        self.write('TRIG:A:TYPE EDGE')
        self.write(f'TRIG:A:SOUR CH{channel}')
        self.write('TRIG:A:EDGE:SLOP POS')
        self.write(f'TRIG:A:LEV{channel}:VAL {level}')

    def run(self):
        """Start continuous acquisition."""
        self.write('RUN')

    def autoscale(self, settle: float = 1.0):
        """Let the scope find the signal (sets channels, timebase and trigger)."""
        self.write('AUT', check=False)
        self.query('*OPC?')  # Wait for autoscale to finish
        time.sleep(settle)  # the automatic measurements only update after new acquisitions

    def recover(self):
        """Back to a working state after an instrument error: clear the interface and the error
        queue, restart the acquisition and find the signal again."""
        self.tool.clear()
        self.write('*CLS', check=False)
        self.write('RUN', check=False)
        self.autoscale()

    def wait_valid(self, slot: int, timeout: float = 2.0, poll: float = 0.2) -> float:
        """Read a measurement slot until it is valid (not NaN) or `timeout` [s] passes."""
        t_end = time.time() + timeout
        while True:
            val = self.read_measurement(slot)
            if not math.isnan(val) or time.time() > t_end:
                return val
            time.sleep(poll)

    def fit_to_signal(self, channel: int, freq_slot: int, peak_slot: int, mean_slot: int,
                      n_periods: float = 5, n_div: float = 6, settle: float = 0.5, min_vpp: float = 0.05,
                      min_freq: float = 10e3) -> bool:
        """Adjust timebase, vertical scale/offset and trigger level to the measured waveform.

        Needs measurement slots already assigned to FREQ, PEAK and MEAN on `channel`.
        Shows about `n_periods` periods over the 10 horizontal divisions and lets the
        signal span about `n_div` vertical divisions around its mean. Returns False
        (settings untouched) when the scope cannot measure the waveform, when it is
        smaller than `min_vpp` [V] (noise, no clock), or slower than `min_freq` [Hz]: that
        timebase would put the scope in roll mode, where the edge trigger is refused.
        """
        freq = self.read_measurement(freq_slot)
        vpp = self.read_measurement(peak_slot)
        mean = self.read_measurement(mean_slot)
        if (math.isnan(freq) or math.isnan(vpp) or math.isnan(mean) or freq < min_freq
                or vpp < min_vpp):
            logger.warning(f"{self.info.name}: cannot fit to CH{channel}, no valid measurement "
                           f"(f {freq:.3e} Hz, {vpp:.3f} Vpp)")
            return False
        att = self._probe_att.get(channel, 1)
        scale = min(max(vpp / n_div, 1e-3 * att), 5 * att)  # RTB2000: 1 mV..5 V/div at the input
        self.set_timebase(n_periods / freq / 10)
        self.set_channel(channel, scale=scale, offset=mean)
        self.set_edge_trigger(channel, level=mean)
        time.sleep(settle)  # let the acquisition and measurements settle
        return True

    def set_measurement(self, slot: int, channel: int, meas_type: str):
        """Assign an automatic measurement slot (1..6), e.g. meas_type 'FREQ', 'PER', 'PEAK', 'MEAN'."""
        channel = self._validate_channel(channel)
        self.write(f'MEAS{slot}:SOUR CH{channel}')
        self.write(f'MEAS{slot}:MAIN {meas_type}')
        self.write(f'MEAS{slot} ON')

    def read_measurement(self, slot: int) -> float:
        """Current result of a measurement slot; NaN when the scope cannot compute it."""
        val = float(self.query(f'MEAS{slot}:RES:ACT?'))
        return math.nan if abs(val) >= INVALID_RESULT else val

    def measure_stats(self, slot: int, n: int = 10, interval: float = 0.1) -> tuple:
        """Read a measurement slot `n` times, `interval` [s] apart; returns (mean, std, n_valid)."""
        vals = []
        for _ in range(n):
            val = self.read_measurement(slot)
            if not math.isnan(val):
                vals.append(val)
            time.sleep(interval)
        if not vals:
            return math.nan, math.nan, 0
        std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        return statistics.mean(vals), std, len(vals)

    def _close(self):
        """Release the VISA session."""
        self.tool.close()

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

import logging
import math
import time

import numpy as np
import pyvisa
from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)

# The scope returns this for a measurement it cannot compute (no signal, clipped, no edges, ...).
INVALID_RESULT = 9.9e37
# Vertical scale limits [V/div] at the input for the 50 Ohm input (the 1 MOhm input goes higher).
SCALE_MIN, SCALE_MAX_50 = 1e-3, 1.0

# Automatic measurements of measure_clock: result key -> Infiniium :MEASure query (source appended).
CLOCK_MEASUREMENTS = {
    "freq": ":MEASure:FREQuency?",
    "period": ":MEASure:PERiod?",
    "vmax": ":MEASure:VMAX?",
    "vmin": ":MEASure:VMIN?",
    "vpp": ":MEASure:VPP?",
    "vtop": ":MEASure:VTOP?",
    "vbase": ":MEASure:VBASe?",
    "vamp": ":MEASure:VAMPlitude?",
    "vavg": ":MEASure:VAVerage? DISPlay,",
    "rise": ":MEASure:RISetime?",
    "fall": ":MEASure:FALLtime?",
    "duty": ":MEASure:DUTYcycle?",
    "overshoot": ":MEASure:OVERshoot?",
    "preshoot": ":MEASure:PREShoot?",
}

# Jitter measurements of jitter_statistics: result key -> (Infiniium command adding the measurement, `{ch}` = channel
# number; a word of the label the scope gives it in :MEASure:RESults?, lower case). TIE and cycle-to-cycle need the
# EZJIT option: a measurement the scope rejects is skipped (NaN). Not yet tried on the instrument: check the labels in
# the raw reply (scope_results) on the first run.
JITTER_MEASUREMENTS = {
    "period": (":MEASure:PERiod CHANnel{ch}", "period"),
    "ctc": (":MEASure:CTCJitter CHANnel{ch},RISing", "cycle"),
    "tie": (":MEASure:TIEClock2 CHANnel{ch},SECond,RISing,AUTO", "tie"),
}
# Statistics per measurement in :MEASure:RESults? with :MEASure:STATistics ON, in the order the scope sends them
STAT_FIELDS = ("current", "min", "max", "mean", "std", "count")


def _parse_results(raw: str) -> list:
    """(label, [values]) per measurement of a :MEASure:RESults? reply: every non-numeric field starts a measurement,
    the numeric fields after it are its values."""
    out = []
    for field in raw.strip().split(","):
        try:
            value = float(field)
        except ValueError:
            out.append((field.strip().strip('"'), []))
            continue
        if out:
            out[-1][1].append(math.nan if abs(value) >= INVALID_RESULT else value)
    return out


class KeysightScopeMXR058A(inst.BaseInstrument):
    """
    Class for the Keysight Infiniium MXR058A oscilloscope (8 channels, 500 MHz, 50 Ohm / 1 MOhm inputs).
    It implements the specific methods for this instrument (Infiniium SCPI).
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Accepts
        channels: int, number of analog channels (default 8).

    Opening the scope resets it. set_channel selects the input impedance per channel (default 50 Ohm, DC): with
    50 Ohm the scope is the termination, like the input of the spectrum analyzer. Stay within the input rating on
    the front panel for the 50 Ohm input.
    """
    def __init__(self, info: inst.BaseInstrumentData, verbose: bool = False):
        self._num_channels = info.args.get("channels", 8)
        self._impedance = {}  # channel -> 50 or 1e6 [Ohm], see set_channel
        super().__init__(info, verbose=verbose)

    def _open_resource(self):
        """
        Open the resource for the Keysight MXR058A oscilloscope.
        """
        rm = pyvisa.ResourceManager()
        logger.info(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        tool = rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")
        tool.timeout = 20000  # ms, *RST and long acquisitions take a while
        return tool

    def _init_instrument(self):
        self.write('*RST', check=False)  # Reset to default settings
        self.query('*OPC?')  # Wait for the reset to finish before the next command
        self.write('*CLS')  # Clear the error queue
        _ = self.status()

    def _validate_channel(self, channel: int) -> int:
        if channel not in range(1, self._num_channels + 1):
            raise ValueError(f"Invalid channel {channel}. Valid range is 1..{self._num_channels}.")
        return channel

    # --- Vertical ---

    def set_channel(self, channel: int, scale: float, offset: float = 0.0, impedance: float = 50):
        """Turn a channel on, DC coupled: scale [V/div], offset [V] (the value at screen center), input impedance
        50 or 1e6 [Ohm]."""
        channel = self._validate_channel(channel)
        if impedance not in (50, 1e6):
            raise ValueError(f"Invalid impedance {impedance}: 50 or 1e6 Ohm.")
        self.write(f':CHANnel{channel}:DISPlay ON')
        self.write(f':CHANnel{channel}:INPut {"DC50" if impedance == 50 else "DC"}')
        self.write(f':CHANnel{channel}:SCALe {scale}')
        self.write(f':CHANnel{channel}:OFFSet {offset}')
        self._impedance[channel] = impedance

    def channel_off(self, channel: int):
        channel = self._validate_channel(channel)
        self.write(f':CHANnel{channel}:DISPlay OFF')

    def set_bandwidth(self, bandwidth="MAX"):
        """Acquisition bandwidth limit: "MAX" (500 MHz), "AUTO" (follows the sample rate) or a value [Hz]."""
        self.write(f':ACQuire:BANDwidth {bandwidth}')

    # --- Horizontal, acquisition, trigger ---

    def set_timebase(self, scale: float, position: float = 0.0):
        """Horizontal scale [s/div] and the time at screen center relative to the trigger [s]."""
        self.write(':TIMebase:REFerence CENTer')
        self.write(f':TIMebase:SCALe {scale}')
        self.write(f':TIMebase:POSition {position}')

    def set_acquisition(self, sample_rate="MAX", points="AUTO", averages: int = 1):
        """Real-time acquisition: sample rate [Sa/s] or "MAX", record length [points] or "AUTO", and `averages`
        acquisitions averaged per waveform (1: off; averaging needs a stable trigger and removes the jitter)."""
        self.write(':ACQuire:MODE RTIMe')
        self.write(f':ACQuire:SRATe:ANALog {sample_rate}')
        self.write(f':ACQuire:POINts:ANALog {points}')
        if averages > 1:
            self.write(f':ACQuire:AVERage:COUNt {averages}')
            self.write(':ACQuire:AVERage ON')
        else:
            self.write(':ACQuire:AVERage OFF')

    def set_edge_trigger(self, channel: int, level: float, slope: str = "POSitive", sweep: str = "AUTO"):
        """Edge trigger on a channel at `level` [V], slope "POSitive" / "NEGative" / "EITHer"; sweep "AUTO"
        (free-runs without a trigger) or "TRIGgered" (waits for one)."""
        channel = self._validate_channel(channel)
        self.write(':TRIGger:MODE EDGE')
        self.write(f':TRIGger:EDGE1:SOURce CHANnel{channel}')
        self.write(f':TRIGger:EDGE1:SLOPe {slope}')
        self.write(f':TRIGger:LEVel CHANnel{channel},{level}')
        self.write(f':TRIGger:SWEep {sweep}')

    def run(self):
        """Start continuous acquisition."""
        self.write(':RUN')

    def stop(self):
        self.write(':STOP')

    def digitize(self, channel: int, timeout_ms: int = 60000):
        """Take one acquisition (all averages when averaging is on) on `channel` and stop; blocks until done.
        Waveform and measurements then refer to this acquisition until run()."""
        channel = self._validate_channel(channel)
        original_timeout = self.tool.timeout
        try:
            self.tool.timeout = timeout_ms
            self.write(f':DIGitize CHANnel{channel}', check=False)
            self.query('*OPC?')
        finally:
            self.tool.timeout = original_timeout
        ret = self.query(':SYSTem:ERRor?')
        if self._ret_to_int(ret) != 0:
            raise ValueError(f'Instrument {self.info.name} error after digitize: {ret}')

    def autoscale(self, settle: float = 1.0):
        """Let the scope find the signal (sets channels, timebase and trigger)."""
        self.write(':AUToscale', check=False)
        self.query('*OPC?')
        time.sleep(settle)

    # --- Measurements ---

    def measure(self, channel: int, query: str) -> float:
        """Result of an Infiniium measurement query on `channel`, e.g. ":MEASure:FREQuency?"; a query ending in
        "," (e.g. ":MEASure:VAVerage? DISPlay,") gets the source appended without a space. NaN when the scope
        cannot compute it."""
        channel = self._validate_channel(channel)
        sep = "" if query.endswith(",") else " "
        val = float(self.query(f'{query}{sep}CHANnel{channel}'))
        return math.nan if abs(val) >= INVALID_RESULT else val

    def measure_clock(self, channel: int) -> dict:
        """The CLOCK_MEASUREMENTS of a clock on `channel` (freq [Hz], period/rise/fall [s], levels [V], duty [%],
        overshoot/preshoot [%]); NaN for what the scope cannot compute. Rise/fall use the scope's default thresholds
        (10-90 %). Use after digitize() to measure exactly the acquired waveform."""
        return {key: self.measure(channel, q) for key, q in CLOCK_MEASUREMENTS.items()}

    def fit_to_signal(self, channel: int, n_periods: float = 5, n_div: float = 8, settle: float = 0.5,
                      min_vpp: float = 0.01) -> bool:
        """Adjust timebase, vertical scale/offset and trigger level to the clock on `channel`: about `n_periods`
        periods over the 10 horizontal divisions, the signal over about `n_div` of the 10 vertical divisions around
        its middle, trigger at the middle. Returns False (settings untouched) when the scope cannot measure a
        frequency or the signal is smaller than `min_vpp` [V] (no clock)."""
        channel = self._validate_channel(channel)
        freq = self.measure(channel, CLOCK_MEASUREMENTS["freq"])
        vmax = self.measure(channel, CLOCK_MEASUREMENTS["vmax"])
        vmin = self.measure(channel, CLOCK_MEASUREMENTS["vmin"])
        if math.isnan(freq) or math.isnan(vmax) or math.isnan(vmin) or vmax - vmin < min_vpp:
            logger.warning(f"{self.info.name}: cannot fit to CH{channel}, no valid clock "
                           f"(f {freq:.4e} Hz, {vmin:.3f} .. {vmax:.3f} V)")
            return False
        scale_max = SCALE_MAX_50 if self._impedance.get(channel, 50) == 50 else 10.0
        scale = min(max((vmax - vmin) / n_div, SCALE_MIN), scale_max)
        mid = (vmax + vmin) / 2
        self.set_timebase(n_periods / freq / 10)
        self.set_channel(channel, scale=scale, offset=mid, impedance=self._impedance.get(channel, 50))
        self.set_edge_trigger(channel, level=mid)
        time.sleep(settle)
        return True

    def _try_write(self, command: str) -> bool:
        """Write `command`; False (logged, error queue cleared) when the scope rejects it, e.g. a missing option."""
        try:
            self.write(command)
            return True
        except ValueError as e:
            logger.warning(f"{self.info.name}: {command} rejected ({e})")
            self.write('*CLS', check=False)
            return False

    def jitter_statistics(self, channel: int, accumulate: float = 10.0) -> dict:
        """The scope's own jitter measurements (JITTER_MEASUREMENTS) on `channel`, over every edge of every
        acquisition during `accumulate` [s] of continuous acquisition: {<key>_<STAT_FIELDS>} [s] (count: number of
        edges), NaN for a measurement the scope rejected (TIE / cycle-to-cycle without EZJIT), and "scope_results",
        the raw :MEASure:RESults? reply. Also turns on the scope's jitter histogram when it offers one (it then shows on
        a screenshot). Leaves the scope stopped."""
        channel = self._validate_channel(channel)
        self.write(':MEASure:CLEar')
        self._try_write(':ANALyze:AEDGes ON')  # measure every edge in the record, not only the first one
        added = [key for key, (cmd, _) in JITTER_MEASUREMENTS.items() if self._try_write(cmd.format(ch=channel))]
        self.write(':MEASure:STATistics ON')
        if "tie" in added:
            self._try_write(':MEASure:JITTer:HISTogram ON')
        self.write(':CDISplay')  # clears the display and the measurement statistics
        self.run()
        time.sleep(accumulate)
        self.stop()
        raw = self.query(':MEASure:RESults?')
        result = {f"{key}_{s}": math.nan for key in JITTER_MEASUREMENTS for s in STAT_FIELDS}
        for label, values in _parse_results(raw):
            key = next((k for k in added if JITTER_MEASUREMENTS[k][1] in label.lower()), None)
            if key is not None and len(values) >= len(STAT_FIELDS):
                result.update({f"{key}_{s}": v for s, v in zip(STAT_FIELDS, values[-len(STAT_FIELDS):])})
        result["scope_results"] = raw.strip()
        logger.info(f"{self.info.name}: jitter statistics over {accumulate:g} s ({', '.join(added) or 'none'}): "
                    f"{raw.strip()}")
        return result

    # --- Data ---

    def get_waveform(self, channel: int) -> tuple:
        """The waveform of `channel` on screen (after digitize(): the acquired one) as (time [s], voltage [V]) numpy
        arrays; time 0 is the trigger."""
        channel = self._validate_channel(channel)
        self.write(f':WAVeform:SOURce CHANnel{channel}')
        self.write(':WAVeform:FORMat WORD')
        self.write(':WAVeform:BYTeorder LSBFirst')
        self.write(':WAVeform:STReaming OFF')
        x_inc = float(self.query(':WAVeform:XINCrement?'))
        x_org = float(self.query(':WAVeform:XORigin?'))
        y_inc = float(self.query(':WAVeform:YINCrement?'))
        y_org = float(self.query(':WAVeform:YORigin?'))
        raw = self.tool.query_binary_values(':WAVeform:DATA?', datatype='h', is_big_endian=False,
                                            container=np.array)
        return x_org + x_inc * np.arange(len(raw)), y_org + y_inc * raw.astype(float)

    def screenshot(self, path):
        """Save the screen as a PNG file at `path`."""
        data = self.tool.query_binary_values(':DISPlay:DATA? PNG', datatype='B', container=bytes)
        with open(str(path), 'wb') as f:
            f.write(data)

    def _close(self):
        """Release the VISA session."""
        self.tool.close()

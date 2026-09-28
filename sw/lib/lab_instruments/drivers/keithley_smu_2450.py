# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

import logging

import pyvisa
from sw.lib.lab_instruments import instrument as inst

logger = logging.getLogger(__name__)


class KeithleySMU2450(inst.BaseInstrument):
    """
    Class for the Keithley 2450 SourceMeter, used as a voltage source.
    The instrument must be set to the SCPI command set (not TSP).
    info: inst.BaseInstrumentData: The data class containing the instrument's information.
    info.args: dict: Additional arguments for the instrument. Accepts
        v_min, v_max: float, software clamp on the source voltage [V] (default 0, 0.75).
        i_limit: float, current compliance [A] (default 10e-6).
        terminals: str, 'FRON' or 'REAR' (default 'FRON').
        remote_sense: bool, 4-wire sensing (default False).
    """
    def __init__(self, info: inst.BaseInstrumentData, verbose: bool = False):
        self._v_min = info.args.get("v_min", 0.0)
        self._v_max = info.args.get("v_max", 0.75)
        self._output_on = False
        super().__init__(info, verbose=verbose)

    def _open_resource(self):
        """
        Open the resource for the Keithley 2450 SourceMeter.
        """
        rm = pyvisa.ResourceManager()
        logger.info(f"Reaching {self.info.name} at: TCPIP::{self.info.IP}::inst0::INSTR")
        return rm.open_resource(f"TCPIP::{self.info.IP}::inst0::INSTR")

    def _init_instrument(self):
        """Reset, then configure as a voltage source measuring current at 0 V, output off."""
        args = self.info.args
        self.write('*RST')  # Reset the instrument to default settings (output off)
        self.write('*CLS')  # Clear the error queue
        self.write(f':ROUT:TERM {args.get("terminals", "FRON")}')
        self.write(':SOUR:FUNC VOLT')
        self.write(':SOUR:VOLT:RANG 2')  # Smallest range covering 0..VDD
        self.write(':SOUR:VOLT 0')
        self.set_current_limit(args.get("i_limit", 10e-6))
        self.write(':SENS:FUNC "CURR"')
        self.write(':SENS:CURR:RANG:AUTO ON')
        self.write(f':SENS:CURR:RSEN {"ON" if args.get("remote_sense", False) else "OFF"}')

    def set_current_limit(self, i_limit: float):
        """Set the current compliance [A] of the voltage source."""
        self.write(f':SOUR:VOLT:ILIM {i_limit}')

    def set_nplc(self, nplc: float):
        """Set the measurement integration time in power-line cycles (0.01..10)."""
        self.write(f':SENS:CURR:NPLC {nplc}')

    def set_voltage(self, voltage: float):
        """Set the source voltage [V]; refuses values outside [v_min, v_max]."""
        if not self._v_min <= voltage <= self._v_max:
            raise ValueError(
                f"{self.info.name}: {voltage} V outside the allowed range [{self._v_min}, {self._v_max}] V")
        self.write(f':SOUR:VOLT {voltage}')

    def measure(self) -> tuple:
        """Trigger one measurement; returns (measured voltage [V], measured current [A])."""
        # SOUR is the measured source readback (source readback is on by default).
        ret = self.query(':READ? "defbuffer1", SOUR, READ')
        v, i = (float(x) for x in ret.strip().split(','))
        return v, i

    def in_compliance(self) -> bool:
        """True when the source is limited by the current compliance."""
        return self._ret_to_int(self.query(':SOUR:VOLT:ILIM:TRIP?')) == 1

    def output_on(self):
        self.write(':OUTP ON')
        self._output_on = True

    def output_off(self):
        self.write(':OUTP OFF')
        self._output_on = False

    def _close(self):
        """Ramp to 0 V and turn the output off, then release the VISA session."""
        if self._output_on:
            self.write(':SOUR:VOLT 0')
            self.output_off()
        self.tool.close()

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Driver for the single-channel Keysight B2900B/BL source/measure units.

The B2901BL installed in the lab is a one-channel SMU.  Unlike a bench power
supply, it must be placed in either voltage-source or current-source mode and
the *other* quantity is a compliance limit.  This module intentionally does
not send ``*RST``: resetting an SMU can change its output configuration in ways
that are inappropriate for a connected DUT.
"""

import logging
from typing import Tuple

import pyvisa

from sw.lib.lab_instruments import instrument as inst


logger = logging.getLogger(__name__)


class KeysightSMUB2900(inst.BaseInstrument):
    """Control a one-channel B2900B/BL SMU over its LAN VISA endpoint.

    This lab setup is limited to +/-0.75 V and +/-1 A.  The limits apply to
    the magnitude of source setpoints; compliance is necessarily a positive
    magnitude.  They are enforced here as a final software guard.
    """

    MAX_VOLTAGE_V = 0.75
    MAX_CURRENT_A = 1.0

    def __init__(self, info: inst.BaseInstrumentData, verbose: bool = False):
        self._output_enabled = False
        self._source_mode = None
        super().__init__(info, verbose=verbose)

    def _open_resource(self):
        """Open the VXI-11 LAN VISA resource advertised by the instrument."""
        rm = pyvisa.ResourceManager()
        resource = f"TCPIP::{self.info.IP}::inst0::INSTR"
        logger.info("Reaching %s at: %s", self.info.name, resource)
        return rm.open_resource(resource)

    def _init_instrument(self):
        """Make a newly opened LAN session safe.

        LAN control is already remote; B2901BL does not accept ``SYST:REM``.
        No reset is performed.  Turning the output off is deliberate: the
        caller must explicitly invoke :meth:`enable_output` after configuring a
        source mode, setpoint, and compliance limit.
        """
        self.disable_output()

    @staticmethod
    def _validate_magnitude(value: float, maximum: float, name: str):
        if abs(value) > maximum:
            raise ValueError(
                f"{name} {value:g} exceeds the B2901BL limit of +/-{maximum:g}")

    @staticmethod
    def _validate_compliance(value: float, maximum: float, name: str):
        if value <= 0 or value > maximum:
            raise ValueError(
                f"{name} compliance must be in (0, {maximum:g}], got {value:g}")

    def set_current_source(self, current_a: float, voltage_compliance_v: float):
        """Configure DC current sourcing with a voltage compliance limit."""
        self._validate_magnitude(current_a, self.MAX_CURRENT_A, "Current")
        self._validate_compliance(
            voltage_compliance_v, self.MAX_VOLTAGE_V, "Voltage")
        self.write("SOUR:FUNC:MODE CURR")
        self.write("SOUR:CURR:RANG:AUTO ON")
        self.write(f"SENS:VOLT:PROT {voltage_compliance_v:.12g}")
        self._source_mode = "current"
        self.set_current(current_a)

    def set_voltage_source(self, voltage_v: float, current_compliance_a: float):
        """Configure DC voltage sourcing with a current compliance limit."""
        self._validate_magnitude(voltage_v, self.MAX_VOLTAGE_V, "Voltage")
        self._validate_compliance(
            current_compliance_a, self.MAX_CURRENT_A, "Current")
        self.write("SOUR:FUNC:MODE VOLT")
        self.write("SOUR:VOLT:RANG:AUTO ON")
        self.write(f"SENS:CURR:PROT {current_compliance_a:.12g}")
        self._source_mode = "voltage"
        self.set_voltage(voltage_v)

    def set_current(self, current_a: float):
        """Change a current-source setpoint without changing compliance.

        Call :meth:`set_current_source` first to select current source mode and
        establish the voltage compliance limit.
        """
        if self._source_mode != "current":
            raise RuntimeError("Configure current source mode before changing current")
        self._validate_magnitude(current_a, self.MAX_CURRENT_A, "Current")
        self.write(f"SOUR:CURR {current_a:.12g}")

    def set_voltage(self, voltage_v: float):
        """Change a voltage-source setpoint without changing compliance.

        Call :meth:`set_voltage_source` first to select voltage source mode and
        establish the current compliance limit.
        """
        if self._source_mode != "voltage":
            raise RuntimeError("Configure voltage source mode before changing voltage")
        self._validate_magnitude(voltage_v, self.MAX_VOLTAGE_V, "Voltage")
        self.write(f"SOUR:VOLT {voltage_v:.12g}")

    def enable_output(self):
        """Enable the already configured source output."""
        self.write("OUTP ON")
        self._output_enabled = True

    def disable_output(self):
        """Disable the source output without changing its configured values."""
        self.write("OUTP OFF")
        self._output_enabled = False

    def measure(self) -> Tuple[float, float]:
        """Return the present output ``(voltage_v, current_a)``."""
        return (
            float(self.query("MEAS:VOLT?")),
            float(self.query("MEAS:CURR?")),
        )

    def close(self, disable_output: bool = True):
        """Close the VISA connection, optionally preserving the output state.

        ``disable_output`` defaults to ``True`` for safe use in calibration
        code.  It may be set to ``False`` only after an explicit request to
        leave a successfully enabled output on after the process exits.
        """
        if self.tool is None:
            return
        try:
            if disable_output:
                self.disable_output()
        finally:
            self.tool.close()
            self.tool = None

    def _close(self):
        """Implement the base-class safe-close hook."""
        self.close()

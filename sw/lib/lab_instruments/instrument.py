# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

from dataclasses import dataclass, field

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

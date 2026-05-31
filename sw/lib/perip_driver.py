# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Command-layer driver for the periphery (DAC) write/read ports.
#
# Exposes the perip_controller command set (see fpga/src/verilog/perip_command_api.sv)
# as methods on top of the shared PortDriver, plus channel/voltage conveniences
# for the AD8802 (12-channel, 8-bit voltage-output TrimDAC).
#
# AD8802 transfer (single V_REF, midscale code 0x80 = V_REF/2):
#     volts = V_REF * code / 256          (code is 0..255)
#     code  = round(volts / V_REF * 256)  (clamped to 0..255)

from typing import List, Optional

from lib.port_driver import PortDriver
from lib.perip_command_api import (
    OP_WRITEBACK,
    make_command,
    cmd_dac_write,
    cmd_dac_reset,
)

# AD8802: 12 channels, 8-bit, full code range over [0, V_REF).
DAC_NUM_CHANNELS = 12
DAC_CODE_STEPS   = 256
DAC_MIDSCALE     = 0x80


def volts_to_code(volts: float, vref: float) -> int:
    """Convert a target voltage to an 8-bit DAC code (clamped to 0..255)."""
    code = int(round(volts / vref * DAC_CODE_STEPS))
    return max(0, min(0xFF, code))


def code_to_volts(code: int, vref: float) -> float:
    """Convert an 8-bit DAC code to its output voltage."""
    return vref * (code & 0xFF) / DAC_CODE_STEPS


class PeripDriver(PortDriver):
    """Drives the perip_controller (DAC) command set over a WritePort + ReadPort.

    Usable directly, or as a context manager that opens/closes both ports:

        with PeripDriver(WRITE_DEV, READ_DEV) as dac:
            dac.set_voltage(channel=1, volts=0.6, vref=1.2)
            dac.set_code(channel=2, code=0x80)
            print(dac.get_code(2))           # -> 128 (from the write cache)

    The AD8802 has no readback line, so the driver keeps a software cache of the
    last code written to each channel (purely host-side; nothing extra is sent to
    the FPGA). It is accurate as long as this driver is the only writer.
    """

    def __init__(self, write_dev: str, read_dev: str, width: int = 32) -> None:
        super().__init__(write_dev, read_dev, width)
        # Last code written per channel (None = unknown / never written).
        self._codes: List[Optional[int]] = [None] * DAC_NUM_CHANNELS

    # ---- raw command set (see perip_command_api.sv) ----
    def dac_write(self, addr: int, data: int, rstn: int = 1, shdn: int = 1) -> None:
        """Write one DAC register: a 12-bit {addr, data} load (Mode-3 SPI).

        rstn / shdn are the active-low control bits (default 1 = normal).
        """
        self._send_words(cmd_dac_write(addr, data, rstn, shdn))
        if 0 <= addr < DAC_NUM_CHANNELS:
            self._codes[addr] = data & 0xFF

    def dac_reset(self, shdn: int = 1) -> None:
        """Assert the hardware reset (drives dac_rstn low): all registers preset to
        midscale 0x80. Note this *holds* the DAC in reset (dac_rstn stays low)
        until the next write releases it (a write carries rstn=1)."""
        self._send_words(cmd_dac_reset(shdn))
        self._codes = [DAC_MIDSCALE] * DAC_NUM_CHANNELS

    def writeback(self, payload: int = 0xADBEE) -> Optional[int]:
        """Send one writeback command (opcode 0xFF); return the echoed word.

        The perip_controller loops the exact command word back into the read
        FIFO, so the returned value should equal the command that was sent. The
        marker + opcode occupy the top 12 bits, so the echoable payload is the
        low 20 bits ([19:0]).
        """
        return self._loopback(make_command(OP_WRITEBACK, payload))

    # ---- channel / voltage helpers (AD8802) ----
    def set_code(self, channel: int, code: int, shdn: int = 1) -> None:
        """Write an 8-bit code (0..255) to a DAC channel (0..11)."""
        self._check_channel(channel)
        self.dac_write(channel, code & 0xFF, rstn=1, shdn=shdn)

    def get_code(self, channel: int) -> Optional[int]:
        """Last code written to a channel (None if never written). Host-side cache."""
        self._check_channel(channel)
        return self._codes[channel]

    def set_voltage(self, channel: int, volts: float, vref: float, shdn: int = 1) -> int:
        """Set a channel to the code nearest to `volts` for the given V_REF.

        Returns the code actually written (clamped to 0..255).
        """
        code = volts_to_code(volts, vref)
        self.set_code(channel, code, shdn=shdn)
        return code

    def get_voltage(self, channel: int, vref: float) -> Optional[float]:
        """Output voltage implied by the last code written (None if unknown)."""
        code = self.get_code(channel)
        return None if code is None else code_to_volts(code, vref)

    def set_all_code(self, code: int, shdn: int = 1) -> None:
        """Write the same code to all 12 channels (normal operation, over SPI)."""
        for ch in range(DAC_NUM_CHANNELS):
            self.set_code(ch, code, shdn=shdn)

    def set_all_voltage(self, volts: float, vref: float, shdn: int = 1) -> None:
        """Set all channels to the code nearest to `volts` for the given V_REF."""
        code = volts_to_code(volts, vref)
        self.set_all_code(code, shdn=shdn)

    def midscale(self) -> None:
        """Set all channels to midscale 0x80 over SPI (vs. dac_reset's held RS_N)."""
        self.set_all_code(DAC_MIDSCALE)

    def reset(self, shdn: int = 1) -> None:
        """Alias for dac_reset() (hardware RS_N midscale preset, held until next write)."""
        self.dac_reset(shdn)

    def shutdown(self, on: bool = True) -> None:
        """Float the DAC outputs (SHDN, active low). SHDN travels with every
        command, so this issues a no-op write to out-of-range address 0xF: no
        register changes, only SHDN is updated."""
        self.dac_write(0xF, 0x00, rstn=1, shdn=(0 if on else 1))

    # ---- internal ----
    @staticmethod
    def _check_channel(channel: int) -> None:
        if not (0 <= channel < DAC_NUM_CHANNELS):
            raise ValueError("channel %d out of range 0..%d" % (channel, DAC_NUM_CHANNELS - 1))

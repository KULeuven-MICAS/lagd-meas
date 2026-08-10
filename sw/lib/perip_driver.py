# Copyright 2026 KU Leuven.
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

from typing import Optional

from sw.lib.port_driver import PortDriver
from sw.lib.perip_command_api import (
    OP_WRITEBACK,
    OP_S2P_READBACK,
    SCK_HZ,
    make_command,
    sck_half_for,
    cmd_dac_write,
    cmd_dac_write_loopback,
    cmd_dac_reset,
    cmd_config_dac_sck,
    cmd_config_s2p_sck,
    cmd_s2p_write,
    cmd_s2p_oe,
)

# AD8802: 12 channels, 8-bit, full code range over [0, V_REF).
DAC_NUM_CHANNELS = 12
DAC_CODE_STEPS   = 256
DAC_MIDSCALE     = 0x80

# Serial bits per transfer, used to size read timeouts. The DAC takes a 12-bit
# {addr,data} load; an S2P write/readback shifts 32 bits plus the LE pulse.
DAC_XFER_BITS = 12
S2P_XFER_BITS = 34


def default_timeout(bits, sck_hz):
    """Read timeout for a transfer of `bits` serial bits at `sck_hz`.

    Both serial clocks are runtime-configurable down to 50 Hz, where a 32-bit S2P
    scan takes most of a second -- a fixed timeout would report a phantom failure.
    The 3x factor covers host-side poll overhead; the constant covers the rest.
    """
    return bits / float(sck_hz) * 3.0 + 0.1


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
        self._codes = [None] * DAC_NUM_CHANNELS  # type: List[Optional[int]]
        # HV9308 S2P host-side cache: last value written, last OE state.
        self._s2p_value = None  # type: Optional[int]
        self._s2p_oe = False
        # Serial clock each device is currently running at.
        self.dac_sck_hz = float(SCK_HZ)
        self.s2p_sck_hz = float(SCK_HZ)

    # ---- runtime serial-clock configuration ----
    def set_dac_sck_hz(self, sck_hz: float) -> float:
        """Set the DAC SPI clock; return the rate actually achieved.

        The divider is integer and the hardware clamps to SCK_MIN_HZ..SCK_MAX_HZ,
        so the achieved rate can differ from the request. Applies to the next DAC
        transfer.
        """
        half, actual = sck_half_for(sck_hz)
        self._send_words(cmd_config_dac_sck(half))
        self.dac_sck_hz = actual
        return actual

    def set_s2p_sck_hz(self, sck_hz: float) -> float:
        """Set the HV9308 shift clock; return the rate actually achieved.

        Same clamping as set_dac_sck_hz. Note the HV9308 is only rated to 8 MHz,
        which the FPGA-side clamp does not enforce.
        """
        half, actual = sck_half_for(sck_hz)
        self._send_words(cmd_config_s2p_sck(half))
        self.s2p_sck_hz = actual
        return actual

    # ---- raw command set (see perip_command_api.sv) ----
    def dac_write(self, addr: int, data: int, rstn: int = 1, shdn: int = 1) -> None:
        """Write one DAC register: a 12-bit {addr, data} load (Mode-3 SPI).

        rstn / shdn are the active-low control bits (default 1 = normal).
        """
        self._send_words(cmd_dac_write(addr, data, rstn, shdn))
        if 0 <= addr < DAC_NUM_CHANNELS:
            self._codes[addr] = data & 0xFF

    def verify_dac_write(self, addr: int, data: int, rstn: int = 1,
                         shdn: int = 1) -> Optional[int]:
        """DAC write that echoes its command word back; return the echoed word.

        Performs the real DAC transfer (like dac_write) AND loops the command word
        into the read FIFO, so the returned value should equal the command sent:

            cmd = make_command(OP_DAC_LOOPBACK, ...)   # what was sent
            assert dac.verify_dac_write(addr, data) == cmd

        The AD8802 has no readback line, so this confirms the *command path* (the
        controller received and decoded exactly this {rstn,shdn,addr,data}), not
        the analog output. Returns None if no word came back within the timeout.
        """
        command_word = cmd_dac_write_loopback(addr, data, rstn, shdn)[0]
        echoed = self._loopback(command_word,
                                default_timeout(DAC_XFER_BITS, self.dac_sck_hz))
        if 0 <= addr < DAC_NUM_CHANNELS:
            self._codes[addr] = data & 0xFF
        return echoed

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

    # ---- HV9308 32-channel serial-to-parallel converter (S2P) ----
    def s2p_write(self, value: int) -> None:
        """Shift a 32-bit value into the HV9308 and latch it (S2P_WRITE).

        Bits are shifted MSB-first; the bit->channel/mirror mapping is the PCB's.
        With OE enabled the outputs follow the new latch immediately.
        """
        self._send_words(cmd_s2p_write(value))
        self._s2p_value = value & 0xFFFFFFFF

    def s2p_readback(self) -> Optional[int]:
        """Scan the HV9308 shift register out of its cascade Data Out (S2P_READBACK).

        Returns the 32-bit register content (the recirculating scan is non-
        destructive), or None on timeout. This reads what the HV9308 silicon
        actually holds -- the strongest digital check of the loaded value.
        """
        return self._loopback(make_command(OP_S2P_READBACK),
                              default_timeout(S2P_XFER_BITS, self.s2p_sck_hz))

    def s2p_verify(self, value: int) -> bool:
        """S2P_WRITE `value`, then READBACK and confirm the HV9308 captured it."""
        self.s2p_write(value)
        return self.s2p_readback() == (value & 0xFFFFFFFF)

    def s2p_output_enable(self, on: bool = True) -> None:
        """Set the HV9308 Output Enable (S2P_OE): True = outputs on, False = blank.

        Powers up blanked (OE=0); enable after loading a configuration.
        """
        self._send_words(cmd_s2p_oe(on))
        self._s2p_oe = bool(on)

    def s2p_reconfigure(self, value: int) -> None:
        """Safely re-load the HV9308: blank the outputs, write, then re-enable.

        Blanking (OE=0) around the latch update avoids a glitch on the outputs as
        they switch from the old configuration to the new one.
        """
        self.s2p_output_enable(False)
        self.s2p_write(value)
        self.s2p_output_enable(True)

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
            raise ValueError(f"channel {channel} out of range 0..{DAC_NUM_CHANNELS - 1}")

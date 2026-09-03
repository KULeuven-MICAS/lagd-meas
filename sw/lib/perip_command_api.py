# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# ISA of the periphery (DAC) controller
# Must stay in sync with fpga/src/verilog/perip_command_api.sv
#
# Same handshake framing as chip_command_api: a 32-bit word is decoded as a
# command only when its top nibble (the marker) equals 0xF. The DAC payload is
# fully contained in the single word (the DAC takes only a 12-bit {addr,data}
# load and returns nothing), so there are no follow-up words. S2P_WRITE is the one
# 2-word frame: a command word plus a raw 32-bit data word.
#
# Command word layout (only valid when marker == 0xF):
#   [31:28] marker : 0xF   ("this word is a command"; any other value is ignored)
#   [27:20] opcode : 0xFF -> writeback (echo the word to the read FIFO, no SPI);
#                    0x03 -> DAC transaction + echo the command word back;
#                    any other value -> perform a DAC transaction (no echo)
#   [19:14] reserved
#   [13]    rstn   : DAC reset (active low). 0 holds dac_rstn low and skips SPI.
#   [12]    shdn   : DAC shutdown (active low)
#   [11:8]  addr   : 4-bit DAC register address
#   [7:0]   data   : 8-bit register data

from typing import List

from sw.lib import clock_api
from sw.lib.clock_api import DAC_SCK, S2P_SCK

# Handshake marker and opcodes (mirror perip_command_api.sv / chip values).
CMD_MARKER       = 0xF
OP_DAC           = 0x00  # any opcode other than the ones below performs a DAC transaction
OP_DAC_LOOPBACK  = 0x03  # DAC transaction + echo the command word back into read FIFO
OP_CONFIG_DAC_SCK = 0x04  # set the DAC SPI clock half-period (payload = half)
OP_CONFIG_S2P_SCK = 0x05  # set the HV9308 shift clock half-period (payload = half)
OP_S2P_WRITE     = 0x10  # shift a 32-bit value into the HV9308 S2P + latch (2-word frame)
OP_S2P_READBACK  = 0x11  # scan the HV9308 shift register out of Data Out -> 1 word
OP_S2P_OE        = 0x12  # set the HV9308 Output Enable level (bit0)
OP_WRITEBACK     = 0xFF  # echo the command word back into the read FIFO (no SPI)

# Field positions inside the 32-bit command word.
MARKER_SHIFT = 28
OPCODE_SHIFT = 20
RSTN_BIT     = 13
SHDN_BIT     = 12
ADDR_SHIFT   = 8
# data occupies [7:0]


def make_command(opcode, payload=0) -> int:
    """Assemble a 32-bit command word.

    marker 0xF in [31:28], opcode in [27:20], payload in [19:0].
    """
    return ((CMD_MARKER & 0xF) << MARKER_SHIFT) \
         | ((opcode & 0xFF) << OPCODE_SHIFT) \
         | (payload & 0x000FFFFF)


def _dac_payload(addr, data, rstn, shdn) -> int:
    """Assemble the 20-bit DAC payload shared by the plain and loopback writes."""
    return ((rstn & 1) << RSTN_BIT) | ((shdn & 1) << SHDN_BIT) \
         | ((addr & 0xF) << ADDR_SHIFT) | (data & 0xFF)


def cmd_dac_write(addr, data, rstn=1, shdn=1) -> List[int]:
    """Word list for one DAC register write (a 12-bit {addr, data} load).

    rstn / shdn are the active-low control bits (default 1 = normal operation).
    Driving rstn=0 instead holds the DAC in reset and performs no SPI transfer.
    """
    return [make_command(OP_DAC, _dac_payload(addr, data, rstn, shdn))]


def cmd_dac_write_loopback(addr, data, rstn=1, shdn=1) -> List[int]:
    """Word list for a DAC write that also echoes its command word back.

    Same framing as cmd_dac_write but with opcode OP_DAC_LOOPBACK: the controller
    performs the real DAC transfer AND loops the exact command word into the read
    FIFO. Since the AD8802 has no readback, this confirms the controller received
    and decoded exactly this command -- the strongest available digital check.
    """
    return [make_command(OP_DAC_LOOPBACK, _dac_payload(addr, data, rstn, shdn))]


def cmd_dac_reset(shdn=1) -> List[int]:
    """Word list to hold the DAC in reset (rstn=0): drives dac_rstn low, no SPI."""
    payload = (0 << RSTN_BIT) | ((shdn & 1) << SHDN_BIT)
    return [make_command(OP_DAC, payload)]


def cmd_writeback(payload=0) -> List[int]:
    """Word list for a writeback loopback test (opcode 0xFF).

    The marker + opcode occupy the top 12 bits, so the echoable payload is the
    low 20 bits ([19:0]).
    """
    return [make_command(OP_WRITEBACK, payload)]


# ---- HV9308 32-channel serial-to-parallel converter (S2P) ----

def cmd_s2p_write(value) -> List[int]:
    """Two-word frame to shift a 32-bit value into the HV9308 and latch it.

    Word 0 is the S2P_WRITE command; word 1 is the raw 32-bit value (a data word,
    consumed by position -- no marker). Shifted MSB-first; the bit->channel/mirror
    mapping is the PCB's, handled by a (future) s2p_pack helper.
    """
    return [make_command(OP_S2P_WRITE), value & 0xFFFFFFFF]


def cmd_s2p_readback() -> List[int]:
    """Word list to scan the HV9308 shift register out of Data Out (echoes 1 word)."""
    return [make_command(OP_S2P_READBACK)]


def cmd_s2p_oe(on) -> List[int]:
    """Word list to set the HV9308 Output Enable (bit0): 1 = outputs on, 0 = blank."""
    return [make_command(OP_S2P_OE, 1 if on else 0)]


# ---- runtime clock configuration ----
BUS_CLK_HZ = clock_api.BUS_CLK_HZ    # xillydemo.v: CLK_HZ
SCK_HZ     = DAC_SCK.default_hz      # power-on default for BOTH the DAC and S2P clocks
SCK_MAX_HZ = DAC_SCK.max_hz          # hardware clamp: fastest selectable
SCK_MIN_HZ = DAC_SCK.min_hz          # hardware clamp: slowest selectable

SCK_HALF_MIN = DAC_SCK.half_min
SCK_HALF_MAX = DAC_SCK.half_max


def sck_half_for(sck_hz, bus_clk_hz=BUS_CLK_HZ):
    """Half-period in bus-clock cycles for a requested clock, and what you'll get.

    Returns (half, actual_hz), clamped to the same window the hardware enforces.
    The divider is integer, so the achieved rate is bus_clk_hz / (2*half) and
    generally differs from the request.

    NOTE the DAC and S2P knobs share identical bounds.
    """
    if bus_clk_hz != BUS_CLK_HZ:
        raise ValueError("bus_clk_hz is fixed by the bitstream; see clock_api")
    return DAC_SCK.half_for(sck_hz)


def cmd_config_dac_sck(sck_half) -> List[int]:
    """Word list to set the DAC SPI clock half-period (in bus-clock cycles).

    Takes effect on the next DAC transfer. Out-of-range values are clamped by the
    hardware, so the rate saturates rather than hanging the shift engine.
    """
    return [make_command(OP_CONFIG_DAC_SCK, DAC_SCK.check_half(sck_half))]


def cmd_config_s2p_sck(sck_half) -> List[int]:
    """Word list to set the HV9308 shift-clock half-period (in bus-clock cycles).

    Takes effect on the next S2P write or readback. Note the HV9308 itself is only
    rated to 8 MHz; the hardware clamp enforces the FPGA limit, not the device's.
    """
    return [make_command(OP_CONFIG_S2P_SCK, S2P_SCK.check_half(sck_half))]

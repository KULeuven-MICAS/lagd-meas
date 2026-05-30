# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# ISA of the periphery (DAC) controller
# Must stay in sync with fpga/src/verilog/perip_command_api.sv
#
# Same handshake framing as chip_command_api: a 32-bit word is decoded as a
# command only when its top nibble (the marker) equals 0xF. The DAC payload is
# fully contained in the single word (the DAC takes only a 12-bit {addr,data}
# load and returns nothing), so there are no follow-up words.
#
# Command word layout (only valid when marker == 0xF):
#   [31:28] marker : 0xF   ("this word is a command"; any other value is ignored)
#   [27:20] opcode : 0xFF -> writeback (echo the word to the read FIFO, no SPI);
#                    any other value -> perform a DAC transaction
#   [19:14] reserved
#   [13]    rstn   : DAC reset (active low). 0 holds dac_rstn low and skips SPI.
#   [12]    shdn   : DAC shutdown (active low)
#   [11:8]  addr   : 4-bit DAC register address
#   [7:0]   data   : 8-bit register data

# Handshake marker and opcodes (mirror perip_command_api.sv / chip values).
CMD_MARKER   = 0xF
OP_DAC       = 0x00  # any opcode other than WRITEBACK performs a DAC transaction
OP_WRITEBACK = 0xFF  # echo the command word back into the read FIFO (local)

# Field positions inside the 32-bit command word.
MARKER_SHIFT = 28
OPCODE_SHIFT = 20
RSTN_BIT     = 13
SHDN_BIT     = 12
ADDR_SHIFT   = 8
# data occupies [7:0]


def make_command(opcode, payload=0):
    """Assemble a 32-bit command word.

    marker 0xF in [31:28], opcode in [27:20], payload in [19:0].
    """
    return ((CMD_MARKER & 0xF) << MARKER_SHIFT) \
         | ((opcode & 0xFF) << OPCODE_SHIFT) \
         | (payload & 0x000FFFFF)


def cmd_dac_write(addr, data, rstn=1, shdn=1):
    """Word list for one DAC register write (a 12-bit {addr, data} load).

    rstn / shdn are the active-low control bits (default 1 = normal operation).
    Driving rstn=0 instead holds the DAC in reset and performs no SPI transfer.
    """
    payload = ((rstn & 1) << RSTN_BIT) | ((shdn & 1) << SHDN_BIT) \
            | ((addr & 0xF) << ADDR_SHIFT) | (data & 0xFF)
    return [make_command(OP_DAC, payload)]


def cmd_dac_reset(shdn=1):
    """Word list to hold the DAC in reset (rstn=0): drives dac_rstn low, no SPI."""
    payload = (0 << RSTN_BIT) | ((shdn & 1) << SHDN_BIT)
    return [make_command(OP_DAC, payload)]


def cmd_writeback(payload=0):
    """Word list for a writeback loopback test (opcode 0xFF).

    The marker + opcode occupy the top 12 bits, so the echoable payload is the
    low 20 bits ([19:0]).
    """
    return [make_command(OP_WRITEBACK, payload)]

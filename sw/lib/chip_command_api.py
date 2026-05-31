# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# ISA of the chip controller
# Must stay in sync with fpga/src/verilog/chip_command_api.sv
#
# A 32-bit word is decoded by the chip_controller as a command ONLY when its top
# nibble (the handshake marker) equals 0xF. Any other top nibble means the word
# is NOT a command (e.g. an address or a data word) and is passed through without
# decoding. The chip address space never reaches 0xF in the top nibble, so a real
# address can never be mistaken for a command.
#
# Command word layout (only valid when marker == 0xF):
#   [31:28] marker  : 0xF  (handshake: "this word is a command")
#   [27:20] opcode  : 8-bit operation code
#   [19:16] reserved
#   [15:0]  burst_length / opcode-specific payload
#
#  opcode | operation        | SPI-slave command byte issued on the Quad-SPI bus
#  -------+------------------+--------------------------------------------------
#  0x00   | CONFIG_CLK_RST   | (local only, no SPI transaction)
#  0x01   | CONFIG_SPI_SLAVE | SPI cmd 0x01 (write reg0, enable Quad-SPI)
#  0x02   | DATA_WRITE       | SPI cmd 0x02 (write mem), burst_length words
#  0x0B   | DATA_READ        | SPI cmd 0x0B (read mem),  burst_length words
#  0xFF   | WRITEBACK_FIFO   | (local only, echoes the command word back)

# Handshake marker: a 32-bit word is a command iff bits [31:28] == this value.
CMD_MARKER = 0xF

# Available OPCODEs (8b)
CONFIG_CLK_RST   = 0x00  # Configure chip_clk and chip_rstn (local)
CONFIG_SPI_SLAVE = 0x01  # Enable Quad-SPI on the slave (SPI cmd 0x01)
DATA_WRITE       = 0x02  # Write burst_length words        (SPI cmd 0x02)
DATA_READ        = 0x0B  # Read  burst_length words        (SPI cmd 0x0B)
WRITEBACK_FIFO   = 0xFF  # Loop the command word back into the read FIFO (local)

# Field positions inside the 32-bit command word
MARKER_SHIFT = 28
OPCODE_SHIFT = 20

# burst_length is a 16-bit field; the SPI slave supports up to 65535 words.
MAX_BURST_LEN = 0xFFFF


def make_command(opcode, payload=0):
    """Assemble a 32-bit command word.

    marker 0xF in [31:28], opcode in [27:20], payload in [19:0].
    For DATA_WRITE / DATA_READ the payload is the 16-bit burst_length.
    """
    return ((CMD_MARKER & 0xF) << MARKER_SHIFT) \
         | ((opcode & 0xFF) << OPCODE_SHIFT) \
         | (payload & 0x000FFFFF)


def cmd_config_clk_rst(chip_clk_en, chip_rstn):
    """Word list to set chip_clk_en (bit 1) and chip_rstn (bit 0)."""
    payload = ((chip_clk_en & 1) << 1) | (chip_rstn & 1)
    return [make_command(CONFIG_CLK_RST, payload)]


def cmd_config_spi_slave():
    """Word list to enable Quad-SPI on the SPI slave (write reg0 = 0x01)."""
    return [make_command(CONFIG_SPI_SLAVE)]


def cmd_write(addr, data_words):
    """Word list for a (burst) memory write.

    Frame: [command(len=N)] [start_addr] [data0] .. [data(N-1)].
    N == 1 is a single-word write; N > 1 is a burst to consecutive word
    addresses (start_addr, start_addr+4, ...). data_words may be a single int
    or a list of ints.
    """
    if isinstance(data_words, int):
        data_words = [data_words]
    n = len(data_words)
    if not (1 <= n <= MAX_BURST_LEN):
        raise ValueError(f"write length {n} out of range 1..{MAX_BURST_LEN}")
    return [make_command(DATA_WRITE, n), addr & 0xFFFFFFFF] \
         + [d & 0xFFFFFFFF for d in data_words]


def cmd_read(addr, length=1):
    """Word list for a (burst) memory read: [command(len=N)] [start_addr].

    The chip returns N 32-bit words on the read port, read from start_addr,
    start_addr+4, ...
    """
    if not (1 <= length <= MAX_BURST_LEN):
        raise ValueError(f"read length {length} out of range 1..{MAX_BURST_LEN}")
    return [make_command(DATA_READ, length), addr & 0xFFFFFFFF]


def cmd_writeback(payload=0):
    """Word list for a WRITEBACK_FIFO loopback test.

    Note: the marker + opcode occupy the top 12 bits, so the echoable payload is
    limited to the low 20 bits ([19:0]).
    """
    return [make_command(WRITEBACK_FIFO, payload)]

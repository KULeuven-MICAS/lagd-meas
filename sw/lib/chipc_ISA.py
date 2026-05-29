# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# ISA of the chip controller
# Must stay in sync with fpga/src/verilog/chip_command_api.sv
#
# The opcode occupies the 4 MSBs ([31:28]) of each 32-bit command word.

# Available OPCODEs (4b):
CONFIG_CLK_RST   = 0xA  # Configure chip_clk and chip_rstn
CONFIG_SPI_SLAVE = 0xB  # Configure the SPI slave
DATA_WRITE       = 0xC  # Write data to the chip (32b address + 32b data)
DATA_READ        = 0xD  # Read data from the chip (32b address -> 32b data)
WRITEBACK_FIFO   = 0xE  # Loop the command word straight back into the read FIFO

# Position of the opcode field inside the 32-bit command word
OPCODE_SHIFT = 28


def make_command(opcode, payload=0):
    """Assemble a 32-bit command word: opcode in [31:28], payload in [27:0]."""
    return ((opcode & 0xF) << OPCODE_SHIFT) | (payload & 0x0FFFFFFF)

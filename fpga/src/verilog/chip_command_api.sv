// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>

// OPCODE (start from 0xA. Other address is reserved for the chip)
enum bit[3:0] {
    CONFIG_CLK_RST            = 4'hA,  // Configure the chip_clk and chip_rstn
    CONFIG_SPI_SLAVE          = 4'hB,  // Configure the SPI slave
    DATA_WRITE                = 4'hC,  // Write data to the chip (32b address + 32b data)
    DATA_READ                 = 4'hD,  // Read data from the chip
    WRITEBACK_FIFO            = 4'hE   // Configure the chip_rstn
} e_chip_opcode;

// OPCODE DEPENDENT COMMANDS
// chip_command packet structure, one per opcode:
// always needs to be 32b wide!
typedef struct packed{
    bit[3:0]    opcode;        // 4b opcode
    bit[25:0]   empty;         // empty bits for future use
    bit         chip_clk_en;   // enable the chip_clk
    bit         chip_rstn;     // direct control chip_rstn
} chip_config_t;


// CHIP_COMMAND
// Create the chip_command typedef
// union makes that an t_chip_command can be interpret as any of the given 32b typedefs
typedef union packed{
    chip_config_t  chip_config;
    logic[31:0]   bitwise;
} chip_command_t;

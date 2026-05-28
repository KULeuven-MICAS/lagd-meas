// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>

// perip_command packet structure, always needs to be 32b wide!
typedef struct packed {
    bit valid;           // whether the command is valid
    bit writeback;       // whether to write back the command result to the FIFO
    bit [15:0] empty;    // empty bits for future use
    bit rstn;            // DAC reset control, active low
    bit shdn;            // DAC shutdown control, active low
    bit[3:0] addr;       // 4b address
    bit[7:0] data;       // 8b config data
} dac_config_t;

// Create the perip_command typedef
// union makes that an t_perip_command can be interpret as any of the given 32b typedefs
typedef union packed{
    dac_config_t      dac_config;
    logic[31:0]       bitwise;
} perip_command_t;

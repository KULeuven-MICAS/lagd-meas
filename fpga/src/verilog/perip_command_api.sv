// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>

// PERIPHERY (DAC) COMMAND API
// ---------------------------
// Uses the same handshake framing as chip_command_api.sv: a 32-bit word is
// decoded as a command only when its top nibble (the marker) equals 0xF, and the
// writeback path is selected by the 8-bit opcode (0xFF). The DAC payload is fully
// contained in the single word (the DAC takes only a 12-bit {addr,data} load and
// returns nothing), so there are no follow-up words.
//
// Command word layout (only valid when marker == 0xF):
//   [31:28] marker : 0xF  ("this word is a command"; any other value is ignored)
//   [27:20] opcode : 0xFF -> writeback (echo the word to the read FIFO, no SPI);
//                    any other value -> perform a DAC transaction
//   [19:14] reserved
//   [13]    rstn   : DAC reset (active low). 0 holds dac_rstn low and skips SPI.
//   [12]    shdn   : DAC shutdown (active low)
//   [11:8]  addr   : 4-bit DAC register address
//   [7:0]   data   : 8-bit register data

// Handshake marker and writeback opcode (mirror chip_command_api values).
localparam bit [3:0] PERIP_CMD_MARKER   = 4'hF;
localparam bit [7:0] PERIP_OP_WRITEBACK = 8'hFF;

// perip_command packet structure, always needs to be 32b wide!
typedef struct packed {
    bit [3:0]  marker;   // [31:28] command marker (0xF = valid command)
    bit [7:0]  opcode;   // [27:20] 0xFF = writeback, else DAC transaction
    bit [5:0]  empty;    // [19:14] empty bits for future use
    bit        rstn;     // [13] DAC reset control, active low
    bit        shdn;     // [12] DAC shutdown control, active low
    bit [3:0]  addr;     // [11:8] 4b address
    bit [7:0]  data;     // [7:0]  8b config data
} dac_config_t;

// Create the perip_command typedef
// union makes that a perip_command can be interpreted as any of the given 32b typedefs
typedef union packed{
    dac_config_t      dac_config;
    logic[31:0]       bitwise;
} perip_command_t;

// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// CHIP COMMAND API
// ----------------
// A 32-bit command word is decoded by the chip_controller ONLY when its top
// nibble (the handshake marker) equals 0xF. Any other top nibble means the word
// is NOT a command (e.g. an address or a data word) and is passed through
// without decoding. The chip address space never reaches 0xF in the top nibble,
// so a real address can never be mistaken for a command.
//
// Command word layout (only valid when marker == 0xF):
//   [31:28] marker  : 0xF  (handshake: "this word is a command")
//   [27:20] opcode  : 8-bit operation code (see table below)
//   [19:16] reserved
//   [15:0]  burst_length / opcode-specific payload
//
//  opcode | operation        | SPI-slave command byte issued on the Quad-SPI bus
//  -------+------------------+--------------------------------------------------
//  0x00   | CONFIG_CLK_RST   | (local only, no SPI transaction)
//  0x01   | CONFIG_SPI_SLAVE | SPI cmd 0x01 (write reg0, enable Quad-SPI)
//  0x02   | DATA_WRITE       | SPI cmd 0x02 (write mem), burst_length words
//  0x0B   | DATA_READ        | SPI cmd 0x0B (read mem),  burst_length words
//  0xFF   | WRITEBACK_FIFO   | (local only, echoes the command word back)
//
// Notes:
//   * DATA_WRITE / DATA_READ carry a 16-bit burst_length = number of 32-bit
//     words to transfer in one CS-low frame. burst_length == 1 is the single-
//     word case; > 1 is a burst. The SPI slave supports up to 65535 words in a
//     single frame, hence the 16-bit field.
//   * The opcode value deliberately mirrors the SPI-slave command byte for the
//     memory operations (0x02 / 0x0B) and the config write (0x01), so the
//     controller opcode and the on-wire SPI command stay consistent.

// OPCODE
enum bit [7:0] {
    CONFIG_CLK_RST   = 8'h00,  // Configure chip_clk and chip_rstn (local)
    CONFIG_SPI_SLAVE = 8'h01,  // Enable Quad-SPI on the slave (SPI cmd 0x01)
    DATA_WRITE       = 8'h02,  // Write burst_length words      (SPI cmd 0x02)
    DATA_READ        = 8'h0B,  // Read  burst_length words      (SPI cmd 0x0B)
    WRITEBACK_FIFO   = 8'hFF   // Echo command word to readback FIFO (local)
} e_chip_opcode;

// Handshake marker: a 32-bit word is a command iff bits [31:28] == this value.
localparam bit [3:0] CHIP_CMD_MARKER = 4'hF;

// OPCODE DEPENDENT COMMANDS
// One packed view per command class. marker[31:28] and opcode[27:20] sit at the
// same bit positions in every view so they can be read before the class of the
// command is known. Always 32b wide.

// CONFIG_CLK_RST payload
typedef struct packed {
    bit [3:0]  marker;       // [31:28] = 0xF
    bit [7:0]  opcode;       // [27:20]
    bit [17:0] empty;        // [19:2]  reserved for future use
    bit        chip_clk_en;  // [1]     enable the chip_clk
    bit        chip_rstn;    // [0]     direct control of chip_rstn
} chip_config_t;

// DATA_WRITE / DATA_READ payload
typedef struct packed {
    bit [3:0]  marker;        // [31:28] = 0xF
    bit [7:0]  opcode;        // [27:20]
    bit [3:0]  reserved;      // [19:16]
    bit [15:0] burst_length;  // [15:0]  number of 32-bit words (>= 1)
} chip_burst_t;

// CHIP_COMMAND
// union makes that a chip_command_t can be interpreted as any of the 32b views
typedef union packed {
    chip_config_t chip_config;
    chip_burst_t  chip_burst;
    logic [31:0]  bitwise;
} chip_command_t;

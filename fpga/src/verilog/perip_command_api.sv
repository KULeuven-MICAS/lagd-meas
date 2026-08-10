// Copyright 2026 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>

// PERIPHERY COMMAND API
// ---------------------
// The periphery controller drives TWO devices over the one 32-bit stream
// (/dev/xillybus_{write,read}_32_2), multiplexed by the 8-bit opcode:
//   * the on-board DAC (AD8802), and
//   * the HV9308 32-channel serial-to-parallel converter (S2P) that sets the
//     bias resistors of the current mirrors feeding the chip's analog pins.
//
// Same handshake framing as chip_command_api.sv: a 32-bit word is decoded as a
// command only when its top nibble (the marker) equals 0xF. The DAC commands are
// single self-contained words; the S2P_WRITE command is a 2-word frame (a command
// word followed by the 32-bit value), like chip_controller's command+data frames.
//
// Command word layout (only valid when marker == 0xF):
//   [31:28] marker : 0xF  ("this word is a command"; any other value is ignored)
//   [27:20] opcode : see the table below
//   ...payload depends on the opcode (DAC fields below; S2P uses a follow-up word)
//
//  opcode | name           | frame (host -> write FIFO)         | returns
//  -------+----------------+------------------------------------+----------------
//  0x00   | DAC write      | [cmd]                              | -
//  0x03   | DAC loopback   | [cmd]                              | echo [cmd]
//  0x04   | CONFIG_DAC_SCK | [cmd] (payload = half-period)      | -  (local only)
//  0x05   | CONFIG_S2P_SCK | [cmd] (payload = half-period)      | -  (local only)
//  0x10   | S2P_WRITE      | [cmd] [32-bit value]               | -  (shift+latch)
//  0x11   | S2P_READBACK   | [cmd]                              | 1 word (32 bits)
//  0x12   | S2P_OE         | [cmd] (bit0 = OE level)            | -
//  0xFF   | WRITEBACK      | [cmd]                              | echo [cmd]
//  other  | DAC transaction (no echo)
//
// CONFIG_DAC_SCK / CONFIG_S2P_SCK set the serial clock of one device at runtime.
//
// DAC command word fields (opcodes 0x00 / 0x03):
//   [19:14] reserved   [13] rstn (active low)   [12] shdn (active low)
//   [11:8]  addr (4b)  [7:0] data (8b)
//
// S2P notes:
//   * S2P_WRITE shifts the follow-up 32-bit value into the HV9308 MSB-first and
//     pulses LE to latch it. The bit->channel/mirror mapping is the PCB designer's
//     (handled host-side); the FPGA only fixes the MSB-first shift order.
//   * S2P_READBACK scans the shift register out of the HV9308's cascade Data Out,
//     recirculating (non-destructive, no LE), and returns the 32 bits as one word.
//   * S2P_OE sets the Output Enable level (bit0): 1 = outputs follow the latch,
//     0 = all outputs blanked. It powers up 0; software enables it after a write
//     and should blank (0) around any reconfiguration.

// Handshake marker and opcodes (mirror chip_command_api values).
localparam bit [3:0] PERIP_CMD_MARKER      = 4'hF;
localparam bit [7:0] PERIP_OP_DAC_LOOPBACK = 8'h03;  // DAC write + echo command word
localparam bit [7:0] PERIP_OP_CONFIG_DAC_SCK = 8'h04; // set DAC SPI clock half-period
localparam bit [7:0] PERIP_OP_CONFIG_S2P_SCK = 8'h05; // set S2P shift clock half-period
localparam bit [7:0] PERIP_OP_S2P_WRITE    = 8'h10;  // shift 32-bit value + latch
localparam bit [7:0] PERIP_OP_S2P_READBACK = 8'h11;  // scan SR out of Data Out -> 1 word
localparam bit [7:0] PERIP_OP_S2P_OE       = 8'h12;  // set Output Enable (bit0)
localparam bit [7:0] PERIP_OP_WRITEBACK    = 8'hFF;  // echo command word only (no SPI)

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

// CONFIG_DAC_SCK / CONFIG_S2P_SCK payload: serial clock half-period in bus-clock
// cycles. SCK = CLK_HZ / (2*sck_half); at CLK_HZ = 100 MHz, 50000 -> 1 kHz.
// Hardware clamps to [SCK_HALF_MIN, SCK_HALF_MAX].
typedef struct packed {
    bit [3:0]  marker;     // [31:28] = 0xF
    bit [7:0]  opcode;     // [27:20]
    bit [19:0] sck_half;   // [19:0]  half-period in clk_i cycles
} perip_sck_t;

// Create the perip_command typedef
// union makes that a perip_command can be interpreted as any of the given 32b typedefs
typedef union packed{
    dac_config_t      dac_config;
    perip_sck_t       perip_sck;
    logic[31:0]       bitwise;
} perip_command_t;

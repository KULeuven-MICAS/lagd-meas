// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>

// PLL COMMAND API
// ---------------
// Drives the Pomelo PLL test structure (lagd_clk_gen / pomelo_pll_wrap) over the
// 8-bit Xillybus stream (/dev/xillybus_{write,read}_8). The PLL holds a 47-bit
// configuration in two registers (see lagd_clk_gen.sv):
//   * a "shallow" shift register clocked by data_strb_i: each rising edge shifts
//     the chain toward the MSB with data_i entering bit 0;
//   * a "hidden" register clocked by cfg_vld_strb_i: each rising edge loads the
//     whole shallow register and presents it to the PLL.
//   * when data_strb_i AND cfg_vld_strb_i are high together, both registers are
//     asynchronously reset to pll_cfg_pkg::rst_pll_cfg().
// The FPGA drives only four signals to the PLL: clk_sel_i, data_strb_i, data_i,
// cfg_vld_strb_i. data_o (the shift-register MSB) is observed on the PCB/scope
// and is NOT wired back, so writeback/loopback here echo what software sent (the
// same semantics as chip_command_api / perip_command_api), not a device readback.
//
// Because the stream is 8-bit, a command is a multi-byte frame. The first byte is
// the header: top nibble is the marker (0xF = "this is a command"), bottom nibble
// is the opcode. Any header whose marker != 0xF is dropped.
//
// Frame layout:
//   byte 0      : header  = {marker[3:0]=0xF, opcode[3:0]}
//   byte 1..N   : opcode-dependent payload (N below)
//
//  opcode | header | name          | payload | action
//  -------+--------+---------------+---------+--------------------------------------
//  0x0    | 0xF0   | LOAD          | 6 bytes | shift 47 bits MSB-first, then commit
//  0x1    | 0xF1   | LOAD_LOOPBACK | 6 bytes | LOAD + echo the 6 payload bytes back
//  0x2    | 0xF2   | CLK_SEL       | 1 byte  | set static clk_sel (byte[0])
//  0x3    | 0xF3   | RESET         | 0 bytes | pulse both strobes -> reset PLL regs
//  0xF    | 0xFF   | WRITEBACK     | 0 bytes | echo the 0xFF header back (liveness)
//
// Payload bit/byte order (LOAD / LOAD_LOOPBACK): the 47-bit word is exactly the
// value produced by pll_cfg_pkg::pack_pll_cfg(), sent little-endian:
//   byte1 = packed[7:0], byte2 = packed[15:8], ... byte6 = {1'bx, packed[46:40]}.
// The controller shifts it MSB-first (packed[46] first, packed[0] last) so that
// the shallow register ends up equal to packed[46:0].

// Handshake marker: a header byte is a command iff bits [7:4] == this value.
localparam bit [3:0] PLL_CMD_MARKER       = 4'hF;

// Opcodes (header[3:0]). Sequential; WRITEBACK kept at 0xF so the header byte is
// 0xFF, matching the writeback convention of chip_command_api / perip_command_api.
localparam bit [3:0] PLL_OP_LOAD          = 4'h0;  // shift 47 bits + commit
localparam bit [3:0] PLL_OP_LOAD_LOOPBACK = 4'h1;  // LOAD + echo the 6 payload bytes
localparam bit [3:0] PLL_OP_CLK_SEL       = 4'h2;  // set clk_sel from 1 payload byte
localparam bit [3:0] PLL_OP_RESET         = 4'h3;  // pulse both strobes (reset regs)
localparam bit [3:0] PLL_OP_WRITEBACK     = 4'hF;  // echo header (no PLL action)

// Configuration geometry. PllCfgBits must equal $size(pll_cfg_pkg::pll_cfg_t).
localparam int unsigned PLL_CFG_BITS      = 47;
localparam int unsigned PLL_CFG_BYTES     = 6;     // ceil(47/8)

// Header byte view: {marker, opcode}.
typedef struct packed {
    bit [3:0] marker;   // [7:4] command marker (0xF = valid command)
    bit [3:0] opcode;   // [3:0] operation code (see table above)
} pll_header_t;

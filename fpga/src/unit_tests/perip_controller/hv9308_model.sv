// Copyright 2026 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Behavioural model of the HV9308/HV9408 32-channel serial-to-parallel converter:
// a 32-bit static shift register, 32 output latches, and Output Enable.
//   * Data shifts on the rising edge of clk: stage1 <= din, stage_i <= stage_{i-1};
//     Data Out (dout) reflects stage 32 (the far end / cascade output).
//   * LE high transfers the shift register into the latches (modelled on the LE
//     rising edge; the controller pulses LE only while the SR is static, so this
//     is equivalent to the device's level-sensitive transfer).
//   * OE high -> outputs follow the latch; OE low -> all outputs LOW (blanked).
// latch_o exposes the (OE-gated) output state for self-checking.

module hv9308_model (
    input  logic        din,
    input  logic        clk,
    input  logic        le,
    input  logic        oe,
    output logic        dout,
    output logic [31:0] latch_o   // OE-gated output state (for TB checks)
);

    logic [31:0] sr;    // shift register: sr[0]=stage1 (din), sr[31]=stage32 (dout)
    logic [31:0] lat;   // output latch

    always_ff @(posedge clk) sr  <= {sr[30:0], din};
    always_ff @(posedge le)  lat <= sr;

    assign dout    = sr[31];
    assign latch_o = oe ? lat : 32'b0;

endmodule

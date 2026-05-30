// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Behavioral model of the AD8802 12-channel, 8-bit TrimDAC for the
// perip_controller unit testbench.
//
//   * 3-wire SPI, no readback (SDI / CLK / CS only). CS active-low.
//   * SDI is sampled into a 12-bit shift register on every rising CLK edge while
//     CS is low. A serial word is {4-bit addr (MSB first), 8-bit data (MSB
//     first)}; if more than 12 bits arrive the leading ones are discarded (the
//     shift register keeps the last 12).
//   * On the CS rising edge the shift register is decoded and the addressed DAC
//     register (addr 0..11) is loaded. addr 12..15 are ignored.
//   * RS_N (rstn, active low) held low for >= RESET_NS presets all 12 registers
//     to 0x80 (midscale). A reset that is released early is ignored.
//   * SHDN (shdn, active low) floats the analog outputs -- not modelled here; the
//     testbench just checks the value the controller drives.

`timescale 1ns/1ps

module ad8802_model #(
    parameter int unsigned RESET_NS = 90
)(
    input logic clk,    // dac_clk  (CLK)
    input logic csb,    // dac_csb  (CS, active low)
    input logic sdi,    // dac_sdi  (SDI)
    input logic rstn,   // dac_rstn (RS_N, active low)
    input logic shdn    // dac_shdn (SHDN, active low) - captured only
);

    localparam logic [7:0] MIDSCALE = 8'h80;

    logic [7:0]  mem [12];
    logic [11:0] shiftreg;

    // Shift SDI in on the rising clock edge while selected.
    always @(posedge clk) begin
        if (csb === 1'b0)
            shiftreg <= {shiftreg[10:0], sdi};
    end

    // Latch the addressed DAC register on the CS rising edge.
    always @(posedge csb) begin
        if (!$isunknown(shiftreg) && (shiftreg[11:8] < 4'd12))
            mem[shiftreg[11:8]] <= shiftreg[7:0];
    end

    // Midscale preset: rstn must stay low for at least RESET_NS.
    always @(negedge rstn) begin : reset_proc
        fork
            begin : wait_low
                #(RESET_NS);
                if (rstn === 1'b0)
                    for (int i = 0; i < 12; i++) mem[i] = MIDSCALE;
            end
            begin : early_release
                @(posedge rstn);   // released before RESET_NS -> cancel
            end
        join_any
        disable fork;
    end

    // Scoreboard helper: read a register (X if never written/reset).
    function automatic logic [7:0] peek(input int idx);
        return mem[idx];
    endfunction

endmodule

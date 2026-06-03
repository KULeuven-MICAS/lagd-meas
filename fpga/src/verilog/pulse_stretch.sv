// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Pulse stretcher: turns a short (e.g. single-cycle) input event into a level
// that stays high for STRETCH_CYCLES clocks, so brief events become visible on
// an LED. A new pulse arriving while still stretched simply reloads the timer
// (retriggerable), so a stream of events holds the output continuously high.

module pulse_stretch #(
    parameter int STRETCH_CYCLES = 100_000_000  // 1 s at 100 MHz
)(
    input  logic clk_i,
    (* direct_reset = "yes" *) input logic rst_i,
    input  logic pulse_i,   // 1-cycle (or longer) event
    output logic level_o    // high for STRETCH_CYCLES after each pulse
);
    localparam int CW = $clog2(STRETCH_CYCLES + 1);
    logic [CW-1:0] cnt_r;

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i)           cnt_r <= '0;
        else if (pulse_i)    cnt_r <= STRETCH_CYCLES[CW-1:0]; // (re)load on event
        else if (cnt_r != 0) cnt_r <= cnt_r - 1'b1;
    end

    assign level_o = (cnt_r != 0);

endmodule

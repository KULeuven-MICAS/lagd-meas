// Copyright 2026 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// SHARED CLOCK-DIVIDER FUNCTIONS
// f = CLK_HZ / (2 * half)

// Saturate a requested half-period into [lo, hi].
//
// Everything is carried at 32 bits so one function serves the 20-bit command
// payloads and the PLL's 24-bit one alike; callers narrow the result to their
// own register width. `lo` must be >= 1 -- a zero half-period would make the
// counter never match its target and stall the engine forever.
function automatic logic [31:0] clk_half_clamp(input logic [31:0] req,
                                               input logic [31:0] lo,
                                               input logic [31:0] hi);
    if (req < lo)      clk_half_clamp = lo;
    else if (req > hi) clk_half_clamp = hi;
    else               clk_half_clamp = req;
endfunction

// Fastest permitted half-period for a given ceiling, floored at 1.
function automatic int clk_half_min_for(input int clk_hz, input int max_hz);
    clk_half_min_for = (clk_hz / max_hz / 2) < 1 ? 1 : (clk_hz / max_hz / 2);
endfunction

// Slowest permitted half-period for a given floor.
function automatic int clk_half_max_for(input int clk_hz, input int min_hz);
    clk_half_max_for = clk_hz / min_hz / 2;
endfunction

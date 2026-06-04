// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Behavioural model of the Pomelo PLL serial-configuration registers, mirroring
// the two-register structure in lagd_clk_gen.sv (lines 94-107) without pulling in
// the foundry standard cells / pll_cfg_pkg from the lagd-im repo:
//
//   * shallow (shift) register cfg_n  : 47 FFs clocked by data_strb_i. Each rising
//                                       edge shifts toward the MSB, data_i into bit 0
//                                       (cfg_n <= {cfg_n[W-2:0], data_i}).
//   * hidden register        cfg_p    : clocked by cfg_vld_strb_i, loads cfg_n.
//   * reset: when data_strb_i AND cfg_vld_strb_i are high together, the active-low
//            async reset cfg_rst_ni = ~(data_strb_i & cfg_vld_strb_i) loads both
//            registers with rst_pll_cfg() (reset dominates a coincident clock edge).
//   * data_o = cfg_n[W-1] (the shift-register MSB; observed on the PCB in silicon).
//
// The reset value reproduces pll_cfg_pkg::rst_pll_cfg() from
// lagd-im/target/syn/tech/tsmc7ff/rtl/pomelo_pll_wrap.sv (kept in sync by hand).

module pll_shift_model #(
    parameter int W = 47
) (
    input  logic         data_strb_i,
    input  logic         data_i,
    input  logic         cfg_vld_strb_i,
    output logic         data_o,
    output logic [W-1:0] cfg_shallow_o,   // cfg_n (shift register)
    output logic [W-1:0] cfg_hidden_o     // cfg_p (committed config -> drives PLL)
);

    // Active-low async reset: asserted only when BOTH strobes are high.
    wire rst_n = ~(data_strb_i & cfg_vld_strb_i);

    // rst_pll_cfg() replica (see pomelo_pll_wrap.sv:77-98).
    function automatic logic [W-1:0] rst_val();
        logic [W-1:0] r;
        r              = '0;
        r[0]           = 1'b0;        // fb_clk_oen
        r[1]           = 1'b0;        // pll_clk_o_en
        r[11 -: 10]    = '1;          // clk_div_val = all ones
        r[12]          = 1'b0;        // clk_div_en
        r[13]          = 1'b1;        // pdown_PD
        r[14]          = 1'b1;        // pdown_VCO
        r[17 -: 3]     = 3'b100;      // set_current
        r[20 -: 3]     = 3'b100;      // set_c1
        r[23 -: 3]     = 3'b100;      // set_c2
        r[26 -: 3]     = 3'b100;      // set_r1
        r[30 -: 4]     = 4'b1000;     // vco_tune_coarse
        r[34 -: 4]     = 4'b1000;     // vco_current_min
        r[38 -: 4]     = 4'b1000;     // vco_current_max
        r[40 -: 2]     = 2'b10;       // set_v_ctrl
        r[41]          = 1'b0;        // set_clk_out
        r[44 -: 3]     = 3'b100;      // set_div_freq
        r[46 -: 2]     = 2'b00;       // set_fb_mux
        return r;
    endfunction

    logic [W-1:0] cfg_n, cfg_p;

    // Shallow register: shift on data_strb rising edge, async reset dominant.
    always_ff @(posedge data_strb_i or negedge rst_n) begin
        if (!rst_n) cfg_n <= rst_val();
        else        cfg_n <= {cfg_n[W-2:0], data_i};
    end

    // Hidden register: load shallow on cfg_vld rising edge, async reset dominant.
    always_ff @(posedge cfg_vld_strb_i or negedge rst_n) begin
        if (!rst_n) cfg_p <= rst_val();
        else        cfg_p <= cfg_n;
    end

    assign data_o        = cfg_n[W-1];
    assign cfg_shallow_o = cfg_n;
    assign cfg_hidden_o  = cfg_p;

endmodule

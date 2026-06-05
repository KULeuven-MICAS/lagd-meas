// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Self-checking unit testbench for pll_controller (Pomelo PLL serial config).
//
//   +-------------+  8-bit bytes  +-----------------+  4 wires   +-----------------+
//   | input FIFO  |-------------->|                 |----------->|  pll_shift_model |
//   | model (TB)  |               |  pll_controller |  strb/data | (shallow+hidden  |
//   +-------------+               |     (DUT)       |  cfg_vld   |  registers)      |
//   +-------------+  echo bytes   |                 |  clk_sel   +-----------------+
//   | output FIFO |<--------------|                 |
//   | model (TB)  |               +-----------------+
//   +-------------+
//
// The model reproduces the PLL's two-register shift/commit/reset behaviour (see
// pll_shift_model.sv). The bench drives byte-framed commands (pll_command_api.sv)
// and checks: RESET loads the reset defaults; LOAD shifts the 47-bit word in
// MSB-first and commits it (cfg_hidden == word, pinning byte order and bit order);
// LOAD_LOOPBACK additionally echoes the 6 payload bytes; WRITEBACK echoes the
// 0xFF header without touching the PLL; CLK_SEL sets the static clk_sel output;
// non-0xF markers are dropped. An assertion monitor verifies the two strobes are
// never high together except during an intended RESET.
//
// STRB_HALF is set small here so each strobe phase is a few cycles (the pulse
// shape is identical to the 1 MHz hardware default, just faster to simulate).
//
// Command-API constants come from pll_command_api.sv (compiled first as the
// shared $unit scope - see the Makefile).

`timescale 1ns/1ps

module tb_pll_controller;

    localparam int  STRB_HALF  = 4;
    localparam int  W          = PLL_CFG_BITS;   // 47
    localparam time CLK_PERIOD = 10ns;

    // ---------------- clock / reset ----------------
    logic clk = 1'b0;
    logic rst = 1'b1;
    always #(CLK_PERIOD/2) clk = ~clk;

    // ---------------- DUT <-> FIFO wires ----------------
    logic       fifo_rd_en;
    logic       fifo_empty;
    logic [7:0] fifo_dout;
    logic       fifo_wr_en;
    logic       fifo_full;
    logic [7:0] fifo_din;

    // ---------------- DUT <-> PLL wires ----------------
    logic pll_clk_sel, pll_data_strb, pll_data, pll_cfg_vld, pll_data_o;

    // ---------------- DUT ----------------
    pll_controller #(
        .STRB_HALF (STRB_HALF)
    ) dut (
        .clk_i              (clk),
        .rst_i              (rst),
        .fifo_pll_rd_en_o   (fifo_rd_en),
        .fifo_pll_empty_i   (fifo_empty),
        .fifo_pll_dout_i    (fifo_dout),
        .fifo_pll_wr_en_o   (fifo_wr_en),
        .fifo_pll_full_i    (fifo_full),
        .fifo_pll_din_o     (fifo_din),
        .pll_clk_sel_o      (pll_clk_sel),
        .pll_data_strb_o    (pll_data_strb),
        .pll_data_o         (pll_data),
        .pll_cfg_vld_strb_o (pll_cfg_vld),
        .pll_data_i         (pll_data_o)      // closes the READBACK recirculation loop
    );

    // ---------------- PLL register model ----------------
    // The model's data_o (shallow-register MSB) feeds back into the DUT's
    // pll_data_i, so READBACK reads/recirculates through the real shift model.
    logic [W-1:0] cfg_shallow, cfg_hidden;
    pll_shift_model #(.W(W)) i_pll (
        .data_strb_i    (pll_data_strb),
        .data_i         (pll_data),
        .cfg_vld_strb_i (pll_cfg_vld),
        .data_o         (pll_data_o),
        .cfg_shallow_o  (cfg_shallow),
        .cfg_hidden_o   (cfg_hidden)
    );

    // ---------------- input FIFO model (non-fallthrough, pointer based) --------
    localparam int IN_DEPTH = 4096;
    logic [7:0]  in_mem [IN_DEPTH];
    int unsigned in_wr = 0;
    int unsigned in_rd = 0;
    assign fifo_empty = (in_wr == in_rd);
    always_ff @(posedge clk) begin
        if (fifo_rd_en && (in_wr != in_rd)) begin
            fifo_dout <= in_mem[in_rd % IN_DEPTH];
            in_rd     <= in_rd + 1;
        end
    end
    task automatic push_byte(input logic [7:0] b);
        in_mem[in_wr % IN_DEPTH] = b;
        in_wr = in_wr + 1;
    endtask

    // ---------------- output FIFO model ----------------
    logic [7:0] out_q [$];
    logic       force_full = 1'b0;
    assign fifo_full = force_full;
    always_ff @(posedge clk) begin
        if (!rst && fifo_wr_en && !fifo_full)
            out_q.push_back(fifo_din);
    end

    // ---------------- scoreboard ----------------
    int errors = 0;
    int checks = 0;
    logic expect_reset = 1'b0;   // set around an intended RESET (see interlock monitor)
    int   interlock_errs = 0;

    task automatic check_eq(input string name, input logic [63:0] got, input logic [63:0] exp);
        checks++;
        if (got !== exp) begin
            errors++;
            $error("[%0t] %s MISMATCH: got 0x%013X exp 0x%013X", $time, name, got, exp);
        end else begin
            $display("[%0t] %s OK: 0x%013X", $time, name, got);
        end
    endtask

    // ---------------- reset-value replica (pll_cfg_pkg::rst_pll_cfg) ----------
    function automatic logic [W-1:0] rst_val();
        logic [W-1:0] r;
        r           = '0;
        r[11 -: 10] = '1;        // clk_div_val
        r[13]       = 1'b1;      // pdown_PD
        r[14]       = 1'b1;      // pdown_VCO
        r[17 -: 3]  = 3'b100;    // set_current
        r[20 -: 3]  = 3'b100;    // set_c1
        r[23 -: 3]  = 3'b100;    // set_c2
        r[26 -: 3]  = 3'b100;    // set_r1
        r[30 -: 4]  = 4'b1000;   // vco_tune_coarse
        r[34 -: 4]  = 4'b1000;   // vco_current_min
        r[38 -: 4]  = 4'b1000;   // vco_current_max
        r[40 -: 2]  = 2'b10;     // set_v_ctrl
        r[44 -: 3]  = 3'b100;    // set_div_freq
        return r;
    endfunction

    // ---------------- sync helpers ----------------
    // Pending = a byte in the input FIFO, in flight in the adapter, or the
    // controller not back in IDLE (state encoding: IDLE == 0).
    task automatic wait_idle();
        @(posedge clk);
        while ((in_wr != in_rd) || dut.adapter_inst.rd_inflight === 1'b1 ||
               dut.fifo_rd_valid === 1'b1 || dut.state_current !== 4'd0)
            @(posedge clk);
        repeat (4) @(posedge clk);
    endtask

    task automatic get_out(output logic [7:0] b);
        int c = 0;
        while (out_q.size() == 0) begin
            @(posedge clk);
            if (++c > 200000) begin
                errors++;
                $error("[%0t] timeout waiting for readback byte", $time);
                b = 'x;
                return;
            end
        end
        b = out_q.pop_front();
    endtask

    // ---------------- transaction helpers ----------------
    // Split a 47-bit word into 6 little-endian payload bytes (top pad bit = 0).
    function automatic logic [7:0] cfg_byte(input logic [W-1:0] word, input int k);
        logic [PLL_CFG_BYTES*8-1:0] w48;
        w48 = {{(PLL_CFG_BYTES*8 - W){1'b0}}, word};
        return w48[k*8 +: 8];
    endfunction

    task automatic do_load(input logic [W-1:0] word, input bit loopback);
        logic [7:0] got;
        push_byte({PLL_CMD_MARKER, loopback ? PLL_OP_LOAD_LOOPBACK : PLL_OP_LOAD});
        for (int k = 0; k < PLL_CFG_BYTES; k++)
            push_byte(cfg_byte(word, k));
        if (loopback) begin
            for (int k = 0; k < PLL_CFG_BYTES; k++) begin
                get_out(got);                        // echoes arrive after the commit
                check_eq($sformatf("load_lb echo[%0d]", k), got, cfg_byte(word, k));
            end
        end
        wait_idle();
        check_eq("load cfg_hidden", cfg_hidden, word);
        check_eq("load cfg_shallow", cfg_shallow, word);
    endtask

    task automatic do_reset();
        expect_reset = 1'b1;
        push_byte({PLL_CMD_MARKER, PLL_OP_RESET});
        wait_idle();
        expect_reset = 1'b0;
        check_eq("reset cfg_hidden",  cfg_hidden,  rst_val());
        check_eq("reset cfg_shallow", cfg_shallow, rst_val());
    endtask

    task automatic do_clk_sel(input logic sel);
        push_byte({PLL_CMD_MARKER, PLL_OP_CLK_SEL});
        push_byte({7'b0, sel});
        wait_idle();
        check_eq("clk_sel", {63'b0, pll_clk_sel}, {63'b0, sel});
    endtask

    task automatic do_writeback();
        logic [7:0] got;
        push_byte({PLL_CMD_MARKER, PLL_OP_WRITEBACK});
        get_out(got);
        check_eq("writeback header", got, {PLL_CMD_MARKER, PLL_OP_WRITEBACK});
        wait_idle();
    endtask

    // READBACK: scan the shallow register out of data_o (recirculating) and check
    // the 6 returned bytes reconstruct `expect`. Also confirm the recirculation
    // preserved the shallow register and left the hidden register untouched.
    task automatic do_readback(input logic [W-1:0] exp_word);
        logic [7:0]   got;
        logic [W-1:0] hid_before;
        hid_before = cfg_hidden;
        push_byte({PLL_CMD_MARKER, PLL_OP_READBACK});
        for (int k = 0; k < PLL_CFG_BYTES; k++) begin
            get_out(got);
            check_eq($sformatf("readback byte[%0d]", k), got, cfg_byte(exp_word, k));
        end
        wait_idle();
        check_eq("readback preserves shallow", cfg_shallow, exp_word);
        check_eq("readback leaves hidden",     cfg_hidden,  hid_before);
    endtask

    // ---------------- strobe interlock monitor ----------------
    // Outside an intended RESET, the two strobes must never be high together
    // (that combination is the PLL's register reset).
    always @(posedge clk) begin
        if (!rst && pll_data_strb && pll_cfg_vld && !expect_reset) begin
            interlock_errs++;
            $error("[%0t] INTERLOCK: data_strb & cfg_vld both high outside RESET", $time);
        end
    end

    // ---------------- optional waveform dump ----------------
    initial begin
        if ($test$plusargs("dump")) begin
            $dumpfile("tb_pll_controller.vcd");
            $dumpvars(0, tb_pll_controller);
        end
    end

    // ---------------- main stimulus ----------------
    logic [W-1:0] hid_before;
    logic [7:0]   dummy;

    initial begin
        rst = 1'b1;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);

        // ---- 1. RESET from unknown state -> reset defaults ----
        $display("=== Test 1: RESET to defaults ===");
        do_reset();

        // ---- 2. LOAD: ordering-sensitive patterns ----
        $display("=== Test 2: LOAD patterns ===");
        do_load('0,                 1'b0);   // all zeros
        do_load({W{1'b1}},          1'b0);   // all ones
        do_load({{(W-1){1'b0}}, 1'b1}, 1'b0);             // only bit 0 (LSB)
        do_load({1'b1, {(W-1){1'b0}}}, 1'b0);             // only bit 46 (MSB)
        do_load(47'h2AAA_AAAA_AAAA, 1'b0);   // alternating
        do_load(47'h5555_5555_5555, 1'b0);   // alternating (other phase)
        do_load(rst_val(),          1'b0);   // a "realistic" packed config

        // ---- 3. LOAD_LOOPBACK: commit AND echo the 6 payload bytes ----
        $display("=== Test 3: LOAD_LOOPBACK ===");
        do_load(47'h1234_5678_9ABC, 1'b1);
        do_load(47'h7EDC_BA98_7654, 1'b1);

        // ---- 4. WRITEBACK: echo 0xFF, PLL config untouched ----
        $display("=== Test 4: WRITEBACK (liveness) ===");
        do_load(47'h0F0F_0F0F_0F0F, 1'b0);   // seed a known config
        hid_before = cfg_hidden;
        do_writeback();
        check_eq("writeback leaves cfg_hidden", cfg_hidden, hid_before);

        // ---- 5. CLK_SEL ----
        $display("=== Test 5: CLK_SEL ===");
        do_clk_sel(1'b1);
        do_clk_sel(1'b0);

        // ---- 6. marker drop: non-0xF top nibble is ignored ----
        $display("=== Test 6: marker drop ===");
        do_load(47'h7777_7777_7777, 1'b0);   // known config
        hid_before = cfg_hidden;
        push_byte(8'h12);                     // marker 0x1 != 0xF -> dropped
        push_byte(8'h34);                     // dropped too
        wait_idle();
        check_eq("marker drop: cfg unchanged", cfg_hidden, hid_before);
        check_eq("marker drop: no echo", {63'b0, (out_q.size() != 0)}, 64'd0);

        // ---- 7. READBACK: scan the shallow register out of data_o ----
        // LOAD a pattern, then READBACK and confirm the returned 47 bits match,
        // the shallow register is preserved (recirculated), and hidden untouched.
        $display("=== Test 7: READBACK (data_o scan) ===");
        do_load(47'h1234_5678_9ABC, 1'b0);  do_readback(47'h1234_5678_9ABC);
        do_load({W{1'b1}},          1'b0);  do_readback({W{1'b1}});            // all ones
        do_load('0,                 1'b0);  do_readback('0);                  // all zeros
        do_load({{(W-1){1'b0}}, 1'b1}, 1'b0); do_readback({{(W-1){1'b0}}, 1'b1}); // bit 0
        do_load({1'b1, {(W-1){1'b0}}}, 1'b0); do_readback({1'b1, {(W-1){1'b0}}}); // bit 46
        do_load(47'h2AAA_AAAA_AAAA, 1'b0);  do_readback(47'h2AAA_AAAA_AAAA);
        // Two readbacks in a row read the same value (recirculation is non-destructive).
        do_readback(47'h2AAA_AAAA_AAAA);

        // ---- 8. RESET after a LOAD: registers return to defaults ----
        $display("=== Test 8: RESET after LOAD ===");
        do_load({W{1'b1}}, 1'b0);
        do_reset();

        // ---- summary ----
        repeat (10) @(posedge clk);
        $display("==================================================");
        $display(" checks: %0d, errors: %0d, interlock_errs: %0d -> %s",
                 checks, errors, interlock_errs,
                 (errors == 0 && interlock_errs == 0) ? "PASS" : "FAIL");
        $display("==================================================");
        if (errors != 0 || interlock_errs != 0) $fatal(1, "testbench failed");
        $finish;
    end

    // global watchdog
    initial begin
        #5ms;
        $fatal(1, "global timeout");
    end

endmodule

// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Self-checking unit testbench for perip_controller (DAC path).
//
//   +-------------+  FIFO words  +-----------------+  3-wire SPI  +-----------+
//   | input FIFO  |------------->|                 |------------->|  AD8802   |
//   | model (TB)  |              | perip_controller|              |  model    |
//   +-------------+              |     (DUT)       |              | (12 regs) |
//   +-------------+  writeback   |                 |              +-----------+
//   | output FIFO |<-------------|                 |
//   | model (TB)  |              +-----------------+
//   +-------------+
//
// Besides functional checks (writeback, marker-drop, DAC register writes, shdn,
// reset path, midscale preset), a timing monitor verifies the AD8802 switching
// requirements on the SPI pins (clock pulse width, data setup/hold, CS<->clock).
//
// Command-word encoding comes from perip_command_api.sv (compiled first as the
// shared $unit scope - see the Makefile).

`timescale 1ns/1ps

module tb_perip_controller;

    localparam int  CLK_HZ     = 100_000_000;
    localparam int  SCK_HZ     = 25_000_000;
    localparam int  CSB_HOLD   = 4;
    localparam time CLK_PERIOD = 10ns;

    // ---------------- clock / reset ----------------
    logic clk = 1'b0;
    logic rst = 1'b1;
    always #(CLK_PERIOD/2) clk = ~clk;

    // ---------------- DUT <-> FIFO wires ----------------
    logic        fifo_rd_en;
    logic        fifo_empty;
    logic [31:0] fifo_dout;
    logic        fifo_wr_en;
    logic        fifo_full;
    logic [31:0] fifo_din;

    // ---------------- DUT <-> DAC wires ----------------
    logic dac_clk, dac_csb, dac_sdi, dac_shdn, dac_rstn;

    // ---------------- DUT ----------------
    perip_controller #(
        .CLK_HZ          (CLK_HZ),
        .SCK_HZ          (SCK_HZ),
        .CSB_HOLD_CYCLES (CSB_HOLD)
    ) dut (
        .clk_i              (clk),
        .rst_i              (rst),
        .fifo_perip_rd_en_o (fifo_rd_en),
        .fifo_perip_empty_i (fifo_empty),
        .fifo_perip_dout_i  (fifo_dout),
        .fifo_perip_wr_en_o (fifo_wr_en),
        .fifo_perip_full_i  (fifo_full),
        .fifo_perip_din_o   (fifo_din),
        .dac_clk_o          (dac_clk),
        .dac_csb_o          (dac_csb),
        .dac_sdi_o          (dac_sdi),
        .dac_shdn_o         (dac_shdn),
        .dac_rstn_o         (dac_rstn)
    );

    // ---------------- DAC model ----------------
    ad8802_model #(.RESET_NS(90)) i_dac (
        .clk  (dac_clk),
        .csb  (dac_csb),
        .sdi  (dac_sdi),
        .rstn (dac_rstn),
        .shdn (dac_shdn)
    );

    // ---------------- input FIFO model (non-fallthrough, pointer based) ----------------
    localparam int IN_DEPTH = 4096;
    logic [31:0] in_mem [IN_DEPTH];
    int unsigned in_wr = 0;
    int unsigned in_rd = 0;
    assign fifo_empty = (in_wr == in_rd);
    always_ff @(posedge clk) begin
        if (fifo_rd_en && (in_wr != in_rd)) begin
            fifo_dout <= in_mem[in_rd % IN_DEPTH];
            in_rd     <= in_rd + 1;
        end
    end
    task automatic push_word(input logic [31:0] w);
        in_mem[in_wr % IN_DEPTH] = w;
        in_wr = in_wr + 1;
    endtask

    // ---------------- output FIFO model ----------------
    logic [31:0] out_q [$];
    logic        force_full = 1'b0;
    assign fifo_full = force_full;
    always_ff @(posedge clk) begin
        if (!rst && fifo_wr_en && !fifo_full)
            out_q.push_back(fifo_din);
    end

    // ---------------- scoreboard ----------------
    int errors = 0;
    int checks = 0;

    task automatic check_eq(input string name, input logic [31:0] got, input logic [31:0] exp);
        checks++;
        if (got !== exp) begin
            errors++;
            $error("[%0t] %s MISMATCH: got 0x%08X exp 0x%08X", $time, name, got, exp);
        end else begin
            $display("[%0t] %s OK: 0x%08X", $time, name, got);
        end
    endtask

    // ---------------- command builders ----------------
    function automatic logic [31:0] make_dac_cmd(input logic [7:0] opcode, input logic rstn,
                                                 input logic shdn, input logic [3:0] addr,
                                                 input logic [7:0] data);
        return {PERIP_CMD_MARKER, opcode, 6'b0, rstn, shdn, addr, data};
    endfunction

    function automatic logic [31:0] make_wb_cmd(input logic [19:0] payload);
        return {PERIP_CMD_MARKER, PERIP_OP_WRITEBACK, payload};
    endfunction

    // ---------------- sync helpers ----------------
    // Pending = a word in the input FIFO, in flight in the adapter, the
    // controller not in IDLE, or the DAC engine still busy.
    task automatic wait_idle();
        @(posedge clk);
        while ((in_wr != in_rd) || dut.adapter_inst.rd_inflight === 1'b1 ||
               dut.fifo_rd_valid === 1'b1 || dut.state_current !== 2'd0 ||
               dut.dac_busy_o === 1'b1)
            @(posedge clk);
        repeat (4) @(posedge clk);
    endtask

    task automatic get_out(output logic [31:0] w);
        int c = 0;
        while (out_q.size() == 0) begin
            @(posedge clk);
            if (++c > 200000) begin
                errors++;
                $error("[%0t] timeout waiting for readback word", $time);
                w = 'x;
                return;
            end
        end
        w = out_q.pop_front();
    endtask

    // ---------------- transaction helpers ----------------
    task automatic do_dac_write(input logic [3:0] addr, input logic [7:0] data, input logic shdn = 1'b1);
        push_word(make_dac_cmd(8'h00, 1'b1, shdn, addr, data));
        wait_idle();
        check_eq($sformatf("dac mem[%0d]", addr), {24'h0, i_dac.mem[addr]}, {24'h0, data});
        check_eq("dac_shdn",  {31'h0, dac_shdn}, {31'h0, shdn});
        check_eq("dac_rstn",  {31'h0, dac_rstn}, 32'h1);
    endtask

    task automatic do_writeback(input logic [19:0] payload);
        logic [31:0] cmd_word, got;
        cmd_word = make_wb_cmd(payload);
        push_word(cmd_word);
        get_out(got);
        check_eq("writeback", got, cmd_word);
        wait_idle();
    endtask

    // ---------------- AD8802 timing monitor ----------------
    realtime t_cs_fall, t_clk_edge, t_clk_rise, t_sdi_change;
    int      rise_idx;
    int      csb_fall_count = 0;
    int      timing_errs = 0;

    task automatic terr(input string what, input realtime got, input realtime need);
        timing_errs++;
        $error("[%0t] TIMING %s: %0.1f ns < %0.1f ns", $time, what, got, need);
    endtask

    always @(negedge dac_csb) begin
        t_cs_fall  = $realtime;
        t_clk_edge = $realtime;
        rise_idx   = 0;
        csb_fall_count++;
    end

    always @(dac_sdi) begin
        if (dac_csb === 1'b0 && t_clk_rise > 0.0 && ($realtime - t_clk_rise) < 5.0)
            terr("t_DH(hold)", $realtime - t_clk_rise, 5.0);
        t_sdi_change = $realtime;
    end

    always @(dac_clk) begin
        if (dac_csb === 1'b0) begin
            if (dac_clk === 1'b1) begin                       // rising (sampling) edge
                if (rise_idx == 0) begin
                    if (($realtime - t_cs_fall) < 20.0) terr("t_CSS(CS->CLK)", $realtime - t_cs_fall, 20.0);
                end else begin
                    if (($realtime - t_clk_edge) < 15.0) terr("t_CL(low width)", $realtime - t_clk_edge, 15.0);
                end
                if (($realtime - t_sdi_change) < 5.0) terr("t_DS(setup)", $realtime - t_sdi_change, 5.0);
                t_clk_rise = $realtime;
                rise_idx++;
            end else if (rise_idx > 0) begin                  // falling edge (skip leading CS edge)
                if (($realtime - t_clk_edge) < 15.0) terr("t_CH(high width)", $realtime - t_clk_edge, 15.0);
            end
            t_clk_edge = $realtime;
        end
    end

    always @(posedge dac_csb) begin
        if (rise_idx > 0) begin
            if (dac_clk !== 1'b1) begin
                timing_errs++;
                $error("[%0t] TIMING: CLK not high at CS rising edge", $time);
            end
            if (($realtime - t_clk_rise) < 20.0) terr("t_CSH(CLK->CS)", $realtime - t_clk_rise, 20.0);
        end
    end

    // ---------------- optional waveform dump ----------------
    initial begin
        if ($test$plusargs("dump")) begin
            $dumpfile("tb_perip_controller.vcd");
            $dumpvars(0, tb_perip_controller);
        end
    end

    // ---------------- main stimulus ----------------
    int c0;
    logic [31:0] got;

    initial begin
        rst = 1'b1;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);

        // ---- 1. writeback ----
        $display("=== Test 1: writeback ===");
        do_writeback(20'hABCDE);
        do_writeback(20'h12345);

        // ---- 2. marker drop ----
        $display("=== Test 2: marker drop ===");
        push_word(32'h1234_5678);     // top nibble != 0xF -> ignored
        do_writeback(20'h0BEEF);      // must still loop back

        // ---- 3. DAC write to every register (addr 0..11) ----
        $display("=== Test 3: DAC write all registers ===");
        for (int a = 0; a < 12; a++)
            do_dac_write(a[3:0], 8'hA0 + a[7:0]);

        // ---- 4. data patterns on one register ----
        $display("=== Test 4: data patterns ===");
        do_dac_write(4'd5, 8'h00);
        do_dac_write(4'd5, 8'hFF);
        do_dac_write(4'd5, 8'hAA);
        do_dac_write(4'd5, 8'h55);

        // ---- 5. shutdown control bit ----
        $display("=== Test 5: shdn control ===");
        do_dac_write(4'd2, 8'h33, 1'b0);   // shdn = 0
        do_dac_write(4'd2, 8'h44, 1'b1);   // shdn = 1

        // ---- 6. addr out of range (12..15) -> DAC ignores ----
        $display("=== Test 6: out-of-range address ===");
        do_dac_write(4'd7, 8'h99);                 // seed a known reg
        push_word(make_dac_cmd(8'h00, 1'b1, 1'b1, 4'd13, 8'hEE));
        wait_idle();
        check_eq("oor leaves mem[7]", {24'h0, i_dac.mem[7]}, {24'h0, 8'h99});

        // ---- 7. reset path: rstn=0 drives dac_rstn low, no SPI ----
        $display("=== Test 7: reset path (no SPI) ===");
        c0 = csb_fall_count;
        push_word(make_dac_cmd(8'h00, 1'b0, 1'b1, 4'd0, 8'h00));   // rstn = 0
        wait_idle();
        check_eq("dac_rstn low",         {31'h0, dac_rstn}, 32'h0);
        check_eq("no SPI (no CS pulse)", (csb_fall_count == c0) ? 32'h0 : 32'h1, 32'h0);

        // ---- 8. midscale preset: rstn held low >= 90 ns -> all regs 0x80 ----
        $display("=== Test 8: midscale preset ===");
        #150;                                   // keep dac_rstn low past 90 ns
        for (int a = 0; a < 12; a++)
            check_eq($sformatf("preset mem[%0d]", a), {24'h0, i_dac.mem[a]}, {24'h0, 8'h80});

        // ---- 9. recover from reset and write again ----
        $display("=== Test 9: write after reset ===");
        do_dac_write(4'd9, 8'hC3);              // rstn=1 in this command restores RS_N

        // ---- summary ----
        repeat (10) @(posedge clk);
        $display("==================================================");
        $display(" checks: %0d, errors: %0d, timing_errs: %0d -> %s",
                 checks, errors, timing_errs,
                 (errors == 0 && timing_errs == 0) ? "PASS" : "FAIL");
        $display("==================================================");
        if (errors != 0 || timing_errs != 0) $fatal(1, "testbench failed");
        $finish;
    end

    // global watchdog
    initial begin
        #5ms;
        $fatal(1, "global timeout");
    end

endmodule

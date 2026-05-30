// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Self-checking unit testbench for chip_controller.
//
//   +-------------+   FIFO words   +-----------------+   Quad-SPI   +-----------+
//   | input FIFO  |--------------->|                 |<------------>|  spi      |
//   | model (TB)  |                | chip_controller |              |  slave    |
//   +-------------+                |     (DUT)       |              |  model    |
//   +-------------+   readback     |                 |              | (memory)  |
//   | output FIFO |<---------------|                 |              +-----------+
//   | model (TB)  |                +-----------------+
//   +-------------+
//
// The input FIFO model is a *non-fallthrough* (1-cycle read latency) standard
// FIFO, matching what fifo_to_axi_stream_adapter expects. The output FIFO model
// captures readback words and can assert `full` (incl. a pseudo-random stress
// mode) to exercise the read backpressure / SCK-pause path.
//
// Command-word encoding comes from chip_command_api.sv (compiled first as the
// shared $unit scope - see the Makefile `sim` target).

`timescale 1ns/1ps

module tb_chip_controller;

    localparam int  CLK_HZ     = 100_000_000;
    localparam int  SCK_HZ     = 25_000_000;
    localparam time CLK_PERIOD = 10ns;

    // ---------------- clock / reset ----------------
    logic clk = 1'b0;
    logic rst = 1'b1;           // active-high (direct_reset)
    always #(CLK_PERIOD/2) clk = ~clk;

    // ---------------- DUT <-> FIFO wires ----------------
    logic        fifo_chip_rd_en;
    logic        fifo_chip_empty;
    logic [31:0] fifo_chip_dout;
    logic        fifo_chip_wr_en;
    logic        fifo_chip_full;
    logic [31:0] fifo_chip_din;

    // ---------------- DUT <-> SPI bus wires ----------------
    logic        chip_sck, chip_csb;
    logic [3:0]  chip_sd_o, chip_sd_oe, chip_sd_i;
    logic        clk_chip, chip_arst_no;

    // ---------------- DUT ----------------
    chip_controller #(
        .CLK_HZ (CLK_HZ),
        .SCK_HZ (SCK_HZ)
    ) dut (
        .clk_i             (clk),
        .rst_i             (rst),
        .fifo_chip_rd_en_o (fifo_chip_rd_en),
        .fifo_chip_empty_i (fifo_chip_empty),
        .fifo_chip_dout_i  (fifo_chip_dout),
        .fifo_chip_wr_en_o (fifo_chip_wr_en),
        .fifo_chip_full_i  (fifo_chip_full),
        .fifo_chip_din_o   (fifo_chip_din),
        .chip_sck_o        (chip_sck),
        .chip_csb_o        (chip_csb),
        .chip_sd_i         (chip_sd_i),
        .chip_sd_o         (chip_sd_o),
        .chip_sd_oe_o      (chip_sd_oe),
        .clk_chip_o        (clk_chip),
        .chip_arst_no      (chip_arst_no)
    );

    // ---------------- SPI slave model ----------------
    spi_slave_model i_slave (
        .sck   (chip_sck),
        .csb   (chip_csb),
        .sd_o  (chip_sd_o),
        .sd_oe (chip_sd_oe),
        .sd_i  (chip_sd_i)
    );

    // ---------------- input FIFO model (non-fallthrough) ----------------
    // Pointer-based (not a SV queue): an xsim continuous assign is reliably
    // sensitive to scalar pointers, but NOT always to a queue's .size() — using
    // a queue here leaves `empty` stuck and stalls the whole DUT.
    localparam int IN_DEPTH = 4096;
    logic [31:0] in_mem [IN_DEPTH];
    int unsigned in_wr = 0;
    int unsigned in_rd = 0;
    assign fifo_chip_empty = (in_wr == in_rd);
    always_ff @(posedge clk) begin
        if (fifo_chip_rd_en && (in_wr != in_rd)) begin
            fifo_chip_dout <= in_mem[in_rd % IN_DEPTH];   // data valid one cycle after rd_en
            in_rd <= in_rd + 1;
        end
    end

    task automatic push_word(input logic [31:0] w);
        in_mem[in_wr % IN_DEPTH] = w;
        in_wr = in_wr + 1;
    endtask

    // ---------------- output FIFO model (+ optional full stress) ----------------
    logic [31:0] out_q [$];
    logic        force_full  = 1'b0;
    logic        stress_full = 1'b0;
    logic [3:0]  stress_ctr  = '0;

    always_ff @(posedge clk) stress_ctr <= stress_ctr + 1'b1;
    assign fifo_chip_full = force_full | (stress_full & stress_ctr[1]); // ~half the time

    always_ff @(posedge clk) begin
        if (!rst && fifo_chip_wr_en && !fifo_chip_full)
            out_q.push_back(fifo_chip_din);
    end

    // ---------------- scoreboard bookkeeping ----------------
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

    // ---------------- command-word helper ----------------
    function automatic logic [31:0] make_cmd(input logic [7:0] opcode, input logic [19:0] payload);
        return {CHIP_CMD_MARKER, opcode, payload};
    endfunction

    // Wait until the DUT has consumed the pushed frame and the SPI master is idle.
    // "Work pending" = a word still in the input FIFO, a word in flight inside
    // the adapter (fifo_rd_valid), the SPI master busy, or the controller not
    // yet back in IDLE. The adapter term is essential: when the FIFO pointers
    // drain, a word can still be sitting in the adapter before the controller
    // picks it up, so FIFO-empty + IDLE alone would report "done" too early.
    task automatic wait_idle();
        @(posedge clk);
        while ((in_wr != in_rd) || dut.fifo_rd_valid === 1'b1 ||
               dut.adapter_inst.rd_inflight === 1'b1 ||
               dut.spi_busy_o === 1'b1 || dut.state_current !== 4'd0)
            @(posedge clk);
        repeat (4) @(posedge clk);
    endtask

    // Pop one readback word with a cycle timeout.
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
    task automatic do_enable_quad();
        push_word(make_cmd(CONFIG_SPI_SLAVE, 20'h0));
        wait_idle();
    endtask

    task automatic do_clk_rst(input logic clk_en, input logic rstn);
        push_word(make_cmd(CONFIG_CLK_RST, {18'h0, clk_en, rstn}));
        wait_idle();
    endtask

    task automatic do_write(input logic [31:0] addr, input logic [31:0] data []);
        push_word(make_cmd(DATA_WRITE, data.size()));
        push_word(addr);
        foreach (data[i]) push_word(data[i]);
        wait_idle();
    endtask

    task automatic do_read(input logic [31:0] addr, input int n, output logic [31:0] res []);
        res = new[n];
        push_word(make_cmd(DATA_READ, n[19:0]));
        push_word(addr);
        for (int i = 0; i < n; i++) get_out(res[i]);
        wait_idle();
    endtask

    task automatic do_writeback(input logic [19:0] payload);
        logic [31:0] cmd_word, got;
        cmd_word = make_cmd(WRITEBACK_FIFO, payload);
        push_word(cmd_word);
        get_out(got);
        check_eq("writeback", got, cmd_word);
        wait_idle();
    endtask

    // ---------------- optional waveform dump ----------------
    // Enabled at run time with the +dump plusarg (Makefile: `make sim DUMP=1`).
    initial begin
        if ($test$plusargs("dump")) begin
            $dumpfile("tb_chip_controller.vcd");
            $dumpvars(0, tb_chip_controller);
        end
    end

    // ---------------- main stimulus ----------------
    logic [31:0] wdata [];
    logic [31:0] rdata [];

    initial begin
        // reset
        rst = 1'b1;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);

        // ---- 1. WRITEBACK loopback ----
        $display("=== Test 1: writeback ===");
        do_writeback(20'hABCDE);
        do_writeback(20'h12345);

        // ---- 2. CONFIG_CLK_RST drives the chip control pins ----
        $display("=== Test 2: config clk/rst ===");
        do_clk_rst(1'b1, 1'b0);
        check_eq("chip_arst_no(0)", {31'h0, chip_arst_no}, 32'h0);
        do_clk_rst(1'b1, 1'b1);
        check_eq("chip_arst_no(1)", {31'h0, chip_arst_no}, 32'h1);

        // ---- 3. Enable Quad-SPI on the slave ----
        $display("=== Test 3: enable quad ===");
        do_enable_quad();
        check_eq("en_quad", {31'h0, i_slave.en_quad}, 32'h1);

        // ---- 4. single-word write then read ----
        $display("=== Test 4: single write/read ===");
        wdata = new[1];
        wdata[0] = 32'hCAFEF00D;
        do_write(32'h0000_0010, wdata);
        do_read(32'h0000_0010, 1, rdata);
        check_eq("single rd", rdata[0], 32'hCAFEF00D);

        // ---- 5. burst write then burst read ----
        $display("=== Test 5: burst write/read ===");
        wdata = new[8];
        foreach (wdata[i]) wdata[i] = 32'hA0000000 + i;
        do_write(32'h0000_0100, wdata);
        do_read(32'h0000_0100, 8, rdata);
        foreach (rdata[i])
            check_eq($sformatf("burst rd[%0d]", i), rdata[i], wdata[i]);

        // ---- 6. burst read under output-FIFO backpressure ----
        $display("=== Test 6: burst read with backpressure ===");
        wdata = new[16];
        foreach (wdata[i]) wdata[i] = 32'hB0000000 + (i << 4);
        do_write(32'h0000_0200, wdata);
        stress_full = 1'b1;                 // randomly assert output-FIFO full
        do_read(32'h0000_0200, 16, rdata);
        stress_full = 1'b0;
        foreach (rdata[i])
            check_eq($sformatf("bp rd[%0d]", i), rdata[i], wdata[i]);

        // ---- 7. marker drop: a non-0xF word must be ignored ----
        $display("=== Test 7: marker drop ===");
        push_word(32'h1234_5678);           // top nibble != 0xF -> dropped
        do_writeback(20'h0BEEF);            // must still loop back correctly

        // ---- summary ----
        repeat (10) @(posedge clk);
        $display("==================================================");
        $display(" checks: %0d, errors: %0d -> %s", checks, errors,
                 (errors == 0) ? "PASS" : "FAIL");
        $display("==================================================");
        if (errors != 0) $fatal(1, "testbench failed");
        $finish;
    end

    // global watchdog
    initial begin
        #5ms;
        $fatal(1, "global timeout");
    end

endmodule

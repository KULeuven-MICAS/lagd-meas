// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Source file is written by Thomas Bos


module non_fallthrough_to_fallthrough #(int width)
  (
  input logic clk,
  (* direct_reset = "yes" *) input logic rst,

  //non fall through interface to fifo. When !fifo_empty && fifo_re, then the next cycle fifo_data is valid.
  input logic fifo_empty,
  input logic [width-1:0] fifo_data,
  output logic fifo_re,

  //fall through interface. When !output_empty, output_data is valid. It is discarded when output_re is high on the clock.
  output logic output_empty,
  output logic [width-1:0] output_data,
  input logic output_re
  );

  `REG(width, buffer, clk);
  assign buffer_next = fifo_data;

  logic buffer_re;
  logic buffer_full;
//  logic buffer_we;

  always @ (posedge clk or posedge rst) begin
    if(rst) begin
      buffer_full <= '0;
    end else begin
      buffer_full <= buffer_we || (buffer_full && !buffer_re);
    end
  end

  // delays for fifo_re and fifo_empty
  logic fifo_re_buf, fifo_empty_buf;
  reg_rst #(.WIDTH(1)) fifo_re_buf_inst(.clk(clk), .rst(rst), .din(output_re), .qout(fifo_re_buf), .wen(1));
  reg_rst #(.WIDTH(1)) fifo_empty_buf_inst(.clk(clk), .rst(rst), .din(fifo_empty), .qout(fifo_empty_buf), .wen(1));

  assign output_data = buffer_full ? buffer : fifo_data;

  //use buffer whenever we read something that is not read out at the output now
  assign buffer_we = fifo_re_buf && !fifo_empty_buf && (!output_re || buffer_full);
  assign fifo_re = output_re;
  assign buffer_re = output_re;

  assign output_empty = ! ((fifo_re_buf && !fifo_empty_buf) || buffer_full);


endmodule
`ifndef SYNTHESIS
module non_fallthrough_to_fallthrough_tb;


    logic clk = 0;
    logic rst;
    always #0.5ns clk = !clk;

    initial begin
      rst = 0;
      #1.1ns;
      rst = 1;
      #2ns;
      @(posedge clk);
      rst = 0;
    end

    mailbox #(logic [7:0]) fake_fifo_to_read = new();

    logic fake_fifo_empty;
    logic fake_fifo_re;
    logic [7:0] fake_fifo_data;
    task fake_fifo();
      while(1) begin
        int wait_cycles;
        logic [7:0] data;

        fake_fifo_empty <= 1;
        std::randomize(wait_cycles) with  {wait_cycles dist {0:=3, [1:10]:/3, [11:100]:/1};};
        repeat(wait_cycles) @(posedge clk);
        fake_fifo_empty <= 0;

        @(posedge clk iff fake_fifo_re);
        std::randomize(data);
        fake_fifo_data <= data;
        fake_fifo_to_read.put(data);
      end

    endtask;


    logic dut_empty;
    logic [7:0] dut_data;
    logic dut_re;
    non_fallthrough_to_fallthrough #(
      .width(8)
      )
      dut
      (
      .clk(clk),
      .rst(rst),
      .fifo_empty(fake_fifo_empty),
      .fifo_data(fake_fifo_data),
      .fifo_re(fake_fifo_re),
      .output_empty(dut_empty),
      .output_data(dut_data),
      .output_re(dut_re)
      );

    task read(output logic [7:0] out);
      $display("READ");
      dut_re <= 1;
      @(posedge clk iff !dut_empty);
      out = dut_data;
      dut_re = 0;
      $display("READ:  %08b", out);
    endtask;


    task reader;
      logic [7:0] read_word, correct_word;
      int wait_cycles;
      while(1) begin
        read(read_word);
        fake_fifo_to_read.get(correct_word);
        assert(read_word == correct_word) else begin $display("Read %08b =/= %08b correct", read_word, correct_word) ; $stop; end
        std::randomize(wait_cycles) with {wait_cycles dist {0:=4, [1:10]:/3, [11:100]:/1};};
        repeat(wait_cycles) @(posedge clk);
      end

    endtask;

    initial begin
      wait(rst);
      dut_re <= 0;
      fake_fifo_empty <= 1;
      wait(!rst);
      fork
        fake_fifo();
        reader();
        begin
          repeat (1000000) @(posedge clk);
          $finish;
        end
      join
    end

endmodule;
`endif

// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Source file is written by Thomas Bos
// Description:
// CHIP_CONTROLLER

// Processes the FIFO-CHIP commands as defined by the CHIP_COMMAND API

// CHANGELOG
// v1.0, 17-12-2021  Start basic controller with write_back functionality. (copied from previous repo)
//                   The afe_XX commands and signals are here to serve as an example


module chip_controller(
  input  clk,
  (* direct_reset = "yes" *) input  rst,

  // Connection to fifo
  // chip fifo input (from linux)
  (* mark_debug = "true" *) output reg        fifo_chip_rd_en,
  (* mark_debug = "true" *) input             fifo_chip_empty,
  (* mark_debug = "true" *) input  [31:0]     fifo_chip_dout,
  // chip fifo output (to linux)
  (* mark_debug = "true" *) output reg        fifo_chip_wr_en,
                            input             fifo_chip_full,
  (* mark_debug = "true" *) output reg [31:0] fifo_chip_din,

  // Project specific pins
  output reg afe_arstn_i  // _i naming = relative to chip (same FPGA IO names as chip IO)

  );

  /////////////////////////////////////
  ////    INSTRUCTION HANDLING     ////
  /////////////////////////////////////

  // make falltrough fifo for READ FIFO
  logic fifo_chip_ft_empty;
  (* mark_debug = "true" *) logic[31:0] fifo_chip_ft_dout;
  (* mark_debug = "true" *) logic fifo_chip_ft_re;
  non_fallthrough_to_fallthrough#(.width(32)) nftf_chip_inst(
    .clk          (clk),
    .rst          (rst),
    .fifo_empty   (fifo_chip_empty),
    .fifo_data    (fifo_chip_dout),
    .fifo_re      (fifo_chip_rd_en),
    .output_empty (fifo_chip_ft_empty),
    .output_data  (fifo_chip_ft_dout),
    .output_re    (fifo_chip_ft_re));

  // chip_command
  //  actual chip_command API: see chip_command_api.sv
  (* mark_debug = "true" *) chip_command_t  chip_command;
  (* mark_debug = "true" *) logic           chip_command_we;
  (* mark_debug = "true" *) logic [3:0]     chip_command_opcode;

  reg_rst #(.WIDTH(32)) chip_command_reg_inst (
    .clk  (clk),
    .rst  (rst),
    .din  (fifo_chip_ft_dout),
    .qout (chip_command.bitwise),
    .wen  (chip_command_we)
  );

  assign chip_command_opcode = chip_command.afe_config.opcode;

  /////////////////////////////////////
  ////    CHIP CONTROL MASTER FSM    ////
  /////////////////////////////////////
  // FSM STATE AND NEXTSTATE
  typedef enum {IDLE, PROCESS} chip_ctrl_state_t;
  (* mark_debug = "true" *) chip_ctrl_state_t CS;   // current state
  chip_ctrl_state_t NS;                             // next state

  always @(posedge clk) begin
      if(rst) begin
          CS <= IDLE;
      end else begin
          CS <= NS;
      end
  end

  // FSM CONTROL SIGNALS
  logic writeback_chip_command;   // writeback chip_command in writeback buffer
  logic update_afe_config;        // update all AFE_CONFIG regs

  // ACTUAL FSM
  always_comb begin
      // default values
      NS <= CS;
      writeback_chip_command  <= 0;
      update_afe_config       <= 0;
      // Xillybus FIFO control commands
      fifo_chip_ft_re <= 0;   // read enable
      chip_command_we <= 0;   // chip command write enable

      case(CS)
          IDLE: begin
              fifo_chip_ft_re <= 1;
              if(!fifo_chip_ft_empty) begin
                  NS <= PROCESS;
                  chip_command_we <= 1;
              end
          end
          PROCESS: begin
              case(chip_command_opcode)
                  AFE_CONFIG: begin
                      NS <= IDLE;
                      update_afe_config <= 1;
                  end
                  TEST_WRITEBACK_CHIPFIFO: begin
                      NS <= IDLE;
                      writeback_chip_command <= 1;
                  end
              endcase
          end

          default: begin
              NS <= IDLE;
          end
      endcase
  end

  /////////////////////////////////////
  ////    WRITE BACK BUFFER        ////
  /////////////////////////////////////
  // write back buffer
  always_comb begin
      // default value
      fifo_chip_wr_en <= 0;

      // enable fifo
      if(!fifo_chip_full && ( writeback_chip_command ) ) begin
          fifo_chip_wr_en <= 1;
      end

      // mux data
      if ( writeback_chip_command ) begin
        fifo_chip_din <= chip_command.bitwise;
      end else begin
        fifo_chip_din <= 'b0;
      end
  end

  /////////////////////////////////////
  ////        AFE_CONFIG           ////
  /////////////////////////////////////
  // Configure the main state of AFE
  //  At update_afe_config: copy all config from chip_command
  logic afe_clk_en;

  always_ff @(posedge clk) begin
      if (rst) begin
          afe_clk_en    <= 0;
          afe_arstn_i   <= 0;
      end else if (update_afe_config) begin
          afe_clk_en    <= chip_command.afe_config.afe_clk_en;
          afe_arstn_i   <= chip_command.afe_config.afe_rstn;
      end
  end



endmodule

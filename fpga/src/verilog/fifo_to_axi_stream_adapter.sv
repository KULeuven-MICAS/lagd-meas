// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
// The code is assisted by Gemini, 2026-05-27

module fifo_to_axi_stream_adapter #(parameter int DATA_WIDTH = 32) (
  input  logic                    clk_i,
  (* direct_reset = "yes" *) 
  input  logic                    rst_i,

  // Standard FIFO Interface (Non-Fallthrough)
  input  logic                    fifo_empty_i,
  input  logic [DATA_WIDTH-1:0]   fifo_rdata_i,
  output logic                    fifo_rden_o,

  // AXI-Stream / Valid-Ready Interface
  output logic                    m_axis_tvalid_o,
  input  logic                    m_axis_tready_i,
  output logic [DATA_WIDTH-1:0]   m_axis_tdata_o
);

  //----------------------------------------------------------------
  // Internal Registers & Signals
  //----------------------------------------------------------------
  logic [DATA_WIDTH-1:0] skid_data_reg;
  logic                  skid_valid_reg;
  logic                  fifo_data_phase;

  //----------------------------------------------------------------
  // Control Logic
  //----------------------------------------------------------------
  
  // Read from FIFO if it has data AND (downstream is ready OR skid buffer is empty)
  assign fifo_rden_o = !fifo_empty_i && (m_axis_tready_i || !skid_valid_reg);

  // Track if a read was requested in the previous cycle (data phase)
  always_ff @(posedge clk_i or posedge rst_i) begin
    if (rst_i) begin
      fifo_data_phase <= 1'b0;
    end else begin
      fifo_data_phase <= fifo_rden_o;
    end
  end

  // Output is valid if we have stalled data in the skid register OR new data just arrived
  assign m_axis_tvalid_o = skid_valid_reg || fifo_data_phase;

  // Prioritize the skid register data over the direct FIFO output
  assign m_axis_tdata_o  = skid_valid_reg ? skid_data_reg : fifo_rdata_i;

  //----------------------------------------------------------------
  // Skid Buffer Storage
  //----------------------------------------------------------------
  always_ff @(posedge clk_i or posedge rst_i) begin
    if (rst_i) begin
      skid_valid_reg <= 1'b0;
      skid_data_reg  <= '0;
    end else begin
      if (m_axis_tvalid_o && !m_axis_tready_i) begin
        // Downstream stall: catch incoming FIFO data before it overwrites the bus
        if (!skid_valid_reg && fifo_data_phase) begin
          skid_valid_reg <= 1'b1;
          skid_data_reg  <= fifo_rdata_i;
        end
      end else if (m_axis_tready_i) begin
        // Downstream consumed the data; clear the skid buffer
        skid_valid_reg <= 1'b0;
      end
    end
  end

endmodule

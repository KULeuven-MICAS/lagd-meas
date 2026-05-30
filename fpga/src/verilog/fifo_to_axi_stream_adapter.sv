// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Adapts a standard (non-fallthrough) FIFO read interface - where read data
// appears one cycle after `fifo_rden_o` is asserted - to an AXI-Stream
// valid/ready output.
//
// Implemented as a small DEPTH-entry FIFO that absorbs the source's 1-cycle
// read latency. A read is issued only when its result (arriving next cycle) is
// guaranteed a free slot, accounting for both the words already stored and any
// read already in flight; a concurrent pop frees a slot, so back-to-back reads
// sustain full throughput (one word per cycle) without ever dropping a word.
// DEPTH must be a power of two and >= 2 (2 fully hides the 1-cycle latency).

module fifo_to_axi_stream_adapter #(
  parameter int DATA_WIDTH = 32,
  parameter int DEPTH      = 2
) (
  input  logic                  clk_i,
  (* direct_reset = "yes" *)
  input  logic                  rst_i,

  // Standard FIFO interface (non-fallthrough)
  input  logic                  fifo_empty_i,
  input  logic [DATA_WIDTH-1:0] fifo_rdata_i,
  output logic                  fifo_rden_o,

  // AXI-Stream / valid-ready interface
  output logic                  m_axis_tvalid_o,
  input  logic                  m_axis_tready_i,
  output logic [DATA_WIDTH-1:0] m_axis_tdata_o
);

  localparam int PTRW = (DEPTH < 2) ? 1 : $clog2(DEPTH);

  logic [DATA_WIDTH-1:0] mem [DEPTH];
  logic [PTRW-1:0]       wr_ptr, rd_ptr;
  logic [PTRW:0]         count;        // occupancy, 0 .. DEPTH
  logic                  rd_inflight;  // a read was issued last cycle: data is on fifo_rdata_i now

  wire push = rd_inflight;                              // a read result lands this cycle
  wire pop  = m_axis_tvalid_o && m_axis_tready_i;       // downstream consumes a word

  assign m_axis_tvalid_o = (count != '0);
  assign m_axis_tdata_o  = mem[rd_ptr];

  // "committed" = words stored + read already in flight. Issue a new read only
  // if its result will have a slot; a pop happening this cycle frees one.
  wire [PTRW+1:0] committed = count + {{(PTRW+1){1'b0}}, rd_inflight};
  assign fifo_rden_o = !fifo_empty_i && (committed < (DEPTH + (pop ? 1 : 0)));

  always_ff @(posedge clk_i or posedge rst_i) begin
    if (rst_i) begin
      wr_ptr      <= '0;
      rd_ptr      <= '0;
      count       <= '0;
      rd_inflight <= 1'b0;
    end else begin
      rd_inflight <= fifo_rden_o;
      if (push) begin
        mem[wr_ptr] <= fifo_rdata_i;
        wr_ptr      <= wr_ptr + 1'b1;   // DEPTH is a power of two: wraps naturally
      end
      if (pop) begin
        rd_ptr <= rd_ptr + 1'b1;
      end
      case ({push, pop})
        2'b10:   count <= count + 1'b1;
        2'b01:   count <= count - 1'b1;
        default: count <= count;
      endcase
    end
  end

endmodule

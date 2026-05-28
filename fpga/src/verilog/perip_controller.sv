// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
// Assisted by Copilot (2026)
//
//   Upstream FIFO read interface
//             |
//             v
//   +-----------------------------+
//   | FIFO-to-AXI-stream adapter  |
//   +-----------------------------+
//             |
//             v
//   +-----------------------------+
//   |        State machine        |
//   +-----------------------------+
//        |                     |
//        v                     v
//   DAC SPI interface     FIFO write interface
//
//   The module reads 32-bit command words from the upstream FIFO via the
//   `fifo_to_axi_stream_adapter` and converts the FIFO input into a streaming
//   handshake for the controller FSM. The FSM decodes each word and routes the
//   transaction as follows:
//   - If `valid` is low the word is ignored.
//   - If `writeback` is set the controller writes the full 32-bit word back to
//     the output FIFO and skips the DAC transaction.
//   - If `rstn` is deasserted the controller drives `dac_rstn_o` low and does
//     not start an SPI transfer.
//   - Otherwise the controller starts `dac_spi_driver` to perform a 12-bit
//     MSB-first transfer (`addr[3:0]` concatenated with `data[7:0]`). The DAC
//     engine implements Mode-3 SPI (CPOL=1/CPHA=1): clock idles high, data is
//     updated on the falling edge and sampled on the rising edge. The engine
//     holds CSB low for a parameterized number of cycles after the final bit
//     to meet device timing requirements.

module perip_controller #(
    parameter int CLK_HZ = 100_000_000,
    parameter int SCK_HZ = 25_000_000,
    parameter int CSB_HOLD_CYCLES = 4 // in terms of cycles under CLK_HZ
)(
    input  clk_i,
    (* direct_reset = "yes" *) input logic rst_i,

    // FIFO read intface
    (* mark_debug = "true" *) output logic        fifo_perip_rd_en_o,
    (* mark_debug = "true" *) input               fifo_perip_empty_i,
    (* mark_debug = "true" *) input  [31:0]       fifo_perip_dout_i,
    // FIFO write interface
    (* mark_debug = "true" *) output logic        fifo_perip_wr_en_o,
    (* mark_debug = "true" *) input               fifo_perip_full_i,
    (* mark_debug = "true" *) output logic [31:0] fifo_perip_din_o,

    // Specific dac interface
    (* mark_debug = "true" *) output logic dac_clk_o,
    (* mark_debug = "true" *) output logic dac_csb_o,
    (* mark_debug = "true" *) output logic dac_sdi_o,
    (* mark_debug = "true" *) output logic dac_shdn_o,
    (* mark_debug = "true" *) output logic dac_rstn_o
);

    typedef enum logic [1:0] {
        IDLE,
        DECODE,
        WRITEBACK_WAIT,
        DAC_WAIT
    } perip_state_t;

    (* mark_debug = "true" *) perip_state_t state_current;
    (* mark_debug = "true" *) logic [31:0] fifo_word_r;

    // Command decoded via typedef in perip_command_api.sv
    (* mark_debug = "true" *) perip_command_t fifo_cmd_r;

    logic fifo_rd_valid;
    logic [31:0] fifo_rd_dout;
    logic fifo_rd_ready;

    logic dac_load_o;
    logic dac_busy_o;

    // fifo_cmd_r.bitwise mirrors fifo_word_r (updated in the FSM)
    fifo_to_axi_stream_adapter#(
            .DATA_WIDTH(32)
        ) adapter_inst (
            .clk_i           (clk_i              ),
            .rst_i           (rst_i              ),
            .fifo_empty_i    (fifo_perip_empty_i ),
            .fifo_rdata_i    (fifo_perip_dout_i  ),
            .fifo_rden_o     (fifo_perip_rd_en_o ),
            .m_axis_tvalid_o (fifo_rd_valid      ),
            .m_axis_tdata_o  (fifo_rd_dout       ),
            .m_axis_tready_i (fifo_rd_ready      )
    );

    dac_spi_driver #(
        .CLK_HZ(CLK_HZ),
        .SCK_HZ(SCK_HZ),
        .CSB_HOLD_CYCLES(CSB_HOLD_CYCLES)
    ) dac_driver_inst (
        .clk_i       (clk_i              ),
        .rst_i       (rst_i              ),
        .load_i      (dac_load_o         ),
        .rstn_i      (fifo_cmd_rstn_r    ),
        .shdn_i      (fifo_cmd_shdn_r    ),
        .addr_i      (fifo_cmd_addr_r    ),
        .data_i      (fifo_cmd_data_r    ),
        .busy_o      (dac_busy_o         ),
        .dac_clk_o   (dac_clk_o          ),
        .dac_csb_o   (dac_csb_o          ),
        .dac_sdi_o   (dac_sdi_o          ),
        .dac_shdn_o  (dac_shdn_o         ),
        .dac_rstn_o  (dac_rstn_o         )
    );

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current      <= IDLE;
            fifo_word_r        <= '0;
            fifo_perip_wr_en_o <= 1'b0;
            fifo_perip_din_o   <= '0;
            fifo_rd_ready      <= 1'b0;
            dac_load_o         <= 1'b0;
        end else begin
            fifo_perip_wr_en_o <= 1'b0;
            fifo_perip_din_o   <= '0;
            fifo_rd_ready      <= 1'b0;
            dac_load_o         <= 1'b0;

            case (state_current)
                IDLE: begin
                    fifo_rd_ready <= 1'b1;
                    if (fifo_rd_valid) begin
                        fifo_word_r   <= fifo_rd_dout;
                        fifo_cmd_r.bitwise <= fifo_rd_dout;
                        state_current <= DECODE;
                    end
                end

                DECODE: begin
                    if (!fifo_cmd_r.dac_config.valid) begin
                        state_current <= IDLE;
                    end else if (fifo_cmd_r.dac_config.writeback) begin
                        state_current <= WRITEBACK_WAIT;
                    end else begin
                        dac_load_o <= 1'b1;
                        if (fifo_cmd_r.dac_config.rstn) begin
                            state_current <= DAC_WAIT;
                        end else begin
                            state_current <= IDLE;
                        end
                    end
                end

                WRITEBACK_WAIT: begin
                    if (!fifo_perip_full_i) begin
                        fifo_perip_din_o   <= fifo_word_r;
                        fifo_perip_wr_en_o <= 1'b1;
                        state_current      <= IDLE;
                    end
                end

                DAC_WAIT: begin
                    if (!dac_busy_o) begin
                        state_current <= IDLE;
                    end
                end

                default: begin
                    state_current <= IDLE;
                end
            endcase
        end
    end



endmodule

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
//   SPI interface        FIFO write interface
//
//   The module reads commands/data from the upstream FIFO, converts the FIFO
//   input into a streaming handshake, and routes each transaction either to the
//   SPI master or to the output FIFO for writeback.
//
//   Command framing: a 32-bit FIFO word is decoded as a command only when its
//   top nibble (handshake marker) equals CHIP_CMD_MARKER (0xF); see
//   chip_command_api.sv. DATA_WRITE / DATA_READ carry a 16-bit burst length
//   (number of 32-bit words); length 1 is the single-word case, > 1 is a burst.
//   Data words are streamed to/from the SPI master with backpressure: for a
//   write the input FIFO feeds the master; for a read the master feeds the
//   output FIFO, and a full output FIFO pauses the SPI clock (no data loss).

module chip_controller#(
    parameter int CLK_HZ = 100_000_000,
    parameter int SCK_HZ = 25_000_000
)(
    input  logic clk_i,
    (* direct_reset = "yes" *) input  logic rst_i,
    // FIFO read intface
    (* mark_debug = "true" *) output logic       fifo_chip_rd_en_o,
    (* mark_debug = "true" *) input  logic       fifo_chip_empty_i,
    (* mark_debug = "true" *) input  logic [31:0] fifo_chip_dout_i,
    // FIFO write interface
    (* mark_debug = "true" *) output logic       fifo_chip_wr_en_o,
    (* mark_debug = "true" *) input  logic       fifo_chip_full_i,
    (* mark_debug = "true" *) output logic [31:0] fifo_chip_din_o,
    // Quad-SPI interface to chip
    output logic chip_sck_o,
    output logic chip_csb_o,
        input  logic [3:0] chip_sd_i,
        output logic [3:0] chip_sd_o,
        output logic [3:0] chip_sd_oe_o,
    // control signals to chip
    output logic clk_chip_o,
    output logic chip_arst_no
  );

    typedef enum logic [3:0] {
        IDLE,
        DECODE_CMD,
        FETCH_DATA_ADDR,
        SPI_CFG_START,
        SPI_CFG_WAIT,
        SPI_WRITE_START,
        SPI_WRITE_STREAM,
        SPI_READ_START,
        SPI_READ_STREAM,
        WRITEBACK_PUSH
    } chip_ctrl_state_t;

    (* mark_debug = "true" *) chip_ctrl_state_t state_current;
    (* mark_debug = "true" *) logic [31:0] cmd_word_r;
    (* mark_debug = "true" *) logic [31:0] addr_word_r;
    (* mark_debug = "true" *) logic [15:0] burst_len_r;

    (* mark_debug = "true" *) logic fifo_rd_valid;
    (* mark_debug = "true" *) logic [31:0] fifo_rd_dout;
    (* mark_debug = "true" *) logic fifo_rd_ready;

    (* mark_debug = "true" *) logic chip_clk_en_r;
    (* mark_debug = "true" *) logic chip_rstn_r;

    // Registered SPI master control
    (* mark_debug = "true" *) logic spi_start_o;
    (* mark_debug = "true" *) logic spi_quad_mode_o;
    (* mark_debug = "true" *) logic spi_read_dir_o;
    (* mark_debug = "true" *) logic [7:0]  spi_cmd_o;
    (* mark_debug = "true" *) logic [31:0] spi_addr_o;
    (* mark_debug = "true" *) logic [15:0] spi_len_o;
    (* mark_debug = "true" *) logic [31:0] spi_data_o;   // config data byte (reg0 value)

    // SPI master streaming data path (combinational)
    (* mark_debug = "true" *) logic [31:0] spi_wdata;
    (* mark_debug = "true" *) logic spi_wdata_valid;
    (* mark_debug = "true" *) logic spi_wdata_ready;
    // SPI master status / read stream
    (* mark_debug = "true" *) logic spi_busy_o;
    (* mark_debug = "true" *) logic spi_done_o;
    (* mark_debug = "true" *) logic spi_read_valid;
    (* mark_debug = "true" *) logic spi_read_ready;
    (* mark_debug = "true" *) logic [31:0] spi_read_data;

    fifo_to_axi_stream_adapter#(
            .DATA_WIDTH      (32               ),
            .DEPTH           (2                )
        ) adapter_inst (
            .clk_i           (clk_i            ),
            .rst_i           (rst_i            ),
            .fifo_empty_i    (fifo_chip_empty_i),
            .fifo_rdata_i    (fifo_chip_dout_i ),
            .fifo_rden_o     (fifo_chip_rd_en_o),
            .m_axis_tvalid_o (fifo_rd_valid    ),
            .m_axis_tdata_o  (fifo_rd_dout     ),
            .m_axis_tready_i (fifo_rd_ready    )
    );

    quad_spi_master #(
        .CLK_HZ       (CLK_HZ          ),
        .SCK_HZ       (SCK_HZ          )
    ) spi_master_inst (
        .clk_i        (clk_i           ),
        .rst_i        (rst_i           ),
        .start_i      (spi_start_o     ),
        .quad_mode_i  (spi_quad_mode_o ),
        .read_i       (spi_read_dir_o  ),
        .cmd_i        (spi_cmd_o       ),
        .addr_i       (spi_addr_o      ),
        .len_i        (spi_len_o       ),
        .wdata_i      (spi_wdata       ),
        .wdata_valid_i(spi_wdata_valid ),
        .wdata_ready_o(spi_wdata_ready ),
        .busy_o       (spi_busy_o      ),
        .done_o       (spi_done_o      ),
        .read_valid_o (spi_read_valid  ),
        .read_ready_i (spi_read_ready  ),
        .read_data_o  (spi_read_data   ),
        .chip_sck_o   (chip_sck_o      ),
        .chip_csb_o   (chip_csb_o      ),
        .chip_sd_i    (chip_sd_i       ),
        .chip_sd_o    (chip_sd_o       ),
        .chip_sd_oe_o (chip_sd_oe_o    )
    );

    // chip_command
    //  actual chip_command API: see chip_command_api.sv
    (* mark_debug = "true" *) chip_command_t chip_command;
    (* mark_debug = "true" *) logic [7:0]    chip_command_opcode;

    assign chip_command.bitwise = cmd_word_r;
    assign chip_command_opcode  = chip_command.chip_burst.opcode; // same bits for all views
    assign clk_chip_o = chip_clk_en_r ? clk_i : 1'b1;
    assign chip_arst_no = chip_rstn_r;

    // ------------------------------------------------------------------
    // Streaming data path / handshake (combinational)
    //  - input FIFO  -> SPI master  during a burst write
    //  - SPI master  -> output FIFO during a burst read (gated by !full)
    // ------------------------------------------------------------------
    always_comb begin
        fifo_rd_ready     = 1'b0;
        fifo_chip_wr_en_o = 1'b0;
        fifo_chip_din_o   = cmd_word_r;   // default (writeback path)
        spi_wdata         = spi_data_o;   // default (config data byte)
        spi_wdata_valid   = 1'b0;
        spi_read_ready    = 1'b0;

        case (state_current)
            IDLE:            fifo_rd_ready = 1'b1; // pull/drop words until a command
            FETCH_DATA_ADDR: fifo_rd_ready = 1'b1; // pull the address word

            SPI_WRITE_STREAM: begin
                spi_wdata       = fifo_rd_dout;
                spi_wdata_valid = fifo_rd_valid;
                fifo_rd_ready   = spi_wdata_ready; // dequeue exactly when master pulls
            end

            SPI_READ_STREAM: begin
                spi_read_ready    = !fifo_chip_full_i;            // backpressure -> pauses SCK
                fifo_chip_din_o   = spi_read_data;
                fifo_chip_wr_en_o = spi_read_valid && !fifo_chip_full_i;
            end

            WRITEBACK_PUSH: begin
                fifo_chip_din_o   = cmd_word_r;
                fifo_chip_wr_en_o = !fifo_chip_full_i;
            end

            default: ;
        endcase
    end

    // ------------------------------------------------------------------
    // Main state machine (registered)
    // ------------------------------------------------------------------
    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current   <= IDLE;
            cmd_word_r      <= '0;
            addr_word_r     <= '0;
            burst_len_r     <= '0;
            spi_start_o     <= 1'b0;
            spi_quad_mode_o <= 1'b0;
            spi_read_dir_o  <= 1'b0;
            spi_cmd_o       <= '0;
            spi_addr_o      <= '0;
            spi_len_o       <= '0;
            spi_data_o      <= '0;
            chip_clk_en_r   <= 1'b0;
            chip_rstn_r     <= 1'b1;
        end else begin
            spi_start_o <= 1'b0;

            case (state_current)
                IDLE: begin
                    if (fifo_rd_valid) begin
                        cmd_word_r <= fifo_rd_dout;
                        // Decode only words carrying the command marker; drop others.
                        if (fifo_rd_dout[31:28] == CHIP_CMD_MARKER)
                            state_current <= DECODE_CMD;
                        else
                            state_current <= IDLE;
                    end
                end

                DECODE_CMD: begin
                    case (chip_command_opcode)
                        CONFIG_CLK_RST: begin
                            chip_clk_en_r <= chip_command.chip_config.chip_clk_en;
                            chip_rstn_r   <= chip_command.chip_config.chip_rstn;
                            state_current <= IDLE;
                        end

                        CONFIG_SPI_SLAVE: begin
                            spi_quad_mode_o <= 1'b0;
                            spi_read_dir_o  <= 1'b0;
                            spi_cmd_o       <= 8'h01; // SPI slave: write reg0
                            spi_data_o      <= 32'h0000_0001; // reg0 value: bit0 enables Quad-SPI
                            spi_len_o       <= 16'd1;
                            state_current   <= SPI_CFG_START;
                        end

                        DATA_WRITE: begin
                            burst_len_r   <= chip_command.chip_burst.burst_length;
                            state_current <= FETCH_DATA_ADDR;
                        end

                        DATA_READ: begin
                            burst_len_r   <= chip_command.chip_burst.burst_length;
                            state_current <= FETCH_DATA_ADDR;
                        end

                        WRITEBACK_FIFO: begin
                            state_current <= WRITEBACK_PUSH;
                        end

                        default: begin
                            state_current <= IDLE;
                        end
                    endcase
                end

                FETCH_DATA_ADDR: begin
                    if (fifo_rd_valid) begin
                        addr_word_r     <= fifo_rd_dout;
                        spi_quad_mode_o <= 1'b1;
                        spi_addr_o      <= fifo_rd_dout;
                        spi_len_o       <= burst_len_r;
                        if (burst_len_r == 16'd0) begin
                            // length 0 is a no-op (address word still consumed)
                            state_current <= IDLE;
                        end else if (chip_command_opcode == DATA_WRITE) begin
                            spi_read_dir_o <= 1'b0;
                            spi_cmd_o      <= 8'h02; // SPI slave: write mem
                            state_current  <= SPI_WRITE_START;
                        end else begin
                            spi_read_dir_o <= 1'b1;
                            spi_cmd_o      <= 8'h0B; // SPI slave: read mem
                            state_current  <= SPI_READ_START;
                        end
                    end
                end

                SPI_CFG_START: begin
                    spi_start_o   <= 1'b1;
                    state_current <= SPI_CFG_WAIT;
                end

                SPI_CFG_WAIT: begin
                    if (spi_done_o) state_current <= IDLE;
                end

                SPI_WRITE_START: begin
                    spi_start_o   <= 1'b1;
                    state_current <= SPI_WRITE_STREAM;
                end

                SPI_WRITE_STREAM: begin
                    if (spi_done_o) state_current <= IDLE;
                end

                SPI_READ_START: begin
                    spi_start_o   <= 1'b1;
                    state_current <= SPI_READ_STREAM;
                end

                SPI_READ_STREAM: begin
                    if (spi_done_o) state_current <= IDLE;
                end

                WRITEBACK_PUSH: begin
                    if (!fifo_chip_full_i) state_current <= IDLE;
                end

                default: begin
                    state_current <= IDLE;
                end
            endcase
        end
    end

endmodule

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
//   The module reads commands/data from the upstream FIFO,
//   converts the FIFO input into a streaming handshake, and then
//   routes each transaction either to the SPI master or to the
//   output FIFO for writeback.

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
        FETCH_DATA_WORD,
        SPI_CFG_START,
        SPI_CFG_WAIT,
        SPI_WRITE_START,
        SPI_WRITE_WAIT,
        SPI_READ_START,
        SPI_READ_WAIT,
        SPI_READ_PUSH,
        WRITEBACK_PUSH
    } chip_ctrl_state_t;

    (* mark_debug = "true" *) chip_ctrl_state_t state_current;
    (* mark_debug = "true" *) logic [31:0] cmd_word_r;
    (* mark_debug = "true" *) logic [31:0] addr_word_r;
    (* mark_debug = "true" *) logic [31:0] data_word_r;
    (* mark_debug = "true" *) logic [31:0] readback_word_r;

    (* mark_debug = "true" *) logic fifo_rd_valid;
    (* mark_debug = "true" *) logic [31:0] fifo_rd_dout;
    (* mark_debug = "true" *) logic fifo_rd_ready;

    (* mark_debug = "true" *) logic chip_clk_en_r;
    (* mark_debug = "true" *) logic chip_rstn_r;

    (* mark_debug = "true" *) logic spi_start_o;
    (* mark_debug = "true" *) logic spi_quad_mode_o;
    (* mark_debug = "true" *) logic spi_read_dir_o;
    (* mark_debug = "true" *) logic [7:0] spi_cmd_o;
    (* mark_debug = "true" *) logic [31:0] spi_addr_o;
    (* mark_debug = "true" *) logic [31:0] spi_data_o;
    (* mark_debug = "true" *) logic spi_busy_o;
    (* mark_debug = "true" *) logic spi_done_o;
    (* mark_debug = "true" *) logic spi_read_valid_o;
    (* mark_debug = "true" *) logic [31:0] spi_read_data_o;

    fifo_to_axi_stream_adapter#(
            .DATA_WIDTH(32)
        ) adapter_inst (
            .clk_i           (clk_i             ),
            .rst_i           (rst_i             ),
            .fifo_empty_i    (fifo_chip_empty_i ),
            .fifo_rdata_i    (fifo_chip_dout_i  ),
            .fifo_rden_o     (fifo_chip_rd_en_o ),
            .m_axis_tvalid_o (fifo_rd_valid     ),
            .m_axis_tdata_o  (fifo_rd_dout      ),
            .m_axis_tready_i (fifo_rd_ready     )
    );

    quad_spi_master #(
        .CLK_HZ(CLK_HZ),
        .SCK_HZ(SCK_HZ)
    ) spi_master_inst (
        .clk_i          (clk_i            ),
        .rst_i          (rst_i            ),
        .start_i        (spi_start_o      ),
        .quad_mode_i    (spi_quad_mode_o  ),
        .read_i         (spi_read_dir_o   ),
        .cmd_i          (spi_cmd_o        ),
        .addr_i         (spi_addr_o       ),
        .wdata_i        (spi_data_o       ),
        .busy_o         (spi_busy_o       ),
        .done_o         (spi_done_o       ),
        .read_valid_o   (spi_read_valid_o ),
        .read_data_o    (spi_read_data_o  ),
        .chip_sck_o     (chip_sck_o       ),
        .chip_csb_o     (chip_csb_o       ),
        .chip_sd_i      (chip_sd_i        ),
        .chip_sd_o      (chip_sd_o        ),
        .chip_sd_oe_o   (chip_sd_oe_o     )
    );

    // chip_command
    //  actual chip_command API: see chip_command_api.sv
    (* mark_debug = "true" *) chip_command_t chip_command;
    (* mark_debug = "true" *) logic [3:0]    chip_command_opcode;

    assign chip_command.bitwise = cmd_word_r;
    assign chip_command_opcode = chip_command.chip_config.opcode;
    assign clk_chip_o = chip_clk_en_r ? clk_i : 1'b1;
    assign chip_arst_no = chip_rstn_r;

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current     <= IDLE;
            cmd_word_r        <= '0;
            addr_word_r       <= '0;
            data_word_r       <= '0;
            readback_word_r   <= '0;
            fifo_chip_wr_en_o <= 1'b0;
            fifo_chip_din_o   <= '0;
            fifo_rd_ready     <= 1'b0;
            spi_start_o       <= 1'b0;
            spi_quad_mode_o   <= 1'b0;
            spi_read_dir_o    <= 1'b0;
            spi_cmd_o         <= '0;
            spi_addr_o        <= '0;
            spi_data_o        <= '0;
            chip_clk_en_r     <= 1'b0;
            chip_rstn_r       <= 1'b1;
        end else begin
            fifo_chip_wr_en_o <= 1'b0;
            fifo_rd_ready     <= 1'b0;
            spi_start_o       <= 1'b0;

            case (state_current)
                IDLE: begin
                    fifo_rd_ready <= 1'b1;
                    if (fifo_rd_valid) begin
                        cmd_word_r    <= fifo_rd_dout;
                        state_current <= DECODE_CMD;
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
                            spi_cmd_o       <= 8'h01; // align with ETHz SPI slave IP (config)
                            spi_addr_o      <= '0;
                            spi_data_o      <= '0;
                            state_current   <= SPI_CFG_START;
                        end

                        DATA_WRITE: begin
                            state_current <= FETCH_DATA_ADDR;
                        end

                        DATA_READ: begin
                            state_current <= FETCH_DATA_ADDR;
                        end

                        WRITEBACK_FIFO: begin
                            readback_word_r <= cmd_word_r;
                            state_current   <= WRITEBACK_PUSH;
                        end

                        default: begin
                            state_current <= IDLE;
                        end
                    endcase
                end

                FETCH_DATA_ADDR: begin
                    fifo_rd_ready <= 1'b1;
                    if (fifo_rd_valid) begin
                        addr_word_r <= fifo_rd_dout;
                        if (chip_command_opcode == DATA_WRITE) begin
                            state_current <= FETCH_DATA_WORD;
                        end else begin
                            spi_quad_mode_o <= 1'b1;
                            spi_read_dir_o  <= 1'b1;
                            spi_cmd_o       <= 8'h0B; // align with ETHz SPI slave IP (read)
                            spi_addr_o      <= fifo_rd_dout;
                            spi_data_o      <= '0;
                            state_current   <= SPI_READ_START;
                        end
                    end
                end

                FETCH_DATA_WORD: begin
                    fifo_rd_ready <= 1'b1;
                    if (fifo_rd_valid) begin
                        data_word_r     <= fifo_rd_dout;
                        spi_quad_mode_o <= 1'b1;
                        spi_read_dir_o  <= 1'b0;
                        spi_cmd_o       <= 8'h02; // align with ETHz SPI slave IP (write)
                        spi_addr_o      <= addr_word_r;
                        spi_data_o      <= fifo_rd_dout;
                        state_current   <= SPI_WRITE_START;
                    end
                end

                SPI_CFG_START: begin
                    spi_start_o    <= 1'b1;
                    state_current  <= SPI_CFG_WAIT;
                end

                SPI_CFG_WAIT: begin
                    if (spi_done_o) begin
                        state_current <= IDLE;
                    end
                end

                SPI_WRITE_START: begin
                    spi_start_o    <= 1'b1;
                    state_current  <= SPI_WRITE_WAIT;
                end

                SPI_WRITE_WAIT: begin
                    if (spi_done_o) begin
                        state_current <= IDLE;
                    end
                end

                SPI_READ_START: begin
                    spi_start_o    <= 1'b1;
                    state_current  <= SPI_READ_WAIT;
                end

                SPI_READ_WAIT: begin
                    if (spi_done_o) begin
                        if (spi_read_valid_o) begin
                            readback_word_r <= spi_read_data_o;
                            state_current   <= SPI_READ_PUSH;
                        end else begin
                            state_current <= IDLE;
                        end
                    end
                end

                SPI_READ_PUSH: begin
                    if (!fifo_chip_full_i) begin
                        fifo_chip_din_o   <= readback_word_r;
                        fifo_chip_wr_en_o <= 1'b1;
                        state_current     <= IDLE;
                    end
                end

                WRITEBACK_PUSH: begin
                    if (!fifo_chip_full_i) begin
                        fifo_chip_din_o   <= cmd_word_r;
                        fifo_chip_wr_en_o <= 1'b1;
                        state_current     <= IDLE;
                    end
                end

                default: begin
                    state_current <= IDLE;
                end
            endcase
        end
    end

endmodule

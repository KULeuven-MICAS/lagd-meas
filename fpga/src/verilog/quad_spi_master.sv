// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
// Assisted by Copilot (2026)
//
//   Control inputs
//        |
//        v
//   +---------------------------+
//   |     SPI state machine     |
//   +---------------------------+
//      |                  |
//      v                  v
//   Quad SPI bus      Readback output
//   (cmd/addr/data)    (data + valid)
//
//   The module accepts a start request, sequences the command/address/
//   data phases through its state machine, drives the quad SPI pins,
//   and returns read data when the transaction is a read.

module quad_spi_master #(
    parameter int CLK_HZ = 100_000_000,
    parameter int SCK_HZ = 25_000_000
)(
    input  logic        clk_i,
    (* direct_reset = "yes" *) input  logic rst_i,
    input  logic        start_i,
    input  logic        quad_mode_i,
    input  logic        read_i,
    input  logic [7:0]  cmd_i,
    input  logic [31:0] addr_i,
    input  logic [31:0] wdata_i,
    output logic        busy_o,
    output logic        done_o,
    output logic        read_valid_o,
    output logic [31:0] read_data_o,
    output logic        chip_sck_o,
    output logic        chip_csb_o,
    input  logic [3:0]  chip_sd_i,
    output logic [3:0]  chip_sd_o,
    output logic [3:0]  chip_sd_oe_o
);

    localparam int SCK_HALF = CLK_HZ / SCK_HZ / 2;
    localparam int DUMMY_CYCS = 33;

    typedef enum logic [2:0] {
        IDLE,
        INIT_SEND,
        Q_CMD_ADDR,
        Q_WRITE_DATA,
        Q_DUMMY,
        Q_READ_DATA,
        Q_READ_DONE_WAIT
    } spi_state_t;

    (* mark_debug = "true" *) spi_state_t state_current;
    (* mark_debug = "true" *) logic [6:0] sck_cnt_r;
    (* mark_debug = "true" *) logic [5:0] dummy_cnt_r;
    (* mark_debug = "true" *) logic [3:0] bit_cnt_r;
    (* mark_debug = "true" *) logic [3:0] nibble_cnt_r;
    (* mark_debug = "true" *) logic [7:0] init_shift_r;
    (* mark_debug = "true" *) logic [39:0] quad_shift_r;
    (* mark_debug = "true" *) logic [31:0] write_shift_r;
    (* mark_debug = "true" *) logic [31:0] read_shift_r;
    (* mark_debug = "true" *) logic [3:0] sd_drive_r;
    (* mark_debug = "true" *) logic [3:0] sd_oe_r;
    (* mark_debug = "true" *) logic [7:0] cmd_r;
    (* mark_debug = "true" *) logic [31:0] addr_r;
    (* mark_debug = "true" *) logic [31:0] wdata_r;
    (* mark_debug = "true" *) logic read_r;

    assign chip_sd_o = sd_drive_r;
    assign chip_sd_oe_o = sd_oe_r;

    wire [3:0] sd_in = chip_sd_i;
    wire sck_edge_tick = (state_current != IDLE) && (sck_cnt_r == SCK_HALF - 1);
    wire sck_rise_tick = sck_edge_tick && (chip_sck_o == 1'b0);
    wire sck_fall_tick = sck_edge_tick && (chip_sck_o == 1'b1);

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current  <= IDLE;
            sck_cnt_r      <= '0;
            dummy_cnt_r    <= '0;
            bit_cnt_r      <= '0;
            nibble_cnt_r   <= '0;
            init_shift_r   <= '0;
            quad_shift_r   <= '0;
            write_shift_r  <= '0;
            read_shift_r   <= '0;
            sd_drive_r     <= '0;
            sd_oe_r        <= '0;
            cmd_r          <= '0;
            addr_r         <= '0;
            wdata_r        <= '0;
            read_r         <= 1'b0;
            busy_o         <= 1'b0;
            done_o         <= 1'b0;
            read_valid_o   <= 1'b0;
            read_data_o    <= '0;
            chip_sck_o     <= 1'b0;
            chip_csb_o     <= 1'b1;
        end else begin
            done_o       <= 1'b0;
            read_valid_o <= 1'b0;

            if (state_current == IDLE) begin
                chip_sck_o <= 1'b0;
                chip_csb_o <= 1'b1;
                sd_oe_r    <= 4'b0000;
                sck_cnt_r  <= '0;
                if (start_i) begin
                    busy_o  <= 1'b1;
                    chip_csb_o <= 1'b0;
                    cmd_r   <= cmd_i;
                    addr_r  <= addr_i;
                    wdata_r <= wdata_i;
                    read_r  <= read_i;
                    if (!quad_mode_i) begin
                        state_current <= INIT_SEND;
                        init_shift_r  <= cmd_i;
                        bit_cnt_r     <= 4'd8;
                        sd_oe_r       <= 4'b0001;
                        sd_drive_r    <= {3'b000, cmd_i[7]};
                    end else begin
                        state_current <= Q_CMD_ADDR;
                        quad_shift_r  <= {cmd_i, addr_i};
                        nibble_cnt_r  <= 4'd10;
                        sd_oe_r       <= 4'b1111;
                        sd_drive_r    <= cmd_i[7:4];
                    end
                end else begin
                    busy_o <= 1'b0;
                end
            end else begin
                sck_cnt_r <= sck_edge_tick ? '0 : (sck_cnt_r + 1'b1);

                if (sck_edge_tick) begin
                    chip_sck_o <= ~chip_sck_o;

                    if (sck_rise_tick) begin
                        case (state_current)
                            Q_DUMMY: begin
                                dummy_cnt_r <= dummy_cnt_r + 1'b1;
                            end

                            Q_READ_DATA: begin
                                read_shift_r <= {read_shift_r[27:0], sd_in};
                                if (nibble_cnt_r == 4'd1) begin
                                    read_data_o   <= {read_shift_r[27:0], sd_in};
                                    state_current <= Q_READ_DONE_WAIT;
                                end else begin
                                    nibble_cnt_r <= nibble_cnt_r - 1'b1;
                                end
                            end

                            default: begin
                            end
                        endcase
                    end

                    if (sck_fall_tick) begin
                        case (state_current)
                            INIT_SEND: begin
                                if (bit_cnt_r == 4'd1) begin
                                    chip_sck_o     <= 1'b0;
                                    chip_csb_o     <= 1'b1;
                                    sd_oe_r        <= 4'b0000;
                                    busy_o         <= 1'b0;
                                    done_o         <= 1'b1;
                                    state_current  <= IDLE;
                                end else begin
                                    bit_cnt_r    <= bit_cnt_r - 1'b1;
                                    init_shift_r <= {init_shift_r[6:0], 1'b0};
                                    sd_drive_r   <= {3'b000, init_shift_r[6]};
                                end
                            end

                            Q_CMD_ADDR: begin
                                if (nibble_cnt_r == 4'd1) begin
                                    if (read_r) begin
                                        sd_oe_r        <= 4'b0000;
                                        dummy_cnt_r    <= '0;
                                        state_current  <= Q_DUMMY;
                                    end else begin
                                        write_shift_r  <= wdata_r;
                                        nibble_cnt_r   <= 4'd8;
                                        sd_oe_r        <= 4'b1111;
                                        sd_drive_r     <= wdata_r[31:28];
                                        state_current  <= Q_WRITE_DATA;
                                    end
                                end else begin
                                    nibble_cnt_r  <= nibble_cnt_r - 1'b1;
                                    quad_shift_r  <= {quad_shift_r[35:0], 4'b0};
                                    sd_drive_r    <= quad_shift_r[35:32];
                                end
                            end

                            Q_WRITE_DATA: begin
                                if (nibble_cnt_r == 4'd1) begin
                                    chip_sck_o    <= 1'b0;
                                    chip_csb_o    <= 1'b1;
                                    sd_oe_r       <= 4'b0000;
                                    busy_o        <= 1'b0;
                                    done_o        <= 1'b1;
                                    state_current <= IDLE;
                                end else begin
                                    nibble_cnt_r <= nibble_cnt_r - 1'b1;
                                    write_shift_r <= {write_shift_r[27:0], 4'b0};
                                    sd_drive_r    <= write_shift_r[27:24];
                                end
                            end

                            Q_DUMMY: begin
                                if (dummy_cnt_r == DUMMY_CYCS) begin
                                    nibble_cnt_r  <= 4'd8;
                                    read_shift_r  <= '0;
                                    state_current <= Q_READ_DATA;
                                end
                            end

                            Q_READ_DONE_WAIT: begin
                                chip_sck_o    <= 1'b0;
                                chip_csb_o    <= 1'b1;
                                sd_oe_r       <= 4'b0000;
                                busy_o        <= 1'b0;
                                read_valid_o  <= 1'b1;
                                done_o        <= 1'b1;
                                state_current <= IDLE;
                            end

                            default: begin
                            end
                        endcase
                    end
                end
            end
        end
    end

endmodule

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
//
//   Burst support: a single start can transfer len_i 32-bit words inside one
//   CS-low frame (len_i == 1 is the single-word case). Data words are streamed:
//     - write: pulled via wdata_i/wdata_valid_i/wdata_ready_o
//     - read : pushed via read_data_o/read_valid_o/read_ready_i
//   When the producer/consumer is not ready at a word boundary, SCK is paused
//   (held, CS stays low) until the handshake completes. The SPI slave is edge
//   driven with CS low, so pausing SCK is harmless.
//
// Required SPI mode by SPI slave: CPOL=0, CPHA=0 (SPI mode 0)
// SPI slave samples data on the rising edge of SCK and changes data on the
// falling edge of SCK.

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
    // Number of 32-bit words to transfer in the frame (>= 1). The SPI slave
    // supports up to 65535 words per frame, hence 16 bits.
    input  logic [15:0] len_i,
    // Write data stream (master pulls one word per data-word boundary)
    input  logic [31:0] wdata_i,
    input  logic        wdata_valid_i,
    output logic        wdata_ready_o,
    output logic        busy_o,
    output logic        done_o,
    // Read data stream (master pushes one word per data-word boundary)
    output logic        read_valid_o,
    input  logic        read_ready_i,
    output logic [31:0] read_data_o,
    output logic        chip_sck_o,
    output logic        chip_csb_o,
    input  logic [3:0]  chip_sd_i,
    output logic [3:0]  chip_sd_o,
    output logic [3:0]  chip_sd_oe_o
);

    localparam int SCK_HALF = CLK_HZ / SCK_HZ / 2;
    // 33 dummy SCK cycles are required by the SPI slave between the read address
    // and the first read data nibble (slave dummy register defaults to 32, plus
    // one extra cycle from the ETHz RX counter off-by-one => 33 actual cycles).
    localparam int DUMMY_CYCS = 33;

    typedef enum logic [2:0] {
        IDLE,
        INIT_SEND,
        Q_CMD_ADDR,
        Q_WRITE_FETCH,
        Q_WRITE_DATA,
        Q_DUMMY,
        Q_READ_DATA,
        Q_READ_HANDOFF
    } spi_state_t;

    (* mark_debug = "true" *) spi_state_t state_current;
    (* mark_debug = "true" *) logic [6:0]  sck_cnt_r;
    (* mark_debug = "true" *) logic [5:0]  dummy_cnt_r;
    (* mark_debug = "true" *) logic [4:0]  bit_cnt_r;
    (* mark_debug = "true" *) logic [3:0]  nibble_cnt_r;
    (* mark_debug = "true" *) logic [15:0] word_cnt_r;
    (* mark_debug = "true" *) logic [15:0] init_shift_r;
    (* mark_debug = "true" *) logic [39:0] quad_shift_r;
    (* mark_debug = "true" *) logic [31:0] write_shift_r;
    (* mark_debug = "true" *) logic [31:0] read_shift_r;
    (* mark_debug = "true" *) logic [3:0]  sd_drive_r;
    (* mark_debug = "true" *) logic [3:0]  sd_oe_r;
    (* mark_debug = "true" *) logic        read_r;

    assign chip_sd_o    = sd_drive_r;
    assign chip_sd_oe_o = sd_oe_r;

    // Streaming handshakes: the master is waiting for the producer/consumer only
    // in the dedicated word-boundary states.
    assign wdata_ready_o = (state_current == Q_WRITE_FETCH);
    assign read_valid_o  = (state_current == Q_READ_HANDOFF);

    wire [3:0] sd_in = chip_sd_i;

    // SCK is only generated in the bit/nibble-clocking states. In the
    // Q_WRITE_FETCH / Q_READ_HANDOFF wait states it is frozen (paused) so the
    // stream handshake can apply backpressure without losing data.
    wire sck_active = (state_current == INIT_SEND)    ||
                      (state_current == Q_CMD_ADDR)   ||
                      (state_current == Q_DUMMY)      ||
                      (state_current == Q_WRITE_DATA) ||
                      (state_current == Q_READ_DATA);

    wire sck_edge_tick = sck_active && (sck_cnt_r == SCK_HALF - 1);
    wire sck_rise_tick = sck_edge_tick && (chip_sck_o == 1'b0);
    wire sck_fall_tick = sck_edge_tick && (chip_sck_o == 1'b1);

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current  <= IDLE;
            sck_cnt_r      <= '0;
            dummy_cnt_r    <= '0;
            bit_cnt_r      <= '0;
            nibble_cnt_r   <= '0;
            word_cnt_r     <= '0;
            init_shift_r   <= '0;
            quad_shift_r   <= '0;
            write_shift_r  <= '0;
            read_shift_r   <= '0;
            sd_drive_r     <= '0;
            sd_oe_r        <= '0;
            read_r         <= 1'b0;
            busy_o         <= 1'b0;
            done_o         <= 1'b0;
            read_data_o    <= '0;
            chip_sck_o     <= 1'b0;
            chip_csb_o     <= 1'b1;
        end else begin
            done_o <= 1'b0;

            if (state_current == IDLE) begin
                chip_sck_o <= 1'b0;
                chip_csb_o <= 1'b1;
                sd_oe_r    <= 4'b0000;
                sck_cnt_r  <= '0;
                if (start_i) begin
                    busy_o     <= 1'b1;
                    chip_csb_o <= 1'b0;
                    read_r     <= read_i;
                    word_cnt_r <= len_i;
                    if (!quad_mode_i) begin
                        // Single-SPI config write: send the command byte followed
                        // by one data byte in the same CS-low frame (e.g. write
                        // reg0 of the ETHz SPI slave to enable Quad-SPI mode). The
                        // data byte is taken from wdata_i[7:0].
                        state_current <= INIT_SEND;
                        init_shift_r  <= {cmd_i, wdata_i[7:0]};
                        bit_cnt_r     <= 5'd16;
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
            end else if (sck_active) begin
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
                                    state_current <= Q_READ_HANDOFF;
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
                                if (bit_cnt_r == 5'd1) begin
                                    chip_sck_o     <= 1'b0;
                                    chip_csb_o     <= 1'b1;
                                    sd_oe_r        <= 4'b0000;
                                    busy_o         <= 1'b0;
                                    done_o         <= 1'b1;
                                    state_current  <= IDLE;
                                end else begin
                                    bit_cnt_r    <= bit_cnt_r - 1'b1;
                                    init_shift_r <= {init_shift_r[14:0], 1'b0};
                                    sd_drive_r   <= {3'b000, init_shift_r[14]};
                                end
                            end

                            Q_CMD_ADDR: begin
                                if (nibble_cnt_r == 4'd1) begin
                                    if (read_r) begin
                                        sd_oe_r        <= 4'b0000;
                                        dummy_cnt_r    <= '0;
                                        state_current  <= Q_DUMMY;
                                    end else begin
                                        // Fetch the first write word from the stream
                                        state_current  <= Q_WRITE_FETCH;
                                    end
                                end else begin
                                    nibble_cnt_r  <= nibble_cnt_r - 1'b1;
                                    quad_shift_r  <= {quad_shift_r[35:0], 4'b0};
                                    sd_drive_r    <= quad_shift_r[35:32];
                                end
                            end

                            Q_WRITE_DATA: begin
                                if (nibble_cnt_r == 4'd1) begin
                                    if (word_cnt_r == 16'd1) begin
                                        chip_sck_o    <= 1'b0;
                                        chip_csb_o    <= 1'b1;
                                        sd_oe_r       <= 4'b0000;
                                        busy_o        <= 1'b0;
                                        done_o        <= 1'b1;
                                        state_current <= IDLE;
                                    end else begin
                                        // More words: fetch the next one (SCK now low)
                                        word_cnt_r    <= word_cnt_r - 1'b1;
                                        state_current <= Q_WRITE_FETCH;
                                    end
                                end else begin
                                    nibble_cnt_r  <= nibble_cnt_r - 1'b1;
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

                            default: begin
                            end
                        endcase
                    end
                end
            end else begin
                // SCK-paused word-boundary states (backpressure / handshake).
                case (state_current)
                    Q_WRITE_FETCH: begin
                        if (wdata_valid_i) begin
                            write_shift_r <= wdata_i;
                            sd_drive_r    <= wdata_i[31:28];
                            sd_oe_r       <= 4'b1111;
                            nibble_cnt_r  <= 4'd8;
                            state_current <= Q_WRITE_DATA;
                        end
                    end

                    Q_READ_HANDOFF: begin
                        if (read_ready_i) begin
                            if (word_cnt_r == 16'd1) begin
                                chip_sck_o    <= 1'b0;
                                chip_csb_o    <= 1'b1;
                                sd_oe_r       <= 4'b0000;
                                busy_o        <= 1'b0;
                                done_o        <= 1'b1;
                                state_current <= IDLE;
                            end else begin
                                word_cnt_r    <= word_cnt_r - 1'b1;
                                nibble_cnt_r  <= 4'd8;
                                read_shift_r  <= '0;
                                state_current <= Q_READ_DATA;
                            end
                        end
                    end

                    default: begin
                    end
                endcase
            end
        end
    end

endmodule

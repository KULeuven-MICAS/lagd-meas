// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
// Assisted by Copilot (2026)

//   Control inputs
//        |
//        v
//   +-----------------------------+
//   |        DAC SPI Driver       |
//   +-----------------------------+
//        |           |             |
//        v           v             v
//   SPI signals   Control pins   Status
// (dac_clk/dac_csb) (dac_shdn/dac_rstn) (busy)
//
//   Mode-3 SPI engine (CPOL=1/CPHA=1) for the AD8802 TrimDAC:
//   - dac_clk_o idles high. On `load_i` (with `rstn_i` asserted) it pulls CS low
//     and drops the clock (leading edge), then shifts out a 12-bit word
//     MSB-first formed as `{addr_i, data_i}`. Each bit is launched on the
//     falling edge and the DAC samples it on the following rising edge.
//   - Each clock half-period is SCK_HALF_CYCLES fabric cycles, so the very first
//     low and high phases are full half-periods too (the first rising edge lands
//     one full half-period after CS falls). This satisfies the AD8802 minimum
//     clock pulse width (15 ns) and CS-to-clock setup.
//   - After the last bit, the clock is held high and `dac_csb_o` is held low for
//     `CSB_HOLD_CYCLES` extra fabric cycles, then CS is released high (with the
//     clock high) to latch the addressed DAC register. `busy_o` is high for the
//     whole transfer. `dac_shdn_o` / `dac_rstn_o` reflect the input controls.

module dac_spi_driver #(
    parameter int CLK_HZ = 100_000_000,
    parameter int SCK_HZ = 25_000_000,
    parameter int CSB_HOLD_CYCLES = 4 // in terms of cycles under CLK_HZ
)(
    input  logic       clk_i,
    (* direct_reset = "yes" *) input logic rst_i,
    input  logic       load_i,
    input  logic       rstn_i,
    input  logic       shdn_i,
    input  logic [3:0] addr_i,
    input  logic [7:0] data_i,
    output logic       busy_o,
    output logic       dac_clk_o,
    output logic       dac_csb_o,
    output logic       dac_sdi_o,
    output logic       dac_shdn_o,
    output logic       dac_rstn_o
);

    localparam int SHIFT_BITS = 12;
    localparam int SCK_HALF_CYCLES = CLK_HZ / SCK_HZ / 2;

    typedef enum logic [1:0] {
        IDLE,
        LOW_WAIT,
        HIGH_WAIT,
        POST_HOLD
    } dac_state_t;

    (* mark_debug = "true" *) dac_state_t state_current;
    (* mark_debug = "true" *) logic [SHIFT_BITS-1:0] shift_reg_r;
    (* mark_debug = "true" *) logic [3:0] half_cnt_r;
    (* mark_debug = "true" *) logic [2:0] hold_cnt_r;
    (* mark_debug = "true" *) logic [3:0] bit_idx_r;

    wire [SHIFT_BITS-1:0] tx_word = {addr_i, data_i};

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current <= IDLE;
            shift_reg_r   <= '0;
            half_cnt_r    <= '0;
            hold_cnt_r    <= '0;
            bit_idx_r     <= '0;
            busy_o        <= 1'b0;
            dac_clk_o     <= 1'b1;   // Mode-3: clock idles high
            dac_csb_o     <= 1'b1;
            dac_sdi_o     <= 1'b0;
            dac_shdn_o    <= 1'b1;
            dac_rstn_o    <= 1'b1;
        end else begin
            case (state_current)
                IDLE: begin
                    busy_o    <= 1'b0;
                    dac_clk_o <= 1'b1;
                    dac_csb_o <= 1'b1;

                    if (load_i) begin
                        dac_shdn_o <= shdn_i;
                        dac_rstn_o <= rstn_i;
                        if (rstn_i) begin
                            // Start the transfer: drop CS and the clock (leading
                            // edge launches the MSB), then count out a full low
                            // half-period before the first sampling (rising) edge.
                            shift_reg_r   <= tx_word;
                            bit_idx_r     <= SHIFT_BITS - 1;
                            half_cnt_r    <= '0;
                            hold_cnt_r    <= '0;
                            busy_o        <= 1'b1;
                            dac_csb_o     <= 1'b0;
                            dac_clk_o     <= 1'b0;
                            dac_sdi_o     <= tx_word[SHIFT_BITS-1];
                            state_current <= LOW_WAIT;
                        end
                    end
                end

                LOW_WAIT: begin
                    busy_o    <= 1'b1;
                    dac_csb_o <= 1'b0;
                    dac_clk_o <= 1'b0;

                    if (half_cnt_r == SCK_HALF_CYCLES - 1) begin
                        half_cnt_r    <= '0;
                        dac_clk_o     <= 1'b1;   // rising edge: DAC samples sdi
                        state_current <= HIGH_WAIT;
                    end else begin
                        half_cnt_r <= half_cnt_r + 1;
                    end
                end

                HIGH_WAIT: begin
                    busy_o    <= 1'b1;
                    dac_csb_o <= 1'b0;
                    dac_clk_o <= 1'b1;

                    if (half_cnt_r == SCK_HALF_CYCLES - 1) begin
                        half_cnt_r <= '0;
                        if (bit_idx_r == 0) begin
                            // last bit sampled: keep clock high, hold CS low
                            hold_cnt_r    <= CSB_HOLD_CYCLES - 1;
                            state_current <= POST_HOLD;
                        end else begin
                            // falling edge launches the next bit
                            bit_idx_r     <= bit_idx_r - 1;
                            shift_reg_r   <= {shift_reg_r[SHIFT_BITS-2:0], 1'b0};
                            dac_sdi_o     <= shift_reg_r[SHIFT_BITS-2];
                            dac_clk_o     <= 1'b0;
                            state_current <= LOW_WAIT;
                        end
                    end else begin
                        half_cnt_r <= half_cnt_r + 1;
                    end
                end

                POST_HOLD: begin
                    busy_o    <= 1'b1;
                    dac_clk_o <= 1'b1;
                    dac_csb_o <= 1'b0;

                    if (hold_cnt_r == 0) begin
                        busy_o        <= 1'b0;
                        dac_csb_o     <= 1'b1;   // release CS (clock high) -> DAC latches
                        state_current <= IDLE;
                    end else begin
                        hold_cnt_r <= hold_cnt_r - 1;
                    end
                end

                default: begin
                    state_current <= IDLE;
                end
            endcase
        end
    end

endmodule

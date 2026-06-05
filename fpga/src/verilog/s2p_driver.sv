// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>

//   Control inputs                         HV9308 serial interface
//        |                                  (din / clk / le)
//        v                                       ^
//   +-----------------------------+              |
//   |        S2P Driver           |--------------+
//   +-----------------------------+
//        |            |
//        v            v
//   status (busy/done)  readback data
//
//   Serial driver for the HV9308/HV9408 32-channel serial-to-parallel converter
//   (a 32-bit static shift register feeding 32 latched high-voltage outputs).
//
//   - WRITE (load_i): shift `wdata_i` out MSB-first on s2p_din_o, one bit per
//     s2p_clk_o rising edge (the HV9308 samples DIN on the low->high clock edge),
//     then pulse s2p_le_o high to transfer the 32-bit shift register into the
//     output latches. LE is held low while shifting. Output Enable (OE) is owned by
//     perip_controller, not this driver.
//   - READBACK (readback_i): the HV9308's cascade Data Out (= shift-register bit
//     32) is wired back as s2p_dout_i. This scans the 32 bits out MSB-first while
//     recirculating each captured bit back into DIN, so after 32 clocks the shift
//     register has rotated full circle and is preserved (it does NOT pulse LE, so
//     the latched outputs are undisturbed). Returns the 32 bits on rdata_o.
//
//   Each clock half-period is SCK_HALF cycles of clk_i. At SCK_HZ=1 MHz / clk_i=
//   100 MHz that is 50 cycles (500 ns), far above the HV9308's 8 MHz / 62 ns /
//   25 ns setup limits, so the external setup/hold is met by construction.

module s2p_driver #(
    parameter int CLK_HZ = 100_000_000,
    parameter int SCK_HZ = 1_000_000
)(
    input  logic        clk_i,
    (* direct_reset = "yes" *) input logic rst_i,
    input  logic        load_i,       // start a write (shift 32 bits + latch)
    input  logic        readback_i,   // start a recirculating readback scan
    input  logic [31:0] wdata_i,      // data shifted out on a write
    output logic        busy_o,
    output logic        done_o,       // 1-cycle pulse when a transfer completes
    output logic [31:0] rdata_o,      // last readback result

    // HV9308 serial interface
    output logic        s2p_din_o,    // -> Data Input
    output logic        s2p_clk_o,    // -> Clock (samples DIN on rising edge)
    output logic        s2p_le_o,     // -> Latch Enable (high transfers SR -> latch)
    input  logic        s2p_dout_i    // <- Data Out (cascade; SR bit 32)
);

    localparam int SHIFT_BITS = 32;
    localparam int SCK_HALF   = (CLK_HZ / SCK_HZ / 2 < 1) ? 1 : CLK_HZ / SCK_HZ / 2;

    // Two-FF synchronizer for the cascade data-out input (slow, PCB-delayed,
    // asynchronous to clk_i). Sampled at the start of each shift-low phase, long
    // after the previous clock edge (>= SCK_HALF cycles) so it has settled.
    (* async_reg = "true" *) logic [1:0] dout_sync;
    wire dout_synced = dout_sync[1];
    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) dout_sync <= 2'b0;
        else       dout_sync <= {dout_sync[0], s2p_dout_i};
    end

    typedef enum logic [2:0] {
        IDLE,        // wait for load_i / readback_i
        SHIFT_LOW,   // clk low: present bit (write) or capture+recirculate (readback)
        SHIFT_HIGH,  // clk high: HV9308 samples DIN on the rising edge
        LE_GAP,      // write only: guard gap before LE (tDLE)
        LE_HIGH      // write only: LE high -> latch SR into outputs
    } s2p_state_t;

    (* mark_debug = "true" *) s2p_state_t state_current;
    (* mark_debug = "true" *) logic        rb_r;         // current transfer is a readback
    (* mark_debug = "true" *) logic [31:0] shift_reg_r;  // write data, shifting out
    (* mark_debug = "true" *) logic [31:0] rdata_r;      // readback accumulator
    logic [5:0]  bit_idx;     // 31 .. 0
    logic [15:0] half_cnt;    // cycle counter within a clock half-period

    assign rdata_o = rdata_r;

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current <= IDLE;
            rb_r          <= 1'b0;
            shift_reg_r   <= '0;
            rdata_r       <= '0;
            bit_idx       <= '0;
            half_cnt      <= '0;
            busy_o        <= 1'b0;
            done_o        <= 1'b0;
            s2p_din_o     <= 1'b0;
            s2p_clk_o     <= 1'b0;
            s2p_le_o      <= 1'b0;
        end else begin
            done_o <= 1'b0;

            case (state_current)
                IDLE: begin
                    busy_o    <= 1'b0;
                    s2p_clk_o <= 1'b0;
                    s2p_le_o  <= 1'b0;
                    if (load_i || readback_i) begin
                        rb_r          <= readback_i;
                        shift_reg_r   <= wdata_i;
                        bit_idx       <= 6'(SHIFT_BITS - 1);
                        half_cnt      <= '0;
                        busy_o        <= 1'b1;
                        state_current <= SHIFT_LOW;
                    end
                end

                // clk low: drive the current bit and let it settle before the edge.
                SHIFT_LOW: begin
                    s2p_clk_o <= 1'b0;
                    if (half_cnt == '0) begin
                        if (rb_r) begin
                            // recirculate the captured Data Out, accumulate MSB-first
                            s2p_din_o <= dout_synced;
                            rdata_r   <= {rdata_r[SHIFT_BITS-2:0], dout_synced};
                        end else begin
                            s2p_din_o <= shift_reg_r[SHIFT_BITS-1];
                        end
                    end
                    if (half_cnt == SCK_HALF - 1) begin
                        half_cnt      <= '0;
                        s2p_clk_o     <= 1'b1;   // rising edge: HV9308 samples DIN
                        state_current <= SHIFT_HIGH;
                    end else begin
                        half_cnt <= half_cnt + 16'd1;
                    end
                end

                // clk high: hold, then advance to the next bit (or finish).
                SHIFT_HIGH: begin
                    s2p_clk_o <= 1'b1;
                    if (half_cnt == SCK_HALF - 1) begin
                        half_cnt  <= '0;
                        s2p_clk_o <= 1'b0;
                        if (bit_idx == 6'd0) begin
                            if (rb_r) begin
                                done_o        <= 1'b1;   // readback: no latch pulse
                                busy_o        <= 1'b0;
                                state_current <= IDLE;
                            end else begin
                                state_current <= LE_GAP; // write: latch the SR
                            end
                        end else begin
                            bit_idx <= bit_idx - 6'd1;
                            if (!rb_r)
                                shift_reg_r <= {shift_reg_r[SHIFT_BITS-2:0], 1'b0};
                            state_current <= SHIFT_LOW;
                        end
                    end else begin
                        half_cnt <= half_cnt + 16'd1;
                    end
                end

                // Guard gap (clk & le low) so LE rises well after the last clock edge.
                LE_GAP: begin
                    s2p_clk_o <= 1'b0;
                    s2p_le_o  <= 1'b0;
                    if (half_cnt == SCK_HALF - 1) begin
                        half_cnt      <= '0;
                        s2p_le_o      <= 1'b1;   // rising edge into LE_HIGH
                        state_current <= LE_HIGH;
                    end else begin
                        half_cnt <= half_cnt + 16'd1;
                    end
                end

                // LE high: the HV9308 transfers the shift register into the latches.
                LE_HIGH: begin
                    s2p_le_o <= 1'b1;
                    if (half_cnt == SCK_HALF - 1) begin
                        half_cnt      <= '0;
                        s2p_le_o      <= 1'b0;
                        done_o        <= 1'b1;
                        busy_o        <= 1'b0;
                        state_current <= IDLE;
                    end else begin
                        half_cnt <= half_cnt + 16'd1;
                    end
                end

                default: state_current <= IDLE;
            endcase
        end
    end

endmodule

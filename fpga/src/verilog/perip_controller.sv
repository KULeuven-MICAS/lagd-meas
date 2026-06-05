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
//        |            |            |
//        v            v            v
//   DAC SPI       HV9308 S2P    FIFO write
//   (dac_spi_driver) (s2p_driver) (writeback / readback echo)
//
//   The controller multiplexes TWO devices on the one 32-bit stream, routed by the
//   command opcode (see perip_command_api.sv):
//   - DAC (AD8802): single-word commands. opcode 0xFF echoes the word (writeback);
//     0x03 performs a DAC write AND echoes; rstn=0 holds the DAC in reset; any
//     other opcode performs a DAC write (12-bit MSB-first Mode-3 SPI).
//   - HV9308 S2P (bias resistors for the chip's analog current mirrors):
//       * S2P_WRITE (0x10): a 2-word frame [cmd][32-bit value]; shift the value in
//         MSB-first and latch it.
//       * S2P_READBACK (0x11): scan the shift register out of the cascade Data Out
//         (recirculating, non-destructive) and echo the 32 bits as one word.
//       * S2P_OE (0x12): set the Output Enable level (bit0). Powers up 0 (blanked);
//         software enables after a write and blanks around any reconfiguration.

module perip_controller #(
    parameter int CLK_HZ = 100_000_000,
    parameter int SCK_HZ = 25_000_000,       // DAC SPI clock
    parameter int CSB_HOLD_CYCLES = 4,       // in terms of cycles under CLK_HZ
    parameter int S2P_SCK_HZ = 1_000_000     // HV9308 shift clock
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
    (* mark_debug = "true" *) output logic dac_rstn_o,

    // HV9308 serial-to-parallel interface
    (* mark_debug = "true" *) output logic s2p_din_o,
    (* mark_debug = "true" *) output logic s2p_clk_o,
    (* mark_debug = "true" *) output logic s2p_le_o,
    (* mark_debug = "true" *) output logic s2p_oe_o,
    (* mark_debug = "true" *) input  logic s2p_dout_i,

    // activity output (for LED): 1-cycle pulse when a DAC or S2P write is issued
    output logic perip_write_pulse_o
);

    typedef enum logic [2:0] {
        IDLE,
        DECODE,
        WRITEBACK_WAIT,   // push fifo_word_r to the read FIFO (writeback / S2P readback echo)
        DAC_WAIT,
        S2P_FETCH,        // pull the 32-bit data word of an S2P_WRITE frame
        S2P_WRITE_WAIT,   // wait for the HV9308 shift+latch to finish
        S2P_READ_WAIT     // wait for the HV9308 readback scan, then echo the word
    } perip_state_t;

    (* mark_debug = "true" *) perip_state_t state_current;
    (* mark_debug = "true" *) logic [31:0] fifo_word_r;
    // Set when the current DAC command should also echo its command word back
    // (PERIP_OP_DAC_LOOPBACK): drives the DAC AND loops the word to the read FIFO.
    (* mark_debug = "true" *) logic loopback_r;

    // Command decoded via typedef in perip_command_api.sv
    (* mark_debug = "true" *) perip_command_t fifo_cmd_r;

    logic fifo_rd_valid;
    logic [31:0] fifo_rd_dout;
    logic fifo_rd_ready;

    logic dac_load_o;
    logic dac_busy_o;

    // S2P (HV9308) control
    (* mark_debug = "true" *) logic        s2p_load_o;
    (* mark_debug = "true" *) logic        s2p_readback_o;
    (* mark_debug = "true" *) logic [31:0] s2p_data_r;   // value to shift on a write
    logic        s2p_busy_o;
    logic        s2p_done_o;
    logic [31:0] s2p_rdata;
    (* mark_debug = "true" *) logic        s2p_oe_r;     // Output Enable level (0 = blank)

    // fifo_cmd_r.bitwise mirrors fifo_word_r (updated in the FSM)
    fifo_to_axi_stream_adapter#(
            .DATA_WIDTH      (32                ),
            .DEPTH           (2                 )
        ) adapter_inst (
            .clk_i           (clk_i             ),
            .rst_i           (rst_i             ),
            .fifo_empty_i    (fifo_perip_empty_i),
            .fifo_rdata_i    (fifo_perip_dout_i ),
            .fifo_rden_o     (fifo_perip_rd_en_o),
            .m_axis_tvalid_o (fifo_rd_valid     ),
            .m_axis_tdata_o  (fifo_rd_dout      ),
            .m_axis_tready_i (fifo_rd_ready     )
    );

    dac_spi_driver #(
        .CLK_HZ          (CLK_HZ         ),
        .SCK_HZ          (SCK_HZ         ),
        .CSB_HOLD_CYCLES (CSB_HOLD_CYCLES)
    ) dac_driver_inst (
        .clk_i           (clk_i          ),
        .rst_i           (rst_i          ),
        .load_i          (dac_load_o                 ),
        .rstn_i          (fifo_cmd_r.dac_config.rstn ),
        .shdn_i          (fifo_cmd_r.dac_config.shdn ),
        .addr_i          (fifo_cmd_r.dac_config.addr ),
        .data_i          (fifo_cmd_r.dac_config.data ),
        .busy_o          (dac_busy_o     ),
        .dac_clk_o       (dac_clk_o      ),
        .dac_csb_o       (dac_csb_o      ),
        .dac_sdi_o       (dac_sdi_o      ),
        .dac_shdn_o      (dac_shdn_o     ),
        .dac_rstn_o      (dac_rstn_o     )
    );

    s2p_driver #(
        .CLK_HZ     (CLK_HZ        ),
        .SCK_HZ     (S2P_SCK_HZ    )
    ) s2p_driver_inst (
        .clk_i      (clk_i         ),
        .rst_i      (rst_i         ),
        .load_i     (s2p_load_o    ),
        .readback_i (s2p_readback_o),
        .wdata_i    (s2p_data_r    ),
        .busy_o     (s2p_busy_o    ),
        .done_o     (s2p_done_o    ),
        .rdata_o    (s2p_rdata     ),
        .s2p_din_o  (s2p_din_o     ),
        .s2p_clk_o  (s2p_clk_o     ),
        .s2p_le_o   (s2p_le_o      ),
        .s2p_dout_i (s2p_dout_i    )
    );

    assign s2p_oe_o = s2p_oe_r;

    // Combinational read-ready: pull a word in IDLE (the command) and in S2P_FETCH
    // (the 32-bit data word of an S2P_WRITE frame). Combinational keeps it asserted
    // exactly one cycle per accepted word, so no word is dropped.
    assign fifo_rd_ready = (state_current == IDLE) || (state_current == S2P_FETCH);

    // perip "write activity" (for LED): a DAC load or an S2P load.
    assign perip_write_pulse_o = dac_load_o | s2p_load_o;

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current      <= IDLE;
            fifo_word_r        <= '0;
            loopback_r         <= 1'b0;
            fifo_perip_wr_en_o <= 1'b0;
            fifo_perip_din_o   <= '0;
            dac_load_o         <= 1'b0;
            s2p_load_o         <= 1'b0;
            s2p_readback_o     <= 1'b0;
            s2p_data_r         <= '0;
            s2p_oe_r           <= 1'b0;   // power-on: outputs blanked (OE low)
        end else begin
            fifo_perip_wr_en_o <= 1'b0;
            fifo_perip_din_o   <= '0;
            dac_load_o         <= 1'b0;
            s2p_load_o         <= 1'b0;
            s2p_readback_o     <= 1'b0;

            case (state_current)
                IDLE: begin
                    if (fifo_rd_valid) begin
                        fifo_word_r        <= fifo_rd_dout;
                        fifo_cmd_r.bitwise <= fifo_rd_dout;
                        state_current      <= DECODE;
                    end
                end

                DECODE: begin
                    if (fifo_cmd_r.dac_config.marker != PERIP_CMD_MARKER) begin
                        state_current <= IDLE;  // not a command: ignore
                    end else begin
                        case (fifo_cmd_r.dac_config.opcode)
                            PERIP_OP_WRITEBACK: begin
                                loopback_r    <= 1'b0;  // echo only, no transaction
                                state_current <= WRITEBACK_WAIT;
                            end
                            PERIP_OP_S2P_WRITE: begin
                                state_current <= S2P_FETCH;  // pull the 32-bit value
                            end
                            PERIP_OP_S2P_READBACK: begin
                                s2p_readback_o <= 1'b1;
                                state_current  <= S2P_READ_WAIT;
                            end
                            PERIP_OP_S2P_OE: begin
                                s2p_oe_r      <= fifo_word_r[0];  // bit0 = OE level
                                state_current <= IDLE;
                            end
                            default: begin
                                // DAC transaction (plain OP_DAC, or DAC_LOOPBACK which
                                // also echoes the command word once the transfer ends).
                                dac_load_o <= 1'b1;
                                loopback_r <= (fifo_cmd_r.dac_config.opcode == PERIP_OP_DAC_LOOPBACK);
                                if (fifo_cmd_r.dac_config.rstn) begin
                                    state_current <= DAC_WAIT;
                                end else if (fifo_cmd_r.dac_config.opcode == PERIP_OP_DAC_LOOPBACK) begin
                                    state_current <= WRITEBACK_WAIT;  // reset skips SPI, still echo
                                end else begin
                                    state_current <= IDLE;
                                end
                            end
                        endcase
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
                        // loopback writes echo the command word after the transfer
                        state_current <= loopback_r ? WRITEBACK_WAIT : IDLE;
                    end
                end

                // Second word of an S2P_WRITE frame: latch it and kick the driver.
                S2P_FETCH: begin
                    if (fifo_rd_valid) begin
                        s2p_data_r    <= fifo_rd_dout;
                        s2p_load_o    <= 1'b1;
                        state_current <= S2P_WRITE_WAIT;
                    end
                end

                S2P_WRITE_WAIT: begin
                    if (s2p_done_o) state_current <= IDLE;
                end

                // Readback scan: capture the 32 bits and echo them as one word.
                S2P_READ_WAIT: begin
                    if (s2p_done_o) begin
                        fifo_word_r   <= s2p_rdata;
                        state_current <= WRITEBACK_WAIT;
                    end
                end

                default: begin
                    state_current <= IDLE;
                end
            endcase
        end
    end

endmodule

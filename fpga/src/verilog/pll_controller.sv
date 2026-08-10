// Copyright 2026 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
//   Upstream FIFO read interface (8-bit)
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
//   PLL serial interface  FIFO write interface (8-bit)
//
//   Reads byte-framed commands from the upstream 8-bit FIFO (see
//   pll_command_api.sv) and drives the Pomelo PLL's serial configuration
//   interface (clk_sel_i, data_strb_i, data_i, cfg_vld_strb_i).
//
//   A command starts with a header byte {marker=0xF, opcode}. Words whose marker
//   is not 0xF are dropped. LOAD / LOAD_LOOPBACK collect a 6-byte (47-bit)
//   payload and shift it into the PLL's shallow register MSB-first, one bit per
//   data_strb_i rising edge, then pulse cfg_vld_strb_i once to commit it into the
//   hidden register. CLK_SEL latches a static clk_sel level. RESET pulses both
//   strobes together to reset the PLL registers. READBACK scans the shallow
//   register out of data_o (pll_data_i), recirculating each bit so the register is
//   preserved, and returns its 47 bits as 6 bytes (reads what the silicon actually
//   captured). STATUS returns one byte with bit0 = the synchronized PLL lock
//   (pll_lock_i). WRITEBACK echoes the 0xFF header back as a controller-liveness check.
//
//   Strobe timing: data_strb_i / cfg_vld_strb_i are used as gated *clocks* inside
//   the PLL, so each is generated as a clean two-phase pulse - data_i is set up
//   while the strobe is low for strb_half_r cycles, then the strobe is held high
//   for strb_half_r cycles (data stable across the rising edge). The FSM
//   guarantees data_strb_i and cfg_vld_strb_i are never high together except in
//   the deliberate RESET state.
//
//   The half-period is runtime-configurable via CONFIG_STRB (0x6); STRB_HALF is
//   only the power-on default, and STRB_HALF_MIN / STRB_HALF_MAX bound what
//   software may select.

module pll_controller #(
    // All three are clk_i cycles per strobe half-period; strobe = CLK_HZ/(2*half).
    parameter int STRB_HALF     = 50,        // power-on default (50 -> 1 MHz at 100 MHz)
    parameter int STRB_HALF_MIN = 2,         // fastest software may select
    parameter int STRB_HALF_MAX = 1_000_000  // slowest software may select (50 Hz at 100 MHz)
)(
    input  logic clk_i,
    (* direct_reset = "yes" *) input logic rst_i,

    // FIFO read interface (8-bit)
    (* mark_debug = "true" *) output logic       fifo_pll_rd_en_o,
    (* mark_debug = "true" *) input  logic       fifo_pll_empty_i,
    (* mark_debug = "true" *) input  logic [7:0] fifo_pll_dout_i,
    // FIFO write interface (8-bit)
    (* mark_debug = "true" *) output logic       fifo_pll_wr_en_o,
    (* mark_debug = "true" *) input  logic       fifo_pll_full_i,
    (* mark_debug = "true" *) output logic [7:0] fifo_pll_din_o,

    // PLL serial configuration interface (FPGA -> PLL, except pll_data_i)
    (* mark_debug = "true" *) output logic pll_clk_sel_o,      // -> clk_sel_i
    (* mark_debug = "true" *) output logic pll_data_strb_o,    // -> data_strb_i (shift clock)
    (* mark_debug = "true" *) output logic pll_data_o,         // -> data_i (serial data, MSB first)
    (* mark_debug = "true" *) output logic pll_cfg_vld_strb_o, // -> cfg_vld_strb_i (commit clock)
    (* mark_debug = "true" *) input  logic pll_data_i,         // <- data_o (shallow-reg MSB, for READBACK)
    (* mark_debug = "true" *) input  logic pll_lock_i,         // <- pll_lock_o (1 = locked, for STATUS)

    // Activity for LED: high whenever the controller is mid-transaction (any
    // state other than IDLE), i.e. decoding/collecting/shifting/committing/echoing.
    output logic pll_busy_o
);

    typedef enum logic [3:0] {
        IDLE,           // wait for header byte
        COLLECT,        // gather opcode-dependent payload bytes
        SHIFT_LOW,      // data_strb low: present current bit, setup time
        SHIFT_HIGH,     // data_strb high: PLL samples on the rising edge
        COMMIT_GAP,     // guard gap (both strobes low) before commit
        COMMIT_HIGH,    // cfg_vld_strb high: load hidden register
        RST_HIGH,       // both strobes high: reset PLL registers
        READ_LOW,       // data_strb low: sample data_o, recirculate, capture
        READ_HIGH,      // data_strb high: PLL shifts the recirculated bit back in
        ECHO,           // push the 6 payload / readback bytes back
        STATUS_PUSH,    // push the 1-byte status (bit0 = lock)
        WRITEBACK_PUSH  // push the 0xFF header back (liveness)
    } pll_state_t;

    (* mark_debug = "true" *) pll_state_t state_current;

    // Command / payload bookkeeping.
    (* mark_debug = "true" *) logic [3:0]  op_r;           // latched opcode
    (* mark_debug = "true" *) logic        loopback_r;     // echo payload after LOAD
    logic [3:0]  bytes_left;                                // payload bytes still to read
    logic [2:0]  byte_idx;                                  // index of next payload byte (0..5)
    (* mark_debug = "true" *) logic [PLL_CFG_BYTES*8-1:0] cfg_raw_r; // assembled 48-bit payload
    (* mark_debug = "true" *) logic        clk_sel_r;       // static clk_sel level

    // Shift / strobe engine.
    // Counter and register are sized from STRB_HALF_MAX so they never overflow.
    localparam int STRB_CW = $clog2(STRB_HALF_MAX + 1);
    logic [5:0]  bit_idx;        // current bit being shifted (46 .. 0, MSB first)
    logic [STRB_CW-1:0] strb_cnt;  // cycle counter within a strobe half-period
    (* mark_debug = "true" *) logic [STRB_CW-1:0] strb_half_r;  // set by CONFIG_STRB
    logic [2:0]  echo_idx;       // payload byte index during ECHO
    (* mark_debug = "true" *) logic [PLL_CFG_BITS-1:0] read_result_r; // bits captured from data_o

    // Saturate a CONFIG_STRB request into the permitted window, so an out-of-range
    // value slows/limits the strobe instead of hanging the engine.
    function automatic logic [STRB_CW-1:0] clamp_half(input logic [PLL_STRB_BYTES*8-1:0] v);
        if (v < (PLL_STRB_BYTES*8)'(STRB_HALF_MIN))      clamp_half = STRB_CW'(STRB_HALF_MIN);
        else if (v > (PLL_STRB_BYTES*8)'(STRB_HALF_MAX)) clamp_half = STRB_CW'(STRB_HALF_MAX);
        else                                             clamp_half = STRB_CW'(v);
    endfunction

    // Two-FF synchronizer for pll_data_i (the PLL's data_o; slow, PCB-delayed,
    // asynchronous to clk_i). Sampled during the READ_LOW dwell, well after the
    // previous shift has settled and propagated back.
    (* async_reg = "true" *) logic [1:0] data_i_sync;
    wire pll_data_i_synced = data_i_sync[1];
    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) data_i_sync <= 2'b0;
        else       data_i_sync <= {data_i_sync[0], pll_data_i};
    end

    // Two-FF synchronizer for pll_lock_i (the PLL's lock level from the chip; slow,
    // asynchronous to clk_i). Sampled when a STATUS command is served.
    (* async_reg = "true" *) logic [1:0] lock_sync;
    wire pll_lock_synced = lock_sync[1];
    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) lock_sync <= 2'b0;
        else       lock_sync <= {lock_sync[0], pll_lock_i};
    end

    // Read-side stream adapter (absorbs the FIFO's 1-cycle read latency).
    logic       fifo_rd_valid;
    logic [7:0] fifo_rd_dout;
    logic       fifo_rd_ready;

    // Decoded header (combinational view of the current stream byte in IDLE).
    pll_header_t header;
    assign header = fifo_rd_dout;

    fifo_to_axi_stream_adapter #(
        .DATA_WIDTH      (8                ),
        .DEPTH           (2                )
    ) adapter_inst (
        .clk_i           (clk_i            ),
        .rst_i           (rst_i            ),
        .fifo_empty_i    (fifo_pll_empty_i ),
        .fifo_rdata_i    (fifo_pll_dout_i  ),
        .fifo_rden_o     (fifo_pll_rd_en_o ),
        .m_axis_tvalid_o (fifo_rd_valid    ),
        .m_axis_tdata_o  (fifo_rd_dout     ),
        .m_axis_tready_i (fifo_rd_ready    )
    );

    // Pull a byte while waiting for a header (IDLE) or collecting payload (COLLECT).
    // Combinational so each accepted byte is consumed for exactly one cycle.
    always_comb begin
        case (state_current)
            IDLE, COLLECT: fifo_rd_ready = 1'b1;
            default:       fifo_rd_ready = 1'b0;
        endcase
    end

    assign pll_clk_sel_o = clk_sel_r;

    // LED activity: busy for the whole transaction (everything except IDLE).
    assign pll_busy_o = (state_current != IDLE);

    wire byte_taken = fifo_rd_valid && fifo_rd_ready;

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            state_current      <= IDLE;
            op_r               <= '0;
            loopback_r         <= 1'b0;
            bytes_left         <= '0;
            byte_idx           <= '0;
            cfg_raw_r          <= '0;
            // Power-on: select the reference clock (clk_sel=1 -> I1=clk_i). The PLL
            // is powered down by its reset defaults (pdown_PD/pdown_VCO=1) and drives
            // soc_clk, so defaulting to the PLL would leave the RISC-V SoC with no
            // clock. Boot on the reference, then issue CLK_SEL=0 after the PLL is
            // configured and locked.
            clk_sel_r          <= 1'b1;
            bit_idx            <= '0;
            strb_cnt           <= '0;
            strb_half_r        <= clamp_half((PLL_STRB_BYTES*8)'(STRB_HALF));
            echo_idx           <= '0;
            read_result_r      <= '0;
            fifo_pll_wr_en_o   <= 1'b0;
            fifo_pll_din_o     <= '0;
            pll_data_strb_o    <= 1'b0;
            pll_data_o         <= 1'b0;
            pll_cfg_vld_strb_o <= 1'b0;
        end else begin
            // Defaults (overridden below as needed).
            fifo_pll_wr_en_o <= 1'b0;

            case (state_current)
                // ---------------------------------------------------------------
                IDLE: begin
                    if (byte_taken) begin
                        if (header.marker != PLL_CMD_MARKER) begin
                            state_current <= IDLE;  // not a command: drop the byte
                        end else begin
                            op_r       <= header.opcode;
                            byte_idx   <= 3'd0;
                            loopback_r <= (header.opcode == PLL_OP_LOAD_LOOPBACK);
                            case (header.opcode)
                                PLL_OP_LOAD,
                                PLL_OP_LOAD_LOOPBACK: begin
                                    bytes_left    <= 4'(PLL_CFG_BYTES);
                                    state_current <= COLLECT;
                                end
                                PLL_OP_CLK_SEL: begin
                                    bytes_left    <= 4'd1;
                                    state_current <= COLLECT;
                                end
                                PLL_OP_RESET: begin
                                    strb_cnt      <= '0;
                                    state_current <= RST_HIGH;
                                end
                                PLL_OP_READBACK: begin
                                    bit_idx       <= 6'(PLL_CFG_BITS - 1); // 46 down to 0
                                    strb_cnt      <= '0;
                                    read_result_r <= '0;
                                    state_current <= READ_LOW;
                                end
                                PLL_OP_CONFIG_STRB: begin
                                    bytes_left    <= 4'(PLL_STRB_BYTES);
                                    state_current <= COLLECT;
                                end
                                PLL_OP_STATUS: begin
                                    state_current <= STATUS_PUSH;
                                end
                                PLL_OP_WRITEBACK: begin
                                    state_current <= WRITEBACK_PUSH;
                                end
                                default: state_current <= IDLE;
                            endcase
                        end
                    end
                end

                // ---------------------------------------------------------------
                COLLECT: begin
                    if (byte_taken) begin
                        cfg_raw_r[byte_idx*8 +: 8] <= fifo_rd_dout;
                        if (bytes_left == 4'd1) begin
                            // Last payload byte just captured -> dispatch.
                            case (op_r)
                                PLL_OP_CLK_SEL: begin
                                    clk_sel_r     <= fifo_rd_dout[0];
                                    state_current <= IDLE;
                                end
                                PLL_OP_CONFIG_STRB: begin
                                    // Bytes 0..1 are already in cfg_raw_r; the last
                                    // byte is still on the stream (the capture above
                                    // is non-blocking, so cfg_raw_r has not seen it).
                                    strb_half_r   <= clamp_half({fifo_rd_dout, cfg_raw_r[15:0]});
                                    state_current <= IDLE;
                                end
                                default: begin // LOAD / LOAD_LOOPBACK
                                    bit_idx       <= 6'(PLL_CFG_BITS - 1); // 46, MSB first
                                    strb_cnt      <= '0;
                                    state_current <= SHIFT_LOW;
                                end
                            endcase
                        end else begin
                            bytes_left <= bytes_left - 4'd1;
                            byte_idx   <= byte_idx + 3'd1;
                        end
                    end
                end

                // ---------------------------------------------------------------
                // data_strb low: drive the current bit and let it settle.
                SHIFT_LOW: begin
                    pll_data_strb_o <= 1'b0;
                    pll_data_o      <= cfg_raw_r[bit_idx];
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt        <= '0;
                        pll_data_strb_o <= 1'b1;  // rising edge into SHIFT_HIGH
                        state_current   <= SHIFT_HIGH;
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // data_strb high: PLL sampled on the entry rising edge; hold, then
                // drop the strobe and advance to the next bit (or commit).
                SHIFT_HIGH: begin
                    pll_data_strb_o <= 1'b1;
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt        <= '0;
                        pll_data_strb_o <= 1'b0;
                        if (bit_idx == 6'd0) begin
                            state_current <= COMMIT_GAP;
                        end else begin
                            bit_idx       <= bit_idx - 6'd1;
                            state_current <= SHIFT_LOW;
                        end
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // ---------------------------------------------------------------
                // Guard gap: both strobes low before pulsing cfg_vld (so the two
                // strobes are never high together -> no accidental reset).
                COMMIT_GAP: begin
                    pll_data_strb_o    <= 1'b0;
                    pll_cfg_vld_strb_o <= 1'b0;
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt           <= '0;
                        pll_cfg_vld_strb_o <= 1'b1;  // rising edge into COMMIT_HIGH
                        state_current      <= COMMIT_HIGH;
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // cfg_vld high: hidden register loaded on the entry rising edge.
                COMMIT_HIGH: begin
                    pll_cfg_vld_strb_o <= 1'b1;
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt           <= '0;
                        pll_cfg_vld_strb_o <= 1'b0;
                        echo_idx           <= 3'd0;
                        state_current      <= loopback_r ? ECHO : IDLE;
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // ---------------------------------------------------------------
                // RESET: both strobes high together resets the PLL registers.
                RST_HIGH: begin
                    pll_data_strb_o    <= 1'b1;
                    pll_cfg_vld_strb_o <= 1'b1;
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt           <= '0;
                        pll_data_strb_o    <= 1'b0;
                        pll_cfg_vld_strb_o <= 1'b0;
                        state_current      <= IDLE;
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // ---------------------------------------------------------------
                // READBACK: scan the shallow register out of data_o, MSB-first,
                // recirculating each captured bit back in so the register is
                // preserved (a full 47-bit rotation returns it to its prior value).
                // data_strb low: sample the (settled, synchronized) data_o = the
                // current MSB, capture it into read_result_r, and drive it back out
                // on pll_data_o so the next shift recirculates it.
                READ_LOW: begin
                    pll_data_strb_o <= 1'b0;
                    if (strb_cnt == '0) begin
                        // one capture per bit, at entry (input has settled since the
                        // previous shift, plus the 2-FF synchronizer latency).
                        read_result_r <= {read_result_r[PLL_CFG_BITS-2:0], pll_data_i_synced};
                        pll_data_o     <= pll_data_i_synced;  // recirculate
                    end
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt        <= '0;
                        pll_data_strb_o <= 1'b1;   // rising edge into READ_HIGH
                        state_current   <= READ_HIGH;
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // data_strb high: the PLL shifts the recirculated bit into bit 0.
                // After the last bit (bit_idx==0) the register has rotated full
                // circle; hand the captured 47 bits to ECHO as 6 LE bytes.
                READ_HIGH: begin
                    pll_data_strb_o <= 1'b1;
                    if (strb_cnt == strb_half_r - 1) begin
                        strb_cnt        <= '0;
                        pll_data_strb_o <= 1'b0;
                        if (bit_idx == 6'd0) begin
                            cfg_raw_r     <= {{(PLL_CFG_BYTES*8 - PLL_CFG_BITS){1'b0}}, read_result_r};
                            echo_idx      <= 3'd0;
                            state_current <= ECHO;
                        end else begin
                            bit_idx       <= bit_idx - 6'd1;
                            state_current <= READ_LOW;
                        end
                    end else begin
                        strb_cnt <= strb_cnt + 1'b1;
                    end
                end

                // ---------------------------------------------------------------
                // Echo the 6 bytes in cfg_raw_r back (LOAD_LOOPBACK payload, or the
                // READBACK result), same little-endian order as the LOAD payload.
                ECHO: begin
                    if (!fifo_pll_full_i) begin
                        fifo_pll_din_o   <= cfg_raw_r[echo_idx*8 +: 8];
                        fifo_pll_wr_en_o <= 1'b1;
                        if (echo_idx == 3'(PLL_CFG_BYTES) - 3'd1) begin
                            state_current <= IDLE;
                        end else begin
                            echo_idx <= echo_idx + 3'd1;
                        end
                    end
                end

                // STATUS: push one byte, bit0 = synchronized PLL lock.
                STATUS_PUSH: begin
                    if (!fifo_pll_full_i) begin
                        fifo_pll_din_o   <= 8'(pll_lock_synced) << PLL_STATUS_LOCK_BIT;
                        fifo_pll_wr_en_o <= 1'b1;
                        state_current    <= IDLE;
                    end
                end

                // WRITEBACK: echo the 0xFF header (controller-liveness check).
                WRITEBACK_PUSH: begin
                    if (!fifo_pll_full_i) begin
                        fifo_pll_din_o   <= {PLL_CMD_MARKER, PLL_OP_WRITEBACK};
                        fifo_pll_wr_en_o <= 1'b1;
                        state_current    <= IDLE;
                    end
                end

                default: state_current <= IDLE;
            endcase
        end
    end

endmodule

// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Behavioral quad-SPI slave model for the chip_controller unit testbench.
//
// It reproduces the protocol of the ETHz axi_spi_slave (hemaia_axi_spi_slave):
//   * SPI mode 0: MOSI sampled on the rising SCK edge, MISO changed on the
//     falling SCK edge.
//   * Powers up in standard SPI; Quad-SPI is enabled by command 0x01
//     (write reg0) followed by an 8-bit data byte whose bit0 sets en_quad.
//   * Command 0x02 = write mem, command 0x0B = read mem. Both are continuous:
//     data streams until CS is deasserted, with the word address auto-
//     incrementing by 4 (one 32-bit word) per transfer.
//   * A read inserts 33 dummy SCK cycles after the address (slave dummy
//     register = 32 plus the ETHz RX-counter off-by-one => 33 actual cycles),
//     then drives data MS-nibble first with bit[31] on sd[3].
//
// The model is edge driven, so it transparently tolerates the master pausing
// SCK at word boundaries (backpressure) - it simply waits for the next edge.

`timescale 1ns/1ps

module spi_slave_model (
    input  logic       sck,
    input  logic       csb,
    input  logic [3:0] sd_o,    // master -> bus (driven data)
    input  logic [3:0] sd_oe,   // master output enable (per line)
    output logic [3:0] sd_i     // bus -> master
);

    localparam int DUMMY_CYCLES = 33;

    logic        en_quad;
    logic [7:0]  reg0;
    logic [7:0]  cmd_r;
    logic [31:0] addr_r;
    logic [3:0]  miso;
    logic        slave_oe;
    logic [31:0] mem [logic [31:0]];

    // Tri-state bus resolution: the master drives a line when its output enable
    // is set; otherwise the slave drives it during read-data phases.
    for (genvar k = 0; k < 4; k++) begin : g_bus
        assign sd_i[k] = sd_oe[k] ? sd_o[k] : (slave_oe ? miso[k] : 1'b0);
    end

    // Receive one byte, 1 bit per rising edge on sd[0] (standard SPI, MSB first)
    task automatic recv_std_byte(output logic [7:0] b);
        for (int i = 7; i >= 0; i--) begin
            @(posedge sck); #1;
            b[i] = sd_o[0];
        end
    endtask

    // Receive n nibbles, 1 nibble per rising edge (quad SPI, MS-nibble first)
    task automatic recv_quad(input int n_nibbles, output logic [31:0] w);
        w = '0;
        for (int i = 0; i < n_nibbles; i++) begin
            @(posedge sck); #1;
            w = {w[27:0], sd_o[3:0]};
        end
    endtask

    // Drive one 32-bit word out, 1 nibble per falling edge (MS-nibble first)
    task automatic drive_quad_word(input logic [31:0] w);
        logic [31:0] sh;
        sh = w;
        for (int i = 0; i < 8; i++) begin
            @(negedge sck);
            miso = sh[31:28];
            sh   = {sh[27:0], 4'b0};
        end
    endtask

    task automatic run_frame();
        logic [7:0]  c, d;
        logic [31:0] tmp, a, dw;
        if (!en_quad) begin
            // Standard SPI: used to write reg0 and enable Quad-SPI.
            recv_std_byte(c);
            cmd_r = c;
            if (c == 8'h01) begin
                recv_std_byte(d);
                reg0    = d;
                en_quad = reg0[0];
            end
            // other standard commands are ignored by this model
        end else begin
            recv_quad(2, tmp);          // 8-bit command = 2 nibbles
            cmd_r = tmp[7:0];
            case (cmd_r)
                8'h02: begin            // write mem (continuous)
                    recv_quad(8, a);    // 32-bit start address
                    addr_r = a;
                    forever begin
                        recv_quad(8, dw);
                        mem[addr_r] = dw;
                        addr_r = addr_r + 32'd4;
                    end
                end
                8'h0B: begin            // read mem (continuous)
                    recv_quad(8, a);    // 32-bit start address
                    addr_r = a;
                    repeat (DUMMY_CYCLES) @(posedge sck);
                    slave_oe = 1'b1;
                    forever begin
                        drive_quad_word(mem.exists(addr_r) ? mem[addr_r] : 32'h0);
                        addr_r = addr_r + 32'd4;
                    end
                end
                default: ;              // unsupported command: ignore
            endcase
        end
    endtask

    initial begin
        en_quad  = 1'b0;
        reg0     = '0;
        miso     = '0;
        slave_oe = 1'b0;
        forever begin
            slave_oe = 1'b0;
            @(negedge csb);             // start of frame
            fork
                run_frame();
                @(posedge csb);         // CS high terminates the frame
            join_any
            disable fork;               // kill whichever child is still running
            if (csb !== 1'b1) @(posedge csb);
        end
    end

    // Helper for the testbench scoreboard to peek the model memory.
    function automatic logic [31:0] peek(input logic [31:0] byte_addr);
        return mem.exists(byte_addr) ? mem[byte_addr] : 32'h0;
    endfunction

endmodule

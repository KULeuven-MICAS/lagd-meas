`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company:
// Engineer:
//
// Create Date: 11/29/2017 11:37:19 AM
// Design Name:
// Module Name: spi_ads8332
// Project Name:
// Target Devices:
// Tool Versions:
// Description:
//
// Dependencies:
//
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
//
//////////////////////////////////////////////////////////////////////////////////


module spi_ads8331(
    input clk,
    input rst,

    // Control signals
    input wen,          // 1: write data_in to SPI interface
    input wlong,        // 1: write long command (4b + 12b); 0: write only data_in[15:12]
    input ren,          // 1: read data from SPI interface to data_out
    output reg ready,   // 1: SPI controller ready to accept new control

    // Data signals
    input       [15:0] data_in,
    output reg  [15:0] data_out,

    // SPI wires
    input din,
    output reg sync = 1'b1,
    output wire dout,
    output clk_out,
    output clk_out_en       // clock gate enable signal; use when sharing spi_clk among ADC buses
    );

    parameter IDLE  = 2'b00, WRITE_O = 2'b01, WRITE_READ = 2'b11; // READ_O = 2'b10 ;

    (* mark_debug = "true" *) reg [1:0] state = IDLE;
    reg [15:0] data;
    reg [3:0] nbit;
    reg wlong_r;
    reg dout_p;
    (* mark_debug = "true" *) reg clk_en = 0; // Addition to avoid noise on other wires

    reg shifter_en = 0;

    // shifter, cus fuck it
    always @(negedge clk) begin
        if(rst) begin
            data_out <= 0;
        end else if (shifter_en) begin
            data_out <= {data_out[14:0],din};
        end
    end

    // Interface is falling edge triggered on SCLK
    // sync setup time should be smaller than 5 ns
    // dout hold time should be larger than 8 ns
    always @(negedge clk) begin

        if(rst) begin

            state <= IDLE;
            data <= 0;
            nbit <= 0;
            wlong_r <= 1'b0;

            ready <= 0;
//            data_out <= 0;
            shifter_en <= 0;

            sync <= 1'b1;
            dout_p <= 1'b0;

            clk_en <= 1'b0;
        end

        else begin
            case(state)
                IDLE: begin
                    shifter_en <= 0;
                    if(sync & wen & ren) begin
                        data <= data_in;
                        nbit <= 15;
                        ready <= 1'b0;

                        dout_p <= data_in[15];
                        sync <= 1'b0;

                        state <= WRITE_READ;

                        clk_en <= 1'b1;
                    end
                    // Start a write only spi cycle
                    //
                    else if(sync & wen) begin
                        data <= data_in;
                        nbit <= 14;
                        wlong_r <= wlong;
                        ready <= 1'b0;

                        dout_p <= data_in[15];
                        sync <= 1'b0;

                        state <= WRITE_O;

                        clk_en <= 1'b1;
                    end
                    else if(sync & ren) begin
                        nbit <= 15;
                        ready <= 1'b0;
                        sync <= 1'b0;
                        // Even when reading the ADC performs write operations
                        // Thus rewrite last command each time
                        dout_p <= data[15];

                        // Only reading not possible so do write read
                        // without update of the internal data register
                        state <= WRITE_READ;
                        shifter_en <= 1;
                        clk_en <= 1'b1;
                    end
                    else begin

                        ready <= 1'b1;
                        sync <= 1'b1;
                        dout_p <= 1'b0;

                        clk_en <= 1'b0;
                    end

                end

                // Write out nbit 14 till 12 or 0 depending on wlong_r
                // Sync should go high once last bit is captured
                // Since capture takes place one cycle after launch
                // Sync high may not be set when bit 0 is written
                // But only when it is captured => already in IDLE state then
                WRITE_O: begin
                    nbit <= nbit - 1;

                    dout_p <= data[nbit];

                    if((~wlong) & (nbit == 12)) begin
                        state <= IDLE;
                    end
                    else if(nbit==0) begin
                        state <= IDLE;
                    end
                end

                /*
                Due to impossible read only for ADC
                this state would have te rewrite the previous
                data anyway => is identical to write_read
                // Read nbit 15 till 0.
                // Sync goes high after the last capture
                // => when switching to idle
                READ_O: begin
                    nbit <= nbit -1;

                    data_out[nbit] <= din;

                    // ADC always reads in data when sync is low
                    // so rewrite last command when read only is performed
                    if(nbit >= 1) begin
                        dout_p <= data[nbit-1];
                    end

                    if(nbit == 0) begin
                        state <= IDLE;
                        sync <= 1'b1;
                    end
                end
                */

                // Combine read and write
                // Writing is one cycle ahead of reading
                WRITE_READ: begin
                    nbit <= nbit - 1;

//                    data_out[nbit] <= din;
                    shifter_en <= 1;

                    if(nbit >= 1) begin
                        dout_p <= data[nbit-1];
                    end

                    if(nbit == 0) begin
                        shifter_en <= 0;
                        state <= IDLE;
                        sync <= 1'b1;
                    end
                end
                default: begin

                end
            endcase
        end

    end

    assign dout = dout_p;
/*    always @(negedge clk) begin
        dout <= dout_p;
    end*/

//    assign clk_out = clk;
    assign clk_out_en = clk_en;
    BUFHCE bufgce_i0 (
       .I(clk),
       .CE(clk_en),
       .O(clk_out)
    );


endmodule

`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company:
// Engineer:
//
// Create Date: 01/17/2018 09:16:24 AM
// Design Name:
// Module Name: spi_ad5724
// Project Name:
// Target Devices:
// Tool Versions:
// Description:
//    SPI controller for DAC AD5724 SPI protocol.
//    (is in essence a simple FSM with DESSER for SPI protocol)
//    Hardware is fixed to 2 daisy chained DACs.
//
// Dependencies:
//
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
//
//////////////////////////////////////////////////////////////////////////////////


module spi_ad5724(
    input clk,
    input rst,
    input wen,
    input [2:0] channel0,
    input [2:0] register0,
    input [15:0] data0,
    input [2:0] channel1,
    input [2:0] register1,
    input [15:0] data1,
    output reg busy,

    //DAC interface
    output reg  dac_syncb,
    output reg  dac_sdi,
    input       dac_sdo,
    output      clk_out
    );


     //=============Internal Constants======================
    parameter IDLE  = 2'b00, TRANS = 2'b01, WAIT_LOAD = 2'b10;

    reg [2:0] channel0_r;
    reg [2:0] register0_r;
    reg [15:0] data0_r;
    reg [2:0] channel1_r;
    reg [2:0] register1_r;
    reg [15:0] data1_r;
    reg [1:0] state = IDLE;
    reg [6:0] nbit;
    reg [3:0] load_timer;
    reg syncb;

    //reg [23:0] rdata_r;
    //assign rdata = rdata_r[15:0];
    //assign rdata_valid = ~ren_r;

    wire [47:0] word;
    assign word = {1'b0, 1'b0, register1_r, channel1_r, data1_r, 1'b0, 1'b0, register0_r, channel0_r, data0_r};

    //40ns - hold_delay_in_setup_corner - setup_delay is too tight
    //=> needs more constant way to fix hold
    always @(posedge clk) begin
        if (rst)
            dac_syncb = 1;
        else
            dac_syncb = syncb;
    end

    // SPI controller FSM
    //  clocked at negedge to give maximum timing margin, however setting
    //  setup and hold constraints on DAC IO signals becomes crucial!
    always @(negedge clk) begin
        if(rst) begin
            state <= IDLE;
            //rdata_r <= 0;
            data0_r <= 0;
            register0_r <= 0;
            channel0_r <= 0;
            data1_r <= 0;
            register1_r <= 0;
            channel1_r <= 0;
            busy <= 1'b0;
            syncb <= 1'b1;
            load_timer <= 0;
        end
        else begin
            // FSM state machine
            case(state)
                // Wait for a transaction to start
                IDLE: begin

                    if(wen & ~busy) begin
                        state <= TRANS;
                        channel0_r <= channel0;
                        register0_r <= register0;
                        data0_r <= data0;
                        channel1_r <= channel1;
                        register1_r <= register1;
                        data1_r <= data1;
                        nbit <= 23+24;      // in total transmit 2x24b = start from bit 47
                        // READ not implemented
                        //ren_r <= 0;
                        busy <= 1'b1;
                        syncb <= 1'b0;
                    end
                    else begin
                        busy <= 1'b0;
                        syncb <= 1'b1;
                    end
                end

                // Do the transaction of the specified number of bits
                // If transaction initiated no read operation go back to IDLE
                // Else start the read operation
                TRANS: begin
                    dac_sdi <= word[nbit];
                    // Transaction finished
                    if(nbit == 0) begin
                        load_timer <= 0;
                        state <= WAIT_LOAD;
                    end
                    else begin
                        nbit <= nbit - 1;
                    end
                end

                // Delay reading to satisfy syncb high time in readback mode
                WAIT_LOAD: begin
                    syncb <= 1'b1;

                    if(load_timer >= 3) begin
                        state <= IDLE;
                    end
                    else begin
                        load_timer <= load_timer + 1;
                    end
                end

                default: begin
                    state <= IDLE;
                    syncb <= 1'b1;
                end
            endcase
        end
    end


    BUFGCE bufgce_i0 (
       .I(clk),
       .CE(state!=IDLE),
       .O(clk_out)
    );
endmodule

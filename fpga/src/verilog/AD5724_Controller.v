`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company:
// Engineer:
//
// Create Date: 01/17/2018 10:10:26 AM
// Design Name:
// Module Name: AD5724_Controller
// Project Name:
// Target Devices:
// Tool Versions:
// Description:
//    Main controller for the DAC "AD5724":
//      * handles the 2x daisy chained DACs
//      * FSM with startup behavior + handling incoming update requests
//
// Dependencies:
//
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
//    * The way daisy chaining is implemented, no A[2] = 1 SPI-commands can be
//      send externally. This means we cannot invoke CLEAR ALL DAC OUTPUT and
//      LOAD ALL DAC OUTPUT from python.
//
//////////////////////////////////////////////////////////////////////////////////


module AD5724_Controller(
    input clk,
    input rst,
    input [15:0] data_in,     // control the DB[15..0] bits (dac_reg value mode ignores 4b LSB)
    input [2:0] register_in,  // control the REG[2..0] bits
    input [2:0] channel_in,   // 3bit: up to 2 daisy chained 4-ch DACs
    input update,
    output reg ready,

    //Signals towards DAC
    output dac_syncb,
    output dac_sdi,
    input  dac_sdo,
    output dac_sclk
    );

    //=============Internal Constants======================
    // FSM states
    parameter SET_RANGE  = 4'b0000, POWER_UP = 4'b0001, SET_CLR = 4'b0010, CLEAR = 4'b0011;
    parameter IDLE = 4'b0100, HOLD_TRANS = 4'b0101, WAIT_SPI_D = 4'b0110, WAIT_SPI = 4'b0111;
    parameter WAIT_POWERUP = 4'b1000, WAIT_CLEAR = 4'b1001;

    parameter POWERUP_TIME = 500, CLEAR_TIME = 250;
    // DAC_REG[2..0] values
    parameter RANGE_CONTROL = 3'b001, POWER_CONTROL = 3'b010, CONTROL = 3'b011;

    (* mark_debug = "true" *) reg [3:0] state = SET_RANGE, next_state;
    reg [2:0] channel;
    reg [15:0] data;
    reg [2:0] register;
    reg wen;
    reg [9:0] delay_timer;
    reg [2:0] channel0;
    reg [15:0] data0;
    reg [2:0] register0;
    reg [2:0] channel1;
    reg [15:0] data1;
    reg [2:0] register1;

    wire busy;

    // DAC controller FSM
    always @(posedge clk) begin
        if(rst) begin
            state <= SET_RANGE;
            delay_timer <= 0;
            ready <= 1'b0;
            wen <= 1'b0;
            channel <= 0;
            register <= 0;
            data <= 0;
        end
        else begin

            case(state)
                // note by bob: we are going to silently ignore the built-in reset schedule here, and do it our-selve from software.
                // First state, starts the DAC
                // Only accessible through reset, which is released after opening one of the PERIP FIFOs

                // Set all dac_channels to +5V range
                SET_RANGE: begin
                    ready <= 1'b0;
                    register <= RANGE_CONTROL;
                    channel <= 3'b100;
                    data <= {13'b0000000000000,3'b000};
                    wen <= 1'b1;

                    state <= WAIT_SPI_D;
                    next_state <= POWER_UP;
                end

                // Place all 4 DAC outputs in power-on mode
                POWER_UP: begin
                    ready <= 1'b0;
                    register <= POWER_CONTROL;
                    channel <= 3'b000;
                    data <= {12'b000000000000,4'b1111};
                    wen <= 1'b1;

                    state <= WAIT_SPI_D;
                    next_state <= WAIT_POWERUP;
                    delay_timer <= 0;
                end

                WAIT_POWERUP: begin
                    if (delay_timer >= POWERUP_TIME) begin
                        delay_timer <= 0;
                        state <= SET_CLR;
                    end
                    else begin
                        delay_timer <= delay_timer + 1;
                    end
                end

                // After reset, set the clear code for all channels to 0
                // + enable the 20mA current clamp
                SET_CLR: begin
                    ready <= 1'b0;
                    register <= CONTROL;
                    channel <= 3'b001;
                    data <=  {12'b000000000000,4'b0100};
                    wen <= 1'b1;

                    state <= WAIT_SPI_D;
                    next_state <= CLEAR;
                    delay_timer <= 0;
                end

                // With clear code set,
                // Clear the channels
                CLEAR: begin
                    ready <= 1'b0;
                    register <= CONTROL;
                    channel <= 3'b100;
                    data <=  {12'b000000000000,4'b0000};
                    wen <= 1'b1;

                    state <= WAIT_CLEAR;
                    next_state <= IDLE;
                end

                WAIT_CLEAR: begin
                    if (delay_timer >= CLEAR_TIME) begin
                        delay_timer <= 0;
                        state <= IDLE;
                    end
                    else begin
                        delay_timer <= delay_timer + 1;
                    end
                end

                // Wait for a new update to arrive
                // When it arrives check if the spi
                // is ready to process it.
                // Without update, signal that the controller
                // is ready for an update => ready high
                IDLE: begin
                    if(update) begin
                        register <= register_in;
                        channel <= channel_in;
                        data <= data_in;
                        ready <= 1'b0;

                        if(~busy) begin
                            wen <= 1'b1;
                            state <= WAIT_SPI_D;
                            next_state <= IDLE;
                        end
                        else begin
                            state <= HOLD_TRANS;
                        end
                    end
                    else begin
                        ready <= 1'b1;
                    end
                end

                // Wait with the execution of a transaction
                // until the spi interface is not busy
                HOLD_TRANS: begin
                    if(~busy) begin
                        wen <= 1'b1;
                        state <= WAIT_SPI_D;
                        next_state <= IDLE;
                    end
                end

                // Hold the state machine until
                // the busy signal from the spi
                // interface drops low.
                // Next proceed to predefined next_state
                WAIT_SPI_D: begin
                    state <= WAIT_SPI;
                end
                WAIT_SPI: begin
                    wen <= 1'b0;
                    if(~busy) begin
                        state <= next_state;
                    end
                end

                default: begin
                    state <= SET_RANGE;
                end
            endcase
        end
    end

    // channel,register,data demux
    // DAC daisy chain control
    always @(channel_in or channel or register or data) begin
        // if configuration instruction, write to both dac's
        if (register!=3'b000) begin
            channel0 <= channel;
            channel1 <= channel;
            register0 <= register;
            register1 <= register;
            data0 <= data;
            data1 <= data;
        // if dac instruction and channel is < 4, then write to first dac
        end else if (channel_in[2] == 1'b0) begin
            channel0 <= channel;
            channel1 <= 3'b0;
            register0 <= register;
            register1 <= 3'b011;    // send a NOP
            data0 <= data;
            data1 <= 16'b0;
        // if dac instruction and channel >=4, then write to second dac
        end else begin
            channel0 <= 3'b0;
            channel1 <= {1'b0,channel[1:0]}; //note: the channel should be brought back to 4 channels!
            register0 <= 3'b011;
            register1 <= register;
            data0 <= 16'b0;
            data1 <= data;
        end
    end

    spi_ad5724 spi_interface (
        .clk        (clk),
        .rst        (rst),
        .wen        (wen),
        .channel0   (channel0),
        .register0  (register0),
        .data0      (data0),
        .channel1   (channel1),
        .register1  (register1),
        .data1      (data1),
        .busy       (busy),
        .dac_syncb  (dac_syncb),
        .dac_sdi    (dac_sdi),
        .dac_sdo    (dac_sdo),
        .clk_out    (dac_sclk)
        );
endmodule

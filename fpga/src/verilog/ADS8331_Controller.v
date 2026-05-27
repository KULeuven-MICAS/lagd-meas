`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company:
// Engineer:
//
// Create Date: 11/29/2017 02:13:54 PM
// Design Name:
// Module Name: ADS8332_controller
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

// Controller for the ADS8332 ADC
// Should be clocked at the desired spi operating speed

module ADS8331_Controller(
    input clk,
    input rst,

    // control in
    input [2:0] channel,
    input [11:0] configuration,
    input update_command,         // channel[2:0] will be updated to ADC
    input update_configuration,   // configuration[11:0] will be updated to ADC (needs also update_command=1)
    input sample,

    // control out
    output reg ready,             // ready to accept new control
    output reg new_data,          // 1 cycle pulse when new data is available

    // data out
    output reg [15:0] data,

    // device control out
    output reg adc_convst, // active low
    // device control in
    input  adc_eoc_i,

    // spi connections
    input  adc_sdo,
    output adc_fs,
    output adc_sdi,
    output adc_sclk,
    output adc_sclk_en    // sclk clock gate enable; use when sharing sclk among multiple ADC controllers
    );

    // FSM states
    parameter STARTUP = 4'b0000, WAIT_TIME = 4'b0001, SET_CONF = 4'b0010, WAIT_SPI = 4'b0011;
    parameter IDLE = 4'b0100, SET_COMM = 4'b0101, SAMPLE = 4'b0110, WAIT_EOC = 4'b0111;
    parameter READ = 4'b1000, NEW_DATA = 4'b1001;

    parameter START_CONF = 12'b011111111101;
    parameter MINIMAL_WAIT = 2;
    //parameter MINIMAL_WAIT = 1;//todo: bob aangepast omdat het kan omdat de adcs niet werken



    // SPI control registers
    reg spi_wen, spi_ren, spi_wlong;    // control to spi_ads8331 controller
    reg set_conf;
    wire spi_ready;
    (* mark_debug = "true" *) wire [15:0] spi_data;

    // Internal registers
    (* mark_debug = "true" *) reg [3:0] state = STARTUP;
    (* mark_debug = "true" *) reg [3:0] next_state = STARTUP;
    reg [20:0] timer;

    //to debug:
    (* mark_debug = "true" *) reg [3:0] debug_state = STARTUP;
    always @(posedge clk) begin
        debug_state = state;
    end

    // extra: debouncing of adc_eoc
    reg adc_eoc, adc_eoc_d, adc_eoc_dd;
    always @(posedge clk) begin
        if (rst) begin
            adc_eoc <= 0;
            adc_eoc_d <= 0;
            adc_eoc_dd <= 0;
        end else begin
            adc_eoc <= adc_eoc_i;
            adc_eoc_d <= adc_eoc;
            adc_eoc_dd <= adc_eoc_d;
        end
    end

    always @(posedge clk) begin
        if(rst) begin
            timer <= 0;
            ready <= 1'b0;
            new_data <= 1'b0;
            data <= 0;
            adc_convst <= 1'b1;

            spi_wen <= 1'b0;
            spi_ren <= 1'b0;
            spi_wlong <= 1'b0;
            set_conf <= 1'b0;

            state <= STARTUP;
            next_state <= STARTUP;

        end
        else begin
            case(state)
                // AD5390 startup triggers reset, wait for this general reset to stop
                STARTUP: begin
                    adc_convst <= 1'b1; // This seems needed as we don't have a reset
                    timer <= 20;
                    ready <= 1'b0;
                    new_data <= 1'b0;

                    state <= WAIT_TIME;
                    next_state <= SET_CONF;
                end

                IDLE: begin
                    new_data <= 1'b0;
                    set_conf <= 1'b0;

                    // Command updating has priority
                    if(update_command) begin
                        ready <= 1'b0;
                        if(update_configuration) begin
                            state <= SET_CONF;
                        end
                        else begin
                            state <= SET_COMM;
                        end
                    end
                    // Sampling = new conversion at current channel + data read
                    else if(sample) begin
                        ready <= 1'b0;
                        state <= SAMPLE;
                    end
                    // Do nothing
                    else begin
                        ready <= 1'b1;
                    end
                end

                // if the spi interface is ready
                // start the configure write
                SET_CONF: begin
                    if(spi_ready) begin
                        spi_wen <= 1'b1;
                        spi_wlong <= 1'b1;
                        spi_ren <= 1'b0;
                        set_conf <= 1'b1;

                        timer <= 0;
                        state <= WAIT_SPI;
                        next_state <= IDLE;
                    end
                end
                // if the spi interface is ready
                // start the command write
                SET_COMM: begin
                    if(spi_ready) begin
                        spi_wen <= 1'b1;
                        spi_wlong <= 1'b0;
                        spi_ren <= 1'b0;

                        timer <= 0;
                        state <= WAIT_SPI;
                        next_state <= IDLE;
                    end
                end

                SAMPLE: begin
                    // Start a conversion if none is busy
                    if(adc_eoc | adc_eoc_d | adc_eoc_dd) begin
                        adc_convst <= 1'b0;
                    end
                    // If busy check if this conversion is the cause
                    // If so move on, else wait
                    if(~adc_eoc & ~adc_convst) begin
                        state <= WAIT_EOC;
                        next_state <= READ;
                        adc_convst <= 1'b1;
                    end
                end

                READ: begin
                    spi_ren <= 1'b1;
                    spi_wen <= 1'b0;
                    timer <= 0;
                    state <= WAIT_SPI;
                    next_state <= NEW_DATA;
                end

                NEW_DATA: begin
                    data <= spi_data;
                    new_data <= 1'b1;
                    state <= IDLE;
                end

                // Simple configurable wait state
                WAIT_TIME: begin
                    timer <= timer - 1;
                    if(timer == 0) begin
                        state <= next_state;
                    end
                end
                // Simple wait spi_ready with minimal wait options
                WAIT_SPI: begin
                    spi_wen <= 1'b0;
                    spi_ren <= 1'b0;
                    if((spi_ready) & (timer >= MINIMAL_WAIT)) begin
                        timer <= 0;
                        state <= next_state;
                    end
                    else if(timer < MINIMAL_WAIT) begin
                        timer <= timer + 1;
                    end
                end
                // Wait for the end of a conversion
                WAIT_EOC: begin
                    if(adc_eoc) begin
                        state <= next_state;
                    end
                end
                default: begin
                    state <= STARTUP;
                end
            endcase
        end


    end

    // data_in is either:
    //  set_conf=1: {4'b1110, configuration} --> sending configuration CFR to ADC
    //  set_conf=0: {1'b0, channel, configuration} --> sending which analog input channel to use
    //    -- note that the last 12b are dont care anyway
    /*wire dummy;*/
    wire adc_sclk_en;
    spi_ads8331 spi_ads8331_inst (
        .clk      (clk),
        .rst      (rst),
        // Control signals
        .wen      (spi_wen),
        .wlong    (spi_wlong),
        .ren      (spi_ren),
        .ready    (spi_ready),
        // Data signals
        .data_in  ({(set_conf) ? 4'b1110 : {1'b0,channel} ,configuration}),
        .data_out (spi_data),
        // Spi wires
        .din      (adc_sdo),
        .sync     (adc_fs),
        .dout     (adc_sdi),
        .clk_out  (adc_sclk/*dummy*/),
        .clk_out_en   (adc_sclk_en)
        );

    /*
    BUFGCE bufgce_i0 (
       .I(clk),
       .CE((state!=SAMPLE)&&(state!=WAIT_EOC)),
       .O(adc_sclk)
    );*/
endmodule

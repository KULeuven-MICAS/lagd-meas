/*
PERIP_CONTROLLER

Processes the FIFO-PERIP commands as defined by the PERIP_COMMAND API

CHANGELOG
v1.0, 17-12-2021  Start basic controller with write_back functionality. (copied from previous repo)
                  Add simple LED control as example
v1.1, 20-12-2021  Insert supply DAC and ADC control from bvanhoof's code
*/

module perip_controller (
  input  clk_20,   // should be 20MHz clk for reliable DAC/ADC control
  (* direct_reset = "yes" *) input  rst,

  // Connection to fifo
  // perip fifo input (from linux)
  output reg        fifo_perip_rd_en,
  input             fifo_perip_empty,
  input  [31:0]     fifo_perip_dout,
  // perip fifo output (to linux)
  output reg        fifo_perip_wr_en,
  input             fifo_perip_full,
  output reg [31:0] fifo_perip_din,

  // -- Misc pins -- //
  // user_led: leds LD[7..4] on zedboard PCB
  output reg [3:0]  user_led,

  // -- Project specific pins -- //
  // dac1: DAC_LV
  output reg  dac1_sclk,
  output reg  dac1_sdin,
  input       dac1_sdo,
  output reg  dac1_syncbar,
  // dac2: DAC_MV
  output reg  dac2_sclk,
  output reg  dac2_sdin,
  input       dac2_sdo,
  output reg  dac2_syncbar,
  // adc1: ADC_LV
  output reg  adc1_sclk,        // sclk shared among adc1,2,3
  output reg  adc1_sdin,
  input       adc1_sdo,
  output reg  adc1_csbar,
  output reg  adc1_convstbar,
  input       adc1_status,
  // adc2: ADC_MVHV
  output reg  adc2_sdin,
  input       adc2_sdo,
  output reg  adc2_csbar,
  output reg  adc2_convstbar,
  input       adc2_status,
  // adc3: ADC_BIAS
  output reg  adc3_sdin,
  input       adc3_sdo,
  output reg  adc3_csbar,
  output reg  adc3_convstbar,
  input       adc3_status
  );

  //////////////////////////////////////////////////////////////////////////////
  ////    INSTRUCTION HANDLING     ////
  //////////////////////////////////////////////////////////////////////////////

  // make fallthrough read registers
  logic fifo_perip_ft_empty;
  (* mark_debug = "true" *) logic[31:0] fifo_perip_ft_dout;
  (* mark_debug = "true" *) logic fifo_perip_ft_re;
  non_fallthrough_to_fallthrough#(.width(32)) nftf_perip_inst(
    .clk          (clk_20),
    .rst          (rst),
    .fifo_empty   (fifo_perip_empty),
    .fifo_data    (fifo_perip_dout),
    .fifo_re      (fifo_perip_rd_en),
    .output_empty (fifo_perip_ft_empty),
    .output_data  (fifo_perip_ft_dout),
    .output_re    (fifo_perip_ft_re));

  // perip_command
  //  actual perip_command API: see perip_command_api.sv
  (* mark_debug = "true" *) perip_command_t perip_command;
  (* mark_debug = "true" *) logic           perip_command_we;
  (* mark_debug = "true" *) logic [3:0]     perip_command_opcode;

  reg_rst #(.WIDTH(32)) perip_command_reg_inst(
    .clk    (clk_20),
    .rst    (rst),
    .din    (fifo_perip_ft_dout),
    .qout   (perip_command.bitwise),
    .wen    (perip_command_we)
  );

  assign perip_command_opcode = perip_command.led_ctrl.opcode;


  //////////////////////////////////////////////////////////////////////////////
  ////    PERIP CONTROL MASTER FSM    ////
  //////////////////////////////////////////////////////////////////////////////

  // PERIP_COUNTER
  //  General purpose counter for perip control FSM
  logic perip_counter_rst, perip_counter_en;      // FSM control sigs
  (* mark_debug = "true" *) logic [15:0] perip_counter;
  bv_counter #(.WIDTH(16)) chip_counter_inst (
      .clk                (clk_20),
      .rst                (rst || perip_counter_rst),
      .counter_inc        (perip_counter_en),
      .counter_load       ('b0),
      .counter_load_value ('b0),
      .counter_val        (perip_counter)
  );

  // FSM STATE AND NEXTSTATE
  typedef enum {IDLE, PROCESS, SAMPLE, WAIT_SAMPLE, WAIT_ADC, WAIT_DAC} perip_ctrl_state_t;
  (* mark_debug = "true" *) perip_ctrl_state_t CS;   // current state
  perip_ctrl_state_t NS;                             // next state

  // NOTE, Bob had rst on sensitivity list..
  always @(posedge clk_20) begin
      if(rst) begin
          CS <= IDLE;
      end else begin
          CS <= NS;
      end
  end

  // FSM CONTROL SIGNALS
  //  supply ADCs
  logic adc1_update_command, adc1_update_config, adc1_sample;
  logic adc1_ready, adc1_new_data;
  logic[15:0] adc1_data;
  logic adc2_update_command, adc2_update_config, adc2_sample;
  logic adc2_ready, adc2_new_data;
  logic[15:0] adc2_data;
  logic adc3_update_command, adc3_update_config, adc3_sample;
  logic adc3_ready, adc3_new_data;
  logic[15:0] adc3_data;
  //  supply DACs
  logic dac1_update, dac1_ready;
  logic dac2_update, dac2_ready;
  //  misc
  logic writeback_perip_command;
  logic user_led_update;            // user request for LED update

  // ACTUAL FSM
  always_comb begin
      // Default controlsig values
      //  misc
      NS <= CS;
      writeback_perip_command   <= 0;
      user_led_update           <= 0;
      //  Xillybus FIFO control commands
      fifo_perip_ft_re <= 0;   // read enable
      perip_command_we <= 0;   // perip command write enable
      //  FSM counter
      perip_counter_rst <= 0;   // active high
      perip_counter_en  <= 0;
      //  adc control signals
      adc1_update_command <= 0;
      adc1_update_config <= 0;
      adc1_sample <= 0;
      adc2_update_command <= 0;
      adc2_update_config <= 0;
      adc2_sample <= 0;
      adc3_update_command <= 0;
      adc3_update_config <= 0;
      adc3_sample <= 0;
      //  dac control signals
      dac1_update <= 0;
      dac2_update <= 0;

      case(CS)
          IDLE: begin
              // accept new periph_command from FIFO
              fifo_perip_ft_re <= 1;
              if(!fifo_perip_ft_empty) begin
                  NS <= PROCESS;
                  perip_command_we <= 1;
              end
          end
          PROCESS: begin
              case(perip_command_opcode)
                  PCB_DAC_COMMAND: begin
                      if(perip_command.dac.bus==0 && dac1_ready) begin
                          NS <= WAIT_DAC;
                          dac1_update <= 1;
                      end else if(perip_command.dac.bus == 1 && dac2_ready) begin
                          NS <= WAIT_DAC;
                          dac2_update <= 1;
                      end
                  end
                  PCB_ADC_COMMAND: begin
                      if(perip_command.adc_conf.bus==0 && adc1_ready) begin
                          NS <= WAIT_ADC;
                          adc1_update_command <= 1;
                      end else if(perip_command.adc_conf.bus==1 && adc2_ready) begin
                          NS <= WAIT_ADC;
                          adc2_update_command <= 1;
                      end else if(perip_command.adc_conf.bus==2 && adc3_ready) begin
                          NS <= WAIT_ADC;
                          adc3_update_command <= 1;
                      end
                  end
                  PCB_ADC_CONFIG: begin
                      if(perip_command.adc_conf.bus==0 && adc1_ready) begin
                          NS <= WAIT_ADC;
                          adc1_update_command <= 1;
                          adc1_update_config <= 1;
                      end else if (perip_command.adc_conf.bus==1 && adc2_ready) begin
                          NS <= WAIT_ADC;
                          adc2_update_command <= 1;
                          adc2_update_config <= 1;
                      end else if (perip_command.adc_conf.bus==2 && adc3_ready) begin
                          NS <= WAIT_ADC;
                          adc3_update_command <= 1;
                          adc3_update_config <= 1;
                      end
                  end
                  PCB_ADC_SAMPLE: begin
                      // Only allow 1 ADC simultaneous active to avoid missing ADC_SAMPLE data in writeback FIFO
                      if(adc1_ready && adc2_ready && adc3_ready) begin
                          NS <= SAMPLE;
                          perip_counter_rst <= 1;    // for counting adc_sample.length
                      end
                  end
                  LED_CTRL: begin
                      NS <= IDLE;
                      user_led_update <= 1;
                  end
                  TEST_WRITEBACK_PERIPFIFO: begin
                      NS <= IDLE;
                      writeback_perip_command <= 1;
                  end
              endcase
          end
          SAMPLE: begin
              NS <= WAIT_SAMPLE;
              if(perip_command.adc_sample.bus==0) begin
                  adc1_sample <= 1;
              end else if (perip_command.adc_sample.bus==1) begin
                  adc2_sample <= 1;
              end else if (perip_command.adc_sample.bus==2) begin
                  adc3_sample <= 1;
              end
          end
          WAIT_SAMPLE: begin
              if(adc1_ready && adc2_ready && adc3_ready) begin
                  perip_counter_en <= 1;
                  if (perip_counter < perip_command.adc_sample.length) begin
                      NS <= SAMPLE;
                  end else begin
                      NS <= IDLE;
                  end
              end
          end
          WAIT_ADC: begin
              if (perip_command.adc_conf.bus == 0 && adc1_ready) begin
                  NS <= IDLE;
              end else if (perip_command.adc_conf.bus == 1 && adc2_ready) begin
                  NS <= IDLE;
              end else if (perip_command.adc_conf.bus == 2 && adc3_ready) begin
                  NS <= IDLE;
              end
          end
          WAIT_DAC: begin
              // [tbos] weird state; you will only wait here when both DACs are busy
              // note that no new dac_cmds will be missed, that is taken care of by PROCESS state
              // [tbos]: this feels as a useless state that could be deleted..
              if(dac1_ready || dac2_ready) begin
                  NS <= IDLE;
              end
          end

          default: begin
              NS <= IDLE;
          end
      endcase
  end

  //////////////////////////////////////////////////////////////////////////////
  ////    WRITE BACK BUFFER    ////
  //////////////////////////////////////////////////////////////////////////////
  // Control what is written to the PERI FIFO fgpa->linux
  always_comb begin
      // default value
      fifo_perip_wr_en <= 0;

      // enable fifo if any signal is high and the fifo is not full. If the fifo is full, the data is discarded.
      if(!fifo_perip_full && ( adc1_new_data || adc2_new_data || adc3_new_data || writeback_perip_command ) ) begin
          fifo_perip_wr_en <= 1;
      end

      // mux data
      if (adc1_new_data) begin
          fifo_perip_din <= {16'h0000,adc1_data};
      end else if (adc2_new_data) begin
          fifo_perip_din <= {16'h1000,adc2_data};
      end else if (adc3_new_data) begin
          fifo_perip_din <= {16'h2000,adc3_data};
      end else if (writeback_perip_command) begin
        fifo_perip_din  <= perip_command.bitwise;
      end else begin
        fifo_perip_din <= 'b0;
      end
  end

  //////////////////////////////////////////////////////////////////////////////
  ////    ADC AND DAC CONTROL SUBMODULES    ////
  //////////////////////////////////////////////////////////////////////////////

  // ADC MODULES
  //  share the ADC SPI clock among all 3 ADC busses

  // Generate shared ADC SCLK
  wire adc1_sclk_en, adc2_sclk_en, adc3_sclk_en;
  BUFHCE bufgce_adc_sclk (
     .I(clk_20),
     .CE(adc1_sclk_en || adc2_sclk_en || adc3_sclk_en),
     .O(adc1_sclk)
  );

  ADS8331_Controller adc1_controller (
      .clk                  (clk_20),
      .rst                  (rst),
      .channel              (perip_command.adc_conf.channel),
      .configuration        (perip_command.adc_conf.conf),
      .update_command       (adc1_update_command),
      .update_configuration (adc1_update_config),
      .sample               (adc1_sample),
      .ready                (adc1_ready),
      .new_data             (adc1_new_data),
      .data                 (adc1_data),
      // SPI wires
      .adc_convst           (adc1_convstbar),
      .adc_eoc_i            (adc1_status),
      .adc_sdo              (adc1_sdo),
      .adc_fs               (adc1_csbar),
      .adc_sdi              (adc1_sdin),
      .adc_sclk             (),             // do not use sclk, use sclk_en to create shared sclk
      .adc_sclk_en          (adc1_sclk_en));

  ADS8331_Controller adc2_controller (
      .clk                  (clk_20),
      .rst                  (rst),
      .channel              (perip_command.adc_conf.channel),
      .configuration        (perip_command.adc_conf.conf),
      .update_command       (adc2_update_command),
      .update_configuration (adc2_update_config),
      .sample               (adc2_sample),
      .ready                (adc2_ready),
      .new_data             (adc2_new_data),
      .data                 (adc2_data),
      // SPI wires
      .adc_convst           (adc2_convstbar),
      .adc_eoc_i            (adc2_status),
      .adc_sdo              (adc2_sdo),
      .adc_fs               (adc2_csbar),
      .adc_sdi              (adc2_sdin),
      .adc_sclk             (),
      .adc_sclk_en          (adc2_sclk_en));

  ADS8331_Controller adc3_controller (
      .clk                  (clk_20),
      .rst                  (rst),
      .channel              (perip_command.adc_conf.channel),
      .configuration        (perip_command.adc_conf.conf),
      .update_command       (adc3_update_command),
      .update_configuration (adc3_update_config),
      .sample               (adc3_sample),
      .ready                (adc3_ready),
      .new_data             (adc3_new_data),
      .data                 (adc3_data),
      // SPI wires
      .adc_convst           (adc3_convstbar),
      .adc_eoc_i            (adc3_status),
      .adc_sdo              (adc3_sdo),
      .adc_fs               (adc3_csbar),
      .adc_sdi              (adc3_sdin),
      .adc_sclk             (),
      .adc_sclk_en          (adc3_sclk_en));

  // DAC MODULES

  AD5724_Controller dac1_controller (
      .clk        (clk_20),
      .rst        (rst),
      .data_in    (perip_command.dac.data),
      .register_in(perip_command.dac.register),
      .channel_in (perip_command.dac.channel),
      .update     (dac1_update),
      .ready      (dac1_ready),
      .dac_syncb  (dac1_syncbar),
      .dac_sdi    (dac1_sdin),
      .dac_sdo    (dac1_sdo),
      .dac_sclk   (dac1_sclk));

  AD5724_Controller dac2_controller (
      .clk        (clk_20),
      .rst        (rst),
      .data_in    (perip_command.dac.data),
      .register_in(perip_command.dac.register),
      .channel_in (perip_command.dac.channel),
      .update     (dac2_update),
      .ready      (dac2_ready),
      .dac_syncb  (dac2_syncbar),
      .dac_sdi    (dac2_sdin),
      .dac_sdo    (dac2_sdo),
      .dac_sclk   (dac2_sclk));

  //////////////////////////////////////////////////////////////////////////////
  ////    SMALL MODULES    ////
  //////////////////////////////////////////////////////////////////////////////
  // Small modules or registers, not put in separate module

  // LED control
  //  user_led_update -> reg write_enable
  logic [3:0] user_led_next;
  assign user_led_next = perip_command.led_ctrl.user_led;
  reg_rst #(.WIDTH(4)) user_led_reg_inst(
      .clk  (clk_20),
      .rst  (rst),
      .din  (user_led_next),
      .qout (user_led),
      .wen  (user_led_update));
  // Shorter notation:
  // `REG(4, user_led, clk);
  // assign user_led_we = user_led_update;


endmodule

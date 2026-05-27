// Copyright 2025 KU Leuven.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

// Author: Jiacong Sun <jiacong.sun@kuleuven.be>
//
// Source file is written by Thomas Bos
// Description:
//   Toplevel module of xillinux bitstream

// CHANGELOG
//   v1.0, 17-12-2021  Copy from xillinux source files (xillinux/verilog/src/)
//   v1.1, 17-12-2021  Add 2x RW FIFO streams from corebundle/template.v (see corebundle/readme.txt)


module xillydemo
  (
  // Xillydemo default IO pins
  input  clk_100,
  input  otg_oc,
  inout [55:0] PS_GPIO,
  output [3:0] GPIO_LED,
  output [3:0] vga4_blue,
  output [3:0] vga4_green,
  output [3:0] vga4_red,
  output  vga_hsync,
  output  vga_vsync,

  output  audio_mclk,
  output  audio_dac,
  input   audio_adc,
  input   audio_bclk,
  input   audio_lrclk,

  output smb_sclk,
  inout  smb_sdata,
  output [1:0] smbus_addr,

  // PROJECT Specific IO pins
  output [3:0] user_led,      // connect to LD[7..4]

  // DAC SPI (#TODO: ports below are to be renamed or cleaned)
  output dac1_sclk,
  (* mark_debug = "true" *) output dac1_sdin,
  (* mark_debug = "true" *) input  dac1_sdo,
  (* mark_debug = "true" *) output dac1_syncbar,

  // -- CHIP SPI (freq_sel_controller / spi_image_tester → custom chip SPI slave)
  // Pmod JA: JA1=sck, JA2=csb, JA3=SD0, JA4=SD1, JA7=SD2, JA8=SD3  (LVCMOS33)
  (* mark_debug = "true" *) output chip_sck,
  (* mark_debug = "true" *) output chip_csb,
  inout  [3:0] chip_sd   // Quad-SPI bidirectional data
  );


  /////////////////////////////////////////////////////////
  ////    XILLYBUS LEGACY: XILLYBUS WIRES + MODULE     ////
  /////////////////////////////////////////////////////////
  // Copied from corebundle/template.v
  // Dont touch Xillybus wires/regs/modules

  // Clock and quiesce
  wire  bus_clk;
  wire  quiesce;

  // Memory arrays

  reg [7:0] litearray0[0:31];
  reg [7:0] litearray1[0:31];
  reg [7:0] litearray2[0:31];
  reg [7:0] litearray3[0:31];

  // Wires related to /dev/xillybus_mem_32
  wire  user_r_mem_32_rden;
  wire  user_r_mem_32_empty;
  reg  [31:0] user_r_mem_32_data;
  wire  user_r_mem_32_eof;
  wire  user_r_mem_32_open;
  wire  user_w_mem_32_wren;
  wire  user_w_mem_32_full;
  wire [31:0] user_w_mem_32_data;
  wire  user_w_mem_32_open;
  wire [4:0] user_mem_32_addr;
  wire  user_mem_32_addr_update;

  // Wires related to /dev/xillybus_read_32
  wire  user_r_read_32_rden;
  wire  user_r_read_32_empty;
  wire [31:0] user_r_read_32_data;
  wire  user_r_read_32_eof;
  wire  user_r_read_32_open;

  // Wires related to /dev/xillybus_read_32_2
  wire  user_r_read_32_2_rden;
  wire  user_r_read_32_2_empty;
  wire [31:0] user_r_read_32_2_data;
  wire  user_r_read_32_2_eof;
  wire  user_r_read_32_2_open;

  // Wires related to /dev/xillybus_read_8
  wire  user_r_read_8_rden;
  wire  user_r_read_8_empty;
  wire [7:0] user_r_read_8_data;
  wire  user_r_read_8_eof;
  wire  user_r_read_8_open;

  // Wires related to /dev/xillybus_write_32
  wire  user_w_write_32_wren;
  wire  user_w_write_32_full;
  wire [31:0] user_w_write_32_data;
  wire  user_w_write_32_open;

  // Wires related to /dev/xillybus_write_32_2
  wire  user_w_write_32_2_wren;
  wire  user_w_write_32_2_full;
  wire [31:0] user_w_write_32_2_data;
  wire  user_w_write_32_2_open;

  // Wires related to /dev/xillybus_write_8
  wire  user_w_write_8_wren;
  wire  user_w_write_8_full;
  wire [7:0] user_w_write_8_data;
  wire  user_w_write_8_open;

  // Wires related to /dev/xillybus_audio
  wire  user_r_audio_rden;
  wire  user_r_audio_empty;
  wire [31:0] user_r_audio_data;
  wire  user_r_audio_eof;
  wire  user_r_audio_open;
  wire  user_w_audio_wren;
  wire  user_w_audio_full;
  wire [31:0] user_w_audio_data;
  wire  user_w_audio_open;
  // xillybus_audio is removed
  assign user_r_audio_rden = 0;
  assign user_r_audio_open = 0;
  assign user_w_audio_wren = 0;
  assign user_w_audio_data = 0;
  assign user_w_audio_open = 0;

  // Wires related to /dev/xillybus_smb
  wire  user_r_smb_rden;
  wire  user_r_smb_empty;
  wire [7:0] user_r_smb_data;
  wire  user_r_smb_eof;
  wire  user_r_smb_open;
  wire  user_w_smb_wren;
  wire  user_w_smb_full;
  wire [7:0] user_w_smb_data;
  wire  user_w_smb_open;

  // Wires related to Xillybus Lite
  wire  user_clk;
  wire  user_wren;
  wire  user_rden;
  wire [3:0] user_wstrb;
  wire [31:0] user_addr;
  reg  [31:0] user_rd_data;
  wire [31:0] user_wr_data;
  wire  user_irq;

  // Note that none of the ARM processor's direct connections to pads is
  // attached in the instantion below. Normally, they should be connected as
  // toplevel ports here, but that confuses Vivado 2013.4 to think that
  // some of these ports are real I/Os, causing an implementation failure.
  // This detachment results in a lot of warnings during synthesis and
  // implementation, but has no practical significance, as these pads are
  // completely unrelated to the FPGA bitstream.

  xillybus xillybus_ins (
    // Ports related to /dev/xillybus_mem_32
    // FPGA to CPU signals:
    .user_r_mem_32_rden(user_r_mem_32_rden),
    .user_r_mem_32_empty(user_r_mem_32_empty),
    .user_r_mem_32_data(user_r_mem_32_data),
    .user_r_mem_32_eof(user_r_mem_32_eof),
    .user_r_mem_32_open(user_r_mem_32_open),

    // CPU to FPGA signals:
    .user_w_mem_32_wren(user_w_mem_32_wren),
    .user_w_mem_32_full(user_w_mem_32_full),
    .user_w_mem_32_data(user_w_mem_32_data),
    .user_w_mem_32_open(user_w_mem_32_open),

    // Address signals:
    .user_mem_32_addr(user_mem_32_addr),
    .user_mem_32_addr_update(user_mem_32_addr_update),

    // Ports related to /dev/xillybus_read_32
    // FPGA to CPU signals:
    .user_r_read_32_rden(user_r_read_32_rden),
    .user_r_read_32_empty(user_r_read_32_empty),
    .user_r_read_32_data(user_r_read_32_data),
    .user_r_read_32_eof(user_r_read_32_eof),
    .user_r_read_32_open(user_r_read_32_open),

    // Ports related to /dev/xillybus_read_32_2
    // FPGA to CPU signals:
    .user_r_read_32_2_rden(user_r_read_32_2_rden),
    .user_r_read_32_2_empty(user_r_read_32_2_empty),
    .user_r_read_32_2_data(user_r_read_32_2_data),
    .user_r_read_32_2_eof(user_r_read_32_2_eof),
    .user_r_read_32_2_open(user_r_read_32_2_open),

    // Ports related to /dev/xillybus_read_8
    // FPGA to CPU signals:
    .user_r_read_8_rden(user_r_read_8_rden),
    .user_r_read_8_empty(user_r_read_8_empty),
    .user_r_read_8_data(user_r_read_8_data),
    .user_r_read_8_eof(user_r_read_8_eof),
    .user_r_read_8_open(user_r_read_8_open),

    // Ports related to /dev/xillybus_write_8
    // CPU to FPGA signals:
    .user_w_write_8_wren(user_w_write_8_wren),
    .user_w_write_8_full(user_w_write_8_full),
    .user_w_write_8_data(user_w_write_8_data),
    .user_w_write_8_open(user_w_write_8_open),

    // Ports related to /dev/xillybus_write_32
    // CPU to FPGA signals:
    .user_w_write_32_wren(user_w_write_32_wren),
    .user_w_write_32_full(user_w_write_32_full),
    .user_w_write_32_data(user_w_write_32_data),
    .user_w_write_32_open(user_w_write_32_open),

    // Ports related to /dev/xillybus_write_32_2
    // CPU to FPGA signals:
    .user_w_write_32_2_wren(user_w_write_32_2_wren),
    .user_w_write_32_2_full(user_w_write_32_2_full),
    .user_w_write_32_2_data(user_w_write_32_2_data),
    .user_w_write_32_2_open(user_w_write_32_2_open),

//    // Ports related to /dev/xillybus_audio
//    // FPGA to CPU signals:
//    .user_r_audio_rden(user_r_audio_rden),
//    .user_r_audio_empty(user_r_audio_empty),
//    .user_r_audio_data(user_r_audio_data),
//    .user_r_audio_eof(user_r_audio_eof),
//    .user_r_audio_open(user_r_audio_open),
//
//    // CPU to FPGA signals:
//    .user_w_audio_wren(user_w_audio_wren),
//    .user_w_audio_full(user_w_audio_full),
//    .user_w_audio_data(user_w_audio_data),
//    .user_w_audio_open(user_w_audio_open),
//
    // Ports related to /dev/xillybus_smb
    // FPGA to CPU signals:
    .user_r_smb_rden(user_r_smb_rden),
    .user_r_smb_empty(user_r_smb_empty),
    .user_r_smb_data(user_r_smb_data),
    .user_r_smb_eof(user_r_smb_eof),
    .user_r_smb_open(user_r_smb_open),

    // CPU to FPGA signals:
    .user_w_smb_wren(user_w_smb_wren),
    .user_w_smb_full(user_w_smb_full),
    .user_w_smb_data(user_w_smb_data),
    .user_w_smb_open(user_w_smb_open),

    // Ports related to Xillybus Lite
    .user_clk(user_clk),
    .user_wren(user_wren),
    .user_rden(user_rden),
    .user_wstrb(user_wstrb),
    .user_addr(user_addr),
    .user_rd_data(user_rd_data),
    .user_wr_data(user_wr_data),
    .user_irq(user_irq),

    // General signals
    .clk_100(clk_100),
    .otg_oc(otg_oc),
    .PS_GPIO(PS_GPIO),
    .GPIO_LED(GPIO_LED),
    .bus_clk(bus_clk),
    .quiesce(quiesce),

    .PS_CLK(PS_CLK),
    .PS_PORB(PS_PORB),
    .PS_SRSTB(PS_SRSTB),
    .DDR_Addr(DDR_Addr),
    .DDR_BankAddr(DDR_BankAddr),
    .DDR_CAS_n(DDR_CAS_n),
    .DDR_CKE(DDR_CKE),
    .DDR_CS_n(DDR_CS_n),
    .DDR_Clk(DDR_Clk),
    .DDR_Clk_n(DDR_Clk_n),
    .DDR_DM(DDR_DM),
    .DDR_DQ(DDR_DQ),
    .DDR_DQS(DDR_DQS),
    .DDR_DQS_n(DDR_DQS_n),
    .DDR_DRSTB(DDR_DRSTB),
    .DDR_ODT(DDR_ODT),
    .DDR_RAS_n(DDR_RAS_n),
    .DDR_VRN(DDR_VRN),
    .DDR_VRP(DDR_VRP),
    .MIO(MIO),
    .DDR_WEB(DDR_WEB),

    // VGA port related output
    .vga4_blue(vga4_blue),
    .vga4_green(vga4_green),
    .vga4_red(vga4_red),
    .vga_hsync(vga_hsync),
    .vga_vsync(vga_vsync)
  );

  //////////////////////////////////////////////////////
  ////    XILLYBUS LEGACY: LOGIC AND SUBMODULES     ////
  //////////////////////////////////////////////////////
  // Example Logic from Xillybus
  assign      user_irq = 0; // No interrupts for now

  always @(posedge user_clk)
  begin
	   if (user_wstrb[0])
	     litearray0[user_addr[6:2]] <= user_wr_data[7:0];

	   if (user_wstrb[1])
	     litearray1[user_addr[6:2]] <= user_wr_data[15:8];

	   if (user_wstrb[2])
	    litearray2[user_addr[6:2]] <= user_wr_data[23:16];

	   if (user_wstrb[3])
	    litearray3[user_addr[6:2]] <= user_wr_data[31:24];

	   if (user_rden)
	    user_rd_data <= {  litearray3[user_addr[6:2]],
			                   litearray2[user_addr[6:2]],
			                   litearray1[user_addr[6:2]],
			                   litearray0[user_addr[6:2]] };
  end

  i2s_audio audio
   (
    .bus_clk(bus_clk),
    .clk_100(clk_100),
    .quiesce(quiesce),

    .audio_mclk(audio_mclk),
    .audio_dac(audio_dac),
    .audio_adc(audio_adc),
    .audio_bclk(audio_bclk),
    .audio_lrclk(audio_lrclk),

    .user_r_audio_rden(user_r_audio_rden),
    .user_r_audio_empty(user_r_audio_empty),
    .user_r_audio_data(user_r_audio_data),
    .user_r_audio_eof(user_r_audio_eof),
    .user_r_audio_open(user_r_audio_open),

    .user_w_audio_wren(user_w_audio_wren),
    .user_w_audio_full(user_w_audio_full),
    .user_w_audio_data(user_w_audio_data),
    .user_w_audio_open(user_w_audio_open)
  );

  smbus smbus
  (
    .bus_clk(bus_clk),
    .quiesce(quiesce),

    .smb_sclk(smb_sclk),
    .smb_sdata(smb_sdata),
    .smbus_addr(smbus_addr),

    .user_r_smb_rden(user_r_smb_rden),
    .user_r_smb_empty(user_r_smb_empty),
    .user_r_smb_data(user_r_smb_data),
    .user_r_smb_eof(user_r_smb_eof),
    .user_r_smb_open(user_r_smb_open),

    .user_w_smb_wren(user_w_smb_wren),
    .user_w_smb_full(user_w_smb_full),
    .user_w_smb_data(user_w_smb_data),
    .user_w_smb_open(user_w_smb_open)
  );

  //////////////////////////////////////////////////////////////
  //////////////////////////////////////////////////////////////
  ////       Separator of Xillybus IP and MICAS codes       ////
  //////////////////////////////////////////////////////////////
  //////////////////////////////////////////////////////////////

  wire clk_chip;
  wire clk_perip;
  wire rst_chip;
  reg[2:0] rst_chip_pipe;

  ///////////////////////////////
  ////    CLOCKS + RESET     ////
  ///////////////////////////////
  // CLOCK WIZARDS
  //  Generate extra clocks using clock_wizard to relax timing issues
  //  clk_chip: kept for chip
  //  clk_perip： kept for periphery (DAC, etc.)

  clk_wiz_0 clk_gen_chip
  (
    .clk_20(clk_chip),
    .clk_in1(clk_100)
  );

  clk_wiz_1 clk_gen_perip
  (
    .clk_out(clk_perip),
    .clk_in1(clk_100)
  );

  // RESET GENERATION
  //  generate 3-stage synced reset signal when FIFOs are opened

  always @(posedge clk_chip) begin
    rst_chip_pipe <= {rst_chip_pipe[1:0],(!user_w_write_32_open && !user_r_read_32_open)};
  end
  assign rst_chip = rst_chip_pipe[2];

  wire rst_perip;
  reg[2:0] rst_perip_pipe;
  always @(posedge clk_perip) begin
    rst_perip_pipe <= {rst_perip_pipe[1:0],(!user_w_write_32_2_open && !user_r_read_32_2_open)};
  end
  assign rst_perip = rst_perip_pipe[2];

  ///////////////////////////////////////
  ////    XILLINUX <-> FPGA FIFOs    ////
  ///////////////////////////////////////
  // Two bi-directional 32-bit FIFOs between PS (ARM-core) and PL (FPGA-fabric)

  // 32-BIT CHIP-CONTROLLER FIFOS
  //  signal naming: FIFO signals from/to chip_controller are "fifo_chip_XXX"

  //  1. WRITE FIFO
  wire fifo_chip_rd_en;
  wire fifo_chip_empty;
  wire [31:0] fifo_chip_dout;

  fifo_dualport_32x512 fifo_chip_xillinux_to_fpga (
   .rst       (rst_chip),                            // input wire rst
   .wr_clk    (bus_clk),                              // input wire wr_clk
   .rd_clk    (clk_chip),                            // input wire rd_clk
   .din       (user_w_write_32_data),                 // input wire [31 : 0] din
   .wr_en     (user_w_write_32_wren),                 // input wire wr_en
   .rd_en     (fifo_chip_rd_en),                      // input wire rd_en
   .dout      (fifo_chip_dout),                       // output wire [31 : 0] dout
   .full      (user_w_write_32_full),                 // output wire full
   .empty     (fifo_chip_empty)                       // output wire empty
  );

  //  2. READ FIFO
  wire fifo_chip_wr_en;
  wire fifo_chip_full;
  (* mark_debug = "true" *) wire [31:0] fifo_chip_din;

  fifo_dualport_32x512 fifo_chip_fpga_to_xillinux (
    .rst      (rst_chip),                            // input wire rst
    .wr_clk   (clk_chip),                            // input wire wr_clk
    .rd_clk   (bus_clk),                              // input wire rd_clk
    .din      (fifo_chip_din),                        // input wire [31 : 0] din
    .wr_en    (fifo_chip_wr_en),                      // input wire wr_en
    .rd_en    (user_r_read_32_rden),                  // input wire rd_en
    .dout     (user_r_read_32_data),                  // output wire [31 : 0] dout
    .full     (fifo_chip_full),                       // output wire full
    .empty    (user_r_read_32_empty)                  // output wire empty
  );

  assign  user_r_read_32_eof = 0;

  // 32-BIT PERIPHERY-CONTROLLER FIFOS
  //  signal naming: FIFO signals from/to perip_controller are "fifo_perip_XXX"

  //  1. WRITE FIFO
  wire fifo_perip_rd_en;
  wire fifo_perip_empty;
  wire [31:0] fifo_perip_dout;

  fifo_dualport_32x512 fifo_perip_xillinux_to_fpga (
    .rst      (rst_perip),                            // input wire rst
    .wr_clk   (bus_clk),                              // input wire wr_clk
    .rd_clk   (clk_perip),                              // input wire rd_clk
    .din      (user_w_write_32_2_data),               // input wire [7 : 0] din
    .wr_en    (user_w_write_32_2_wren),               // input wire wr_en
    .rd_en    (fifo_perip_rd_en),                     // input wire rd_en
    .dout     (fifo_perip_dout),                      // output wire [7 : 0] dout
    .full     (user_w_write_32_2_full),               // output wire full
    .empty    (fifo_perip_empty)                      // output wire empty
  );

  //  1. READ FIFO
  wire fifo_perip_wr_en;
  wire fifo_perip_full;
  (* mark_debug = "true" *) wire [31:0] fifo_perip_din;

  fifo_dualport_32x512 fifo_perip_fpga_to_xillinux (
    .rst      (rst_perip),                            // input wire rst
    .wr_clk   (clk_perip),                              // input wire wr_clk
    .rd_clk   (bus_clk),                              // input wire rd_clk
    .din      (fifo_perip_din),                       // input wire [7 : 0] din
    .wr_en    (fifo_perip_wr_en),                     // input wire wr_en
    .rd_en    (user_r_read_32_2_rden),                // input wire rd_en
    .dout     (user_r_read_32_2_data),                // output wire [7 : 0] dout
    .full     (fifo_perip_full),                      // output wire full
    .empty    (user_r_read_32_2_empty)                // output wire empty
  );

  assign  user_r_read_32_2_eof = 0;

  // 8-BIT FIFO
  //  can be used for uart
  //  for now: loopback

  (* mark_debug = "true" *) wire [7:0] rx_data;
  (* mark_debug = "true" *) wire rx_valid;

  fifo_dualport_8x2048 fifo_8_fpga_to_xillinux (
    .rst(!user_w_write_8_open && !user_r_read_8_open),        // input wire rst
    .wr_clk(bus_clk),  // input wire wr_clk
    .rd_clk(bus_clk),  // input wire rd_clk
    .din(user_w_write_8_data),        // input wire [7 : 0] din
    .wr_en(user_w_write_8_wren),    // input wire wr_en
    .rd_en(user_r_read_8_rden),    // input wire rd_en
    .dout(user_r_read_8_data),      // output wire [7 : 0] dout
    .full(user_w_write_8_full),      // output wire full
    .empty(user_r_read_8_empty)    // output wire empty
  );

  assign  user_r_read_8_eof = 0;
 

  /////////////////////////////////////////////////
  ////    CHIP and PERIP CONTROLLER MODULES    ////
  /////////////////////////////////////////////////
  // Actual controller module instantiation

  // TODO <Jiacong Sun>: chip_controller probably not be useful for lagd
  // afe_arstn_i is driven by chip_controller but is not brought to a top-level
  // port in this build; declare it as an internal wire to avoid a synthesis error.
  wire afe_arstn_i;

  chip_controller chip_controller_inst(
    .clk(clk_chip),
    .rst(rst_chip),
    .fifo_chip_rd_en  (fifo_chip_rd_en),
    .fifo_chip_wr_en  (fifo_chip_wr_en),
    .fifo_chip_din    (fifo_chip_din),
    .fifo_chip_dout   (fifo_chip_dout),
    .fifo_chip_full   (fifo_chip_full),
    .fifo_chip_empty  (fifo_chip_empty),
    .afe_arstn_i      (afe_arstn_i)
  );

  // user_led is muxed: SPI busy first, then BIST (overrides latent PASS/FAIL),
  // then latent image PASS/FAIL, else perip_controller.
  wire [3:0] perip_led_out;

  perip_controller perip_controller_inst (
    .clk_20             ( clk_perip     ),
    .rst                ( rst_perip   ),

    .fifo_perip_rd_en   ( fifo_perip_rd_en  ),
    .fifo_perip_empty   ( fifo_perip_empty  ),
    .fifo_perip_dout    ( fifo_perip_dout   ),
    .fifo_perip_wr_en   ( fifo_perip_wr_en  ),
    .fifo_perip_full    ( fifo_perip_full   ),
    .fifo_perip_din     ( fifo_perip_din    ),

    .user_led           ( perip_led_out     ),

    .dac1_sclk      (dac1_sclk),
    .dac1_sdin      (dac1_sdin),
    .dac1_sdo       (dac1_sdo),
    .dac1_syncbar   (dac1_syncbar),
    .dac2_sclk      (dac2_sclk),
    .dac2_sdin      (dac2_sdin),
    .dac2_sdo       (dac2_sdo),
    .dac2_syncbar   (dac2_syncbar),

    .adc1_sclk      (adc1_sclk),
    .adc1_sdin      (adc1_sdin),
    .adc1_sdo       (adc1_sdo),
    .adc1_csbar     (adc1_csbar),
    .adc1_convstbar (adc1_convstbar),
    .adc1_status    (adc1_status),
    // ADC2 dropped — outputs left unconnected, inputs tied low.
    .adc2_sdin      (),
    .adc2_sdo       (1'b0),
    .adc2_csbar     (),
    .adc2_convstbar (),
    .adc2_status    (1'b0),
    .adc3_sdin      (adc3_sdin),
    .adc3_sdo       (adc3_sdo),
    .adc3_csbar     (adc3_csbar),
    .adc3_convstbar (adc3_convstbar),
    .adc3_status    (adc3_status)
  );

  // TODO: below is written by Robin Geens. To be adapted
  ////////////////////////////////////////////////////////////////////////
  ////    CHIP SPI MASTER – freq_sel_controller + spi_image_tester    ////
  ////////////////////////////////////////////////////////////////////////
  //
  // Shared board connections (all read from PS_GPIO without conflict):
  //   SW0-SW5  = PS_GPIO[11:16]  →  6-bit freq value for freq_sel_controller
  //   BTNL     = PS_GPIO[19]     →  trigger freq_sel transaction
  //   BTNR     = PS_GPIO[20]     →  trigger image program write
  //   BTNU     = PS_GPIO[21]     →  trigger image program verify
  //
  // Shared SPI pins (Pmod JA, LVCMOS33):
  //   chip_sck  JA1  → chip spis_sck_i
  //   chip_csb  JA2  → chip spis_csb_i
  //   chip_sd[0] JA3  → chip spis_sd_i[0]  (MOSI / Quad bit 0)
  //   chip_sd[1] JA4  → chip spis_sd_o[1]  (MISO / Quad bit 1, bidirectional)
  //   chip_sd[2] JA7  → chip spis_sd_i/o[2]
  //   chip_sd[3] JA8  → chip spis_sd_i/o[3]
  //
  // Arbitration: spi_image_tester takes priority (img_busy=1 overrides freq_sel).
  //
  // SPI status LED vector `{fail,pass,img_busy,freq_busy}` when any controller
  // is busy OR when PASS/FAIL is latched after verify (cleared by BTNR write).
  // Between transactions, SW7=BIST steals the LEDs ahead of latent PASS/FAIL.
  // Bits when status is displayed:
  //   [0] = freq_sel busy
  //   [1] = image test busy
  //   [2] = image test PASS (last verify ok; Cleared when BTNR write starts)
  //   [3] = image test FAIL (last verify mismatch; Cleared when BTNR write starts)

  // Power-on reset: 4 cycles high on startup, then permanently 0.
  reg [3:0] por_shreg = 4'hF;
  always @(posedge clk_100) por_shreg <= {por_shreg[2:0], 1'b0};
  wire rst_freq = por_shreg[3];

  // Read board inputs from PS_GPIO.
  wire [5:0] sw_freq    = PS_GPIO[16:11];  // SW5..SW0
  wire       btn_freq   = PS_GPIO[19];     // BTNL → freq_sel trigger
  wire       btn_img_w  = PS_GPIO[20];     // BTNR → image program write trigger
  wire       btn_img_v  = PS_GPIO[21];     // BTNU → image program verify trigger

  // ---- freq_sel_controller wires ----
  wire freq_sck, freq_csb, freq_mosi, freq_busy;

  freq_sel_controller freq_sel_ctrl (
    .clk      (clk_100),
    .rst      (rst_freq),
    .sw       (sw_freq),
    .btn      (btn_freq),
    .spi_sck  (freq_sck),
    .spi_csb  (freq_csb),
    .spi_mosi (freq_mosi),
    .busy     (freq_busy)
  );

  // ---- spi_image_tester wires ----
  wire        img_sck, img_csb, img_sd_oe, img_busy, img_pass, img_fail;
  wire [3:0]  img_sd_out;
  (* mark_debug = "true" *) wire [3:0]  chip_sd_in;   // data sensed from the chip (IOBUF O outputs)

  spi_image_tester img_tester (
    .clk         (clk_100),
    .rst         (rst_freq),
    .btn_write   (btn_img_w),
    .btn_verify  (btn_img_v),
    .spi_sck     (img_sck),
    .spi_csb     (img_csb),
    .sd_out      (img_sd_out),
    .sd_oe       (img_sd_oe),
    .sd_in       (chip_sd_in),
    .busy        (img_busy),
    .pass        (img_pass),
    .fail        (img_fail)
  );

  // ---- SPI output mux (image_tester takes priority) ----
  wire spi_img_sel = img_busy;

  assign chip_sck = spi_img_sel ? img_sck  : freq_sck;
  assign chip_csb = spi_img_sel ? img_csb  : freq_csb;

  // SD bus mux: image_tester uses all 4 bits; freq_sel drives only SD[0]
  (* mark_debug = "true" *) wire [3:0] chip_sd_out = spi_img_sel ? img_sd_out : {3'b000, freq_mosi};
  // Output enable: FPGA drives during write phases; chip drives during read data
  wire       chip_sd_oe  = spi_img_sel ? img_sd_oe  : freq_busy;
  wire       chip_sd_t   = ~chip_sd_oe;  // IOBUF T: 1 = tristate (input)

  // ---- Bidirectional IOBUF for Quad-SPI data lines ----
  genvar gi;
  generate
    for (gi = 0; gi < 4; gi = gi + 1) begin : gen_chip_iobuf
      IOBUF iobuf_chip_sd (
        .IO (chip_sd[gi]),
        .I  (chip_sd_out[gi]),
        .O  (chip_sd_in[gi]),
        .T  (chip_sd_t)
      );
    end
  endgenerate

  // ---- LED status mux ----
  //
  // BIST mode (SW7 = PS_GPIO[18] = 1): mirrors SW3..SW0 whenever neither SPI
  // controller is busy. That overrides latent image PASS/FAIL on the LEDs; the
  // latched `img_pass` / `img_fail` registers themselves are unaffected.
  //
  // When SW7 = 0: perip_controller except during SPI-busy or latent PASS/FAIL.

  wire [3:0] bist_sw = sw_freq[3:0];  // SW3..SW0 – same switches as freq_sel lower nibble
  wire       bist_en = PS_GPIO[18];   // SW7 – BIST mode select

  wire       spi_busy            = freq_busy | img_busy;
  wire       img_led_status_live = img_pass | img_fail;
  wire [3:0] spi_led_vec         = {img_fail, img_pass, img_busy, freq_busy};
  assign user_led = spi_busy ? spi_led_vec
                  : bist_en  ? bist_sw
                  : img_led_status_live ? spi_led_vec
                  :                       perip_led_out;

endmodule

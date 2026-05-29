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
//   v1.1, 17-12-2021  Add 2x RW FIFO streams from corebundle/template.v (see xillinux_template/corebundle/readme.md)


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

  ///////////////////////////////////////////////////////////
  // Project specific IO pins
  ///////////////////////////////////////////////////////////
  output clk_chip_ctrl_o,
  output clk_perip_ctrl_o,
  output [3:0] user_led,      // connect to LD[7..4]
  // Chip Quad-SPI
  (* mark_debug = "true" *) output chip_sck_o,
  (* mark_debug = "true" *) output chip_csb_o,
  (* mark_debug = "true" *) inout  [3:0] chip_sd_io,   // Quad-SPI bidirectional data
  (* mark_debug = "true" *) output clk_chip_o,
  (* mark_debug = "true" *) output chip_arst_no, // active low reset to chip
  // DAC SPI
  (* mark_debug = "true" *) output dac_sclk_o,
  (* mark_debug = "true" *) output dac_csb_o,
  (* mark_debug = "true" *) output dac_sdin_o,
  (* mark_debug = "true" *) output dac_shdn_o,
  (* mark_debug = "true" *) output dac_rstn_o
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
    .user_r_mem_32_rden      (user_r_mem_32_rden     ),
    .user_r_mem_32_empty     (user_r_mem_32_empty    ),
    .user_r_mem_32_data      (user_r_mem_32_data     ),
    .user_r_mem_32_eof       (user_r_mem_32_eof      ),
    .user_r_mem_32_open      (user_r_mem_32_open     ),

    // CPU to FPGA signals:
    .user_w_mem_32_wren      (user_w_mem_32_wren     ),
    .user_w_mem_32_full      (user_w_mem_32_full     ),
    .user_w_mem_32_data      (user_w_mem_32_data     ),
    .user_w_mem_32_open      (user_w_mem_32_open     ),

    // Address signals:
    .user_mem_32_addr        (user_mem_32_addr       ),
    .user_mem_32_addr_update (user_mem_32_addr_update),

    // Ports related to /dev/xillybus_read_32
    // FPGA to CPU signals:
    .user_r_read_32_rden     (user_r_read_32_rden    ),
    .user_r_read_32_empty    (user_r_read_32_empty   ),
    .user_r_read_32_data     (user_r_read_32_data    ),
    .user_r_read_32_eof      (user_r_read_32_eof     ),
    .user_r_read_32_open     (user_r_read_32_open    ),

    // Ports related to /dev/xillybus_read_32_2
    // FPGA to CPU signals:
    .user_r_read_32_2_rden   (user_r_read_32_2_rden  ),
    .user_r_read_32_2_empty  (user_r_read_32_2_empty ),
    .user_r_read_32_2_data   (user_r_read_32_2_data  ),
    .user_r_read_32_2_eof    (user_r_read_32_2_eof   ),
    .user_r_read_32_2_open   (user_r_read_32_2_open  ),

    // Ports related to /dev/xillybus_read_8
    // FPGA to CPU signals:
    .user_r_read_8_rden      (user_r_read_8_rden     ),
    .user_r_read_8_empty     (user_r_read_8_empty    ),
    .user_r_read_8_data      (user_r_read_8_data     ),
    .user_r_read_8_eof       (user_r_read_8_eof      ),
    .user_r_read_8_open      (user_r_read_8_open     ),

    // Ports related to /dev/xillybus_write_8
    // CPU to FPGA signals:
    .user_w_write_8_wren     (user_w_write_8_wren    ),
    .user_w_write_8_full     (user_w_write_8_full    ),
    .user_w_write_8_data     (user_w_write_8_data    ),
    .user_w_write_8_open     (user_w_write_8_open    ),

    // Ports related to /dev/xillybus_write_32
    // CPU to FPGA signals:
    .user_w_write_32_wren    (user_w_write_32_wren   ),
    .user_w_write_32_full    (user_w_write_32_full   ),
    .user_w_write_32_data    (user_w_write_32_data   ),
    .user_w_write_32_open    (user_w_write_32_open   ),

    // Ports related to /dev/xillybus_write_32_2
    // CPU to FPGA signals:
    .user_w_write_32_2_wren  (user_w_write_32_2_wren ),
    .user_w_write_32_2_full  (user_w_write_32_2_full ),
    .user_w_write_32_2_data  (user_w_write_32_2_data ),
    .user_w_write_32_2_open  (user_w_write_32_2_open ),

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
    .user_r_smb_rden         (user_r_smb_rden        ),
    .user_r_smb_empty        (user_r_smb_empty       ),
    .user_r_smb_data         (user_r_smb_data        ),
    .user_r_smb_eof          (user_r_smb_eof         ),
    .user_r_smb_open         (user_r_smb_open        ),
  
    // CPU to FPGA signals:
    .user_w_smb_wren         (user_w_smb_wren        ),
    .user_w_smb_full         (user_w_smb_full        ),
    .user_w_smb_data         (user_w_smb_data        ),
    .user_w_smb_open         (user_w_smb_open        ),

    // Ports related to Xillybus Lite
    .user_clk                (user_clk               ),
    .user_wren               (user_wren              ),
    .user_rden               (user_rden              ),
    .user_wstrb              (user_wstrb             ),
    .user_addr               (user_addr              ),
    .user_rd_data            (user_rd_data           ),
    .user_wr_data            (user_wr_data           ),
    .user_irq                (user_irq               ),

    // General signals
    .clk_100                 (clk_100                ),
    .otg_oc                  (otg_oc                 ),
    .PS_GPIO                 (PS_GPIO                ),
    .GPIO_LED                (GPIO_LED               ),
    .bus_clk                 (bus_clk                ),
    .quiesce                 (quiesce                ),

    .PS_CLK                  (PS_CLK                 ),
    .PS_PORB                 (PS_PORB                ),
    .PS_SRSTB                (PS_SRSTB               ),
    .DDR_Addr                (DDR_Addr               ),
    .DDR_BankAddr            (DDR_BankAddr           ),
    .DDR_CAS_n               (DDR_CAS_n              ),
    .DDR_CKE                 (DDR_CKE                ),
    .DDR_CS_n                (DDR_CS_n               ),
    .DDR_Clk                 (DDR_Clk                ),
    .DDR_Clk_n               (DDR_Clk_n              ),
    .DDR_DM                  (DDR_DM                 ),
    .DDR_DQ                  (DDR_DQ                 ),
    .DDR_DQS                 (DDR_DQS                ),
    .DDR_DQS_n               (DDR_DQS_n              ),
    .DDR_DRSTB               (DDR_DRSTB              ),
    .DDR_ODT                 (DDR_ODT                ),
    .DDR_RAS_n               (DDR_RAS_n              ),
    .DDR_VRN                 (DDR_VRN                ),
    .DDR_VRP                 (DDR_VRP                ),
    .MIO                     (MIO                    ),
    .DDR_WEB                 (DDR_WEB                ),

    // VGA port related output
    .vga4_blue               (vga4_blue              ),
    .vga4_green              (vga4_green             ),
    .vga4_red                (vga4_red               ),
    .vga_hsync               (vga_hsync              ),
    .vga_vsync               (vga_vsync              )
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
    .bus_clk            (bus_clk           ),
    .clk_100            (clk_100           ),
    .quiesce            (quiesce           ),

    .audio_mclk         (audio_mclk        ),
    .audio_dac          (audio_dac         ),
    .audio_adc          (audio_adc         ),
    .audio_bclk         (audio_bclk        ),
    .audio_lrclk        (audio_lrclk       ),

    .user_r_audio_rden  (user_r_audio_rden ),
    .user_r_audio_empty (user_r_audio_empty),
    .user_r_audio_data  (user_r_audio_data ),
    .user_r_audio_eof   (user_r_audio_eof  ),
    .user_r_audio_open  (user_r_audio_open ),

    .user_w_audio_wren  (user_w_audio_wren ),
    .user_w_audio_full  (user_w_audio_full ),
    .user_w_audio_data  (user_w_audio_data ),
    .user_w_audio_open  (user_w_audio_open )
  );

  smbus smbus
  (
    .bus_clk          (bus_clk         ),
    .quiesce          (quiesce         ),

    .smb_sclk         (smb_sclk        ),
    .smb_sdata        (smb_sdata       ),
    .smbus_addr       (smbus_addr      ),

    .user_r_smb_rden  (user_r_smb_rden ),
    .user_r_smb_empty (user_r_smb_empty),
    .user_r_smb_data  (user_r_smb_data ),
    .user_r_smb_eof   (user_r_smb_eof  ),
    .user_r_smb_open  (user_r_smb_open ),

    .user_w_smb_wren  (user_w_smb_wren ),
    .user_w_smb_full  (user_w_smb_full ),
    .user_w_smb_data  (user_w_smb_data ),
    .user_w_smb_open  (user_w_smb_open )
  );

  //////////////////////////////////////////////////////////////
  //////////////////////////////////////////////////////////////
  ////       Separator of Xillybus IP and Project codes     ////
  //////////////////////////////////////////////////////////////
  //////////////////////////////////////////////////////////////

  wire clk_chip_ctrl;
  wire clk_perip_ctrl;
  wire rst_chip_ctrl; // active high
  wire rst_perip_ctrl; // active high
  reg[2:0] rst_chip_ctrl_pipe;
  reg[2:0] rst_perip_ctrl_pipe;
  wire [3:0] chip_sdi;
  wire [3:0] chip_sdo;
  wire [3:0] chip_sd_oe;

  ///////////////////////////////
  ////    CLOCKS + RESET     ////
  ///////////////////////////////

  assign clk_chip_ctrl_o = clk_chip_ctrl;
  assign clk_perip_ctrl_o = clk_perip_ctrl;

  // CLOCK WIZARDS
  //  Generate extra clocks using clock_wizard to relax timing issues
  //  clk_chip_ctrl: kept for chip controller
  //  clk_perip_ctrl： kept for peripheral controller (DAC, etc.)
  assign clk_chip_ctrl = clk_100; // use bus clock directly
  assign clk_perip_ctrl = clk_100; // use bus clock directly

  genvar chip_sd_idx;
  generate
    for (chip_sd_idx = 0; chip_sd_idx < 4; chip_sd_idx = chip_sd_idx + 1) begin : gen_chip_sd_iobuf
      IOBUF chip_sd_iobuf (
        .I (chip_sdo[chip_sd_idx]),
        .O (chip_sdi[chip_sd_idx]),
        .T (~chip_sd_oe[chip_sd_idx]),
        .IO(chip_sd_io[chip_sd_idx])
      );
    end
  endgenerate

  // clk_wiz_0 clk_gen_chip
  // (
  //   .clk_20  (clk_chip_ctrl ),
  //   .clk_in1 (clk_100       )
  // );

  // clk_wiz_1 clk_gen_perip
  // (
  //   .clk_out (clk_perip_ctrl),
  //   .clk_in1 (clk_100       )
  // );

  // RESET GENERATION
  //  generate 3-stage synced reset signal when FIFOs are opened
  always @(posedge clk_chip_ctrl) begin
    rst_chip_ctrl_pipe <= {rst_chip_ctrl_pipe[1:0],(!user_w_write_32_open && !user_r_read_32_open)};
  end
  assign rst_chip_ctrl = rst_chip_ctrl_pipe[2];

  always @(posedge clk_perip_ctrl) begin
    rst_perip_ctrl_pipe <= {rst_perip_ctrl_pipe[1:0],(!user_w_write_32_2_open && !user_r_read_32_2_open)};
  end
  assign rst_perip_ctrl = rst_perip_ctrl_pipe[2];

  ///////////////////////////////////////
  ////    XILLINUX <-> FPGA FIFOs    ////
  ///////////////////////////////////////
  // Two bi-directional 32-bit FIFOs between PS (ARM-core) and PL (FPGA-fabric)

  // 32-BIT CHIP-CONTROLLER FIFOS
  //  signal naming: FIFO signals from/to chip_controller are "fifo_chip_XXX"

  // WRITE FIFO
  wire fifo_chip_rd_en;
  wire fifo_chip_empty;
  wire [31:0] fifo_chip_dout;

  fifo_dualport_32x512 fifo_chip_xillinux_to_fpga (
   .rst           (rst_chip_ctrl       ), // input wire rst
   .wr_clk        (bus_clk             ), // input wire wr_clk
   .rd_clk        (clk_chip_ctrl       ), // input wire rd_clk
   .din           (user_w_write_32_data), // input wire [31 : 0] din
   .wr_en         (user_w_write_32_wren), // input wire wr_en
   .rd_en         (fifo_chip_rd_en     ), // input wire rd_en
   .dout          (fifo_chip_dout      ), // output wire [31 : 0] dout
   .full          (user_w_write_32_full), // output wire full
   .empty         (fifo_chip_empty     )  // output wire empty
  );

  // READ FIFO
  wire fifo_chip_wr_en;
  wire fifo_chip_full;
  (* mark_debug = "true" *) wire [31:0] fifo_chip_din;

  fifo_dualport_32x512 fifo_chip_fpga_to_xillinux (
    .rst           (rst_chip_ctrl       ), // input wire rst
    .wr_clk        (clk_chip_ctrl       ), // input wire wr_clk
    .rd_clk        (bus_clk             ), // input wire rd_clk
    .din           (fifo_chip_din       ), // input wire [31 : 0] din
    .wr_en         (fifo_chip_wr_en     ), // input wire wr_en
    .rd_en         (user_r_read_32_rden ), // input wire rd_en
    .dout          (user_r_read_32_data ), // output wire [31 : 0] dout
    .full          (fifo_chip_full      ), // output wire full
    .empty         (user_r_read_32_empty)  // output wire empty
  );

  assign  user_r_read_32_eof = 0;

  // 32-BIT PERIPHERY-CONTROLLER FIFOS
  //  signal naming: FIFO signals from/to perip_controller are "fifo_perip_XXX"

  // WRITE FIFO
  wire fifo_perip_rd_en;
  wire fifo_perip_empty;
  wire [31:0] fifo_perip_dout;

  fifo_dualport_32x512 fifo_perip_xillinux_to_fpga (
    .rst           (rst_perip_ctrl        ), // input wire rst
    .wr_clk        (bus_clk               ), // input wire wr_clk
    .rd_clk        (clk_perip_ctrl        ), // input wire rd_clk
    .din           (user_w_write_32_2_data), // input wire [7 : 0] din
    .wr_en         (user_w_write_32_2_wren), // input wire wr_en
    .rd_en         (fifo_perip_rd_en      ), // input wire rd_en
    .dout          (fifo_perip_dout       ), // output wire [7 : 0] dout
    .full          (user_w_write_32_2_full), // output wire full
    .empty         (fifo_perip_empty      )  // output wire empty
  );

  // READ FIFO
  wire fifo_perip_wr_en;
  wire fifo_perip_full;
  (* mark_debug = "true" *) wire [31:0] fifo_perip_din;

  fifo_dualport_32x512 fifo_perip_fpga_to_xillinux (
    .rst           (rst_perip_ctrl        ), // input wire rst
    .wr_clk        (clk_perip_ctrl        ), // input wire wr_clk
    .rd_clk        (bus_clk               ), // input wire rd_clk
    .din           (fifo_perip_din        ), // input wire [7 : 0] din
    .wr_en         (fifo_perip_wr_en      ), // input wire wr_en
    .rd_en         (user_r_read_32_2_rden ), // input wire rd_en
    .dout          (user_r_read_32_2_data ), // output wire [7 : 0] dout
    .full          (fifo_perip_full       ), // output wire full
    .empty         (user_r_read_32_2_empty)  // output wire empty
  );

  assign  user_r_read_32_2_eof = 0;

  // LED indication of FIFO status
  assign user_led[0] = fifo_chip_empty; // debug: LED on when chip_xillinux_to_fpga FIFO is empty
  assign user_led[1] = user_r_read_32_empty; // debug: LED on when chip_fpga_to_xillinux FIFO is empty
  assign user_led[2] = fifo_perip_empty; // debug: LED on when perip_xillinux_to_fpga FIFO is empty
  assign user_led[3] = user_r_read_32_2_empty; // debug: LED on when perip_fpga_to_xillinux FIFO is empty

  // 8-BIT FIFO
  //  can be used for uart
  //  for now: loopback

  // (* mark_debug = "true" *) wire [7:0] rx_data;
  // (* mark_debug = "true" *) wire rx_valid;

  // fifo_dualport_8x2048 fifo_8_fpga_to_xillinux (
  //   .rst    (!user_w_write_8_open && !user_r_read_8_open), // input wire rst
  //   .wr_clk (bus_clk                                    ), // input wire wr_clk
  //   .rd_clk (bus_clk                                    ), // input wire rd_clk
  //   .din    (user_w_write_8_data                        ), // input wire [7 : 0] din
  //   .wr_en  (user_w_write_8_wren                        ), // input wire wr_en
  //   .rd_en  (user_r_read_8_rden                         ), // input wire rd_en
  //   .dout   (user_r_read_8_data                         ), // output wire [7 : 0] dout
  //   .full   (user_w_write_8_full                        ), // output wire full
  //   .empty  (user_r_read_8_empty                        ) // output wire empty
  // );

  // assign  user_r_read_8_eof = 0;

  /////////////////////////////////////////////////
  ////    CHIP and PERIP CONTROLLER MODULES    ////
  /////////////////////////////////////////////////
  parameter integer CLK_HZ = 100_000_000; // 100 MHz bus clock
  parameter integer SCK_HZ = 25_000_000;  // 25 MHz SPI clock (max supported by DAC is 33 MHz)
  parameter integer CSB_HOLD_CYCLES = 40 / (1000_000_000 / CLK_HZ); // 40 ns hold time for CSB signal (see DAC datasheet) converted to number of bus clock cycles

  // Controller for on-chip Quad-SPI
  chip_controller #(
    .CLK_HZ            (CLK_HZ         ),
    .SCK_HZ            (SCK_HZ         )
  ) chip_controller_inst (
    .clk_i             (clk_chip_ctrl  ),
    .rst_i             (rst_chip_ctrl  ),
    // FIFO interfaces to xillybus
    .fifo_chip_rd_en_o (fifo_chip_rd_en),
    .fifo_chip_wr_en_o (fifo_chip_wr_en),
    .fifo_chip_din_o   (fifo_chip_din  ),
    .fifo_chip_dout_i  (fifo_chip_dout ),
    .fifo_chip_full_i  (fifo_chip_full ),
    .fifo_chip_empty_i (fifo_chip_empty),
    // Quad-SPI interface to chip
    .chip_sck_o        (chip_sck_o     ),
    .chip_csb_o        (chip_csb_o     ),
    .chip_sd_i         (chip_sdi       ),
    .chip_sd_o         (chip_sdo       ),
    .chip_sd_oe_o      (chip_sd_oe     ),
    // control signals to chip
    .clk_chip_o        (clk_chip_o     ),
    .chip_arst_no      (chip_arst_no   )
  );

  // Controller for peripheral DAC (single-port SPI)
  wire perip_dac_shdn;
  wire perip_dac_rstn;

  perip_controller #(
    .CLK_HZ            (CLK_HZ           ),
    .SCK_HZ            (SCK_HZ           ),
    .CSB_HOLD_CYCLES   (CSB_HOLD_CYCLES  )
  ) perip_controller_inst (
    .clk_i             (clk_perip_ctrl   ),
    .rst_i             (rst_perip_ctrl   ),
    .fifo_perip_rd_en_o(fifo_perip_rd_en ),
    .fifo_perip_empty_i(fifo_perip_empty ),
    .fifo_perip_dout_i (fifo_perip_dout  ),
    .fifo_perip_wr_en_o(fifo_perip_wr_en ),
    .fifo_perip_full_i (fifo_perip_full  ),
    .fifo_perip_din_o  (fifo_perip_din   ),
    .dac_clk_o         (dac_sclk_o       ),
    .dac_csb_o         (dac_csb_o        ),
    .dac_sdi_o         (dac_sdin_o       ),
    .dac_shdn_o        (dac_shdn_o       ),
    .dac_rstn_o        (dac_rstn_o       )
  );

endmodule

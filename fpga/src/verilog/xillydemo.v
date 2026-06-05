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
  (* mark_debug = "true" *) output chip_rtc_o,   // ~32.768 kHz real-time-clock reference to chip
  // DAC SPI
  (* mark_debug = "true" *) output dac_sclk_o,
  (* mark_debug = "true" *) output dac_csb_o,
  (* mark_debug = "true" *) output dac_sdin_o,
  (* mark_debug = "true" *) output dac_shdn_o,
  (* mark_debug = "true" *) output dac_rstn_o,
  // Others
  (* mark_debug = "true" *) output [1:0] chip_bootmode_o,
  // PLL serial configuration interface (FPGA <-> Pomelo PLL, see pll_controller.sv)
  (* mark_debug = "true" *) output pll_clk_sel_o,
  (* mark_debug = "true" *) output pll_data_strb_o,
  (* mark_debug = "true" *) output pll_data_o,
  (* mark_debug = "true" *) output pll_cfg_vld_strb_o,
  (* mark_debug = "true" *) input  pll_data_i,       // PLL data_o (shallow-reg MSB) for READBACK
  (* mark_debug = "true" *) input  pll_lock_i,       // PLL lock (1 = locked) for STATUS
  // HV9308 32-channel serial-to-parallel converter (current-mirror bias resistors)
  (* mark_debug = "true" *) output s2p_din_o,
  (* mark_debug = "true" *) output s2p_clk_o,
  (* mark_debug = "true" *) output s2p_le_o,
  (* mark_debug = "true" *) output s2p_oe_o,
  (* mark_debug = "true" *) input  s2p_dout_i        // HV9308 cascade Data Out, for READBACK
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
  wire clk_pll_ctrl;
  wire rst_chip_ctrl; // active high
  wire rst_perip_ctrl; // active high
  wire rst_pll_ctrl; // active high
  reg[2:0] rst_chip_ctrl_pipe;
  reg[2:0] rst_perip_ctrl_pipe;
  reg[2:0] rst_pll_ctrl_pipe;
  wire [3:0] chip_sdi;
  wire [3:0] chip_sdo;
  wire [3:0] chip_sd_oe;

  // LED activity/status signals (see user_led assignment near the FIFOs below)
  wire chip_clk_en;        // chip clock enabled (from chip_controller)
  wire chip_write_pulse;   // 1-cycle pulse when a chip write starts
  wire perip_write_pulse;  // 1-cycle pulse when a perip (DAC) write is issued
  wire chip_write_led;     // chip_write_pulse stretched to ~1 s
  wire perip_write_led;    // perip_write_pulse stretched to ~1 s
  reg  heartbeat_led;      // ~1 Hz blink from clk_100

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
  assign clk_pll_ctrl = clk_100; // use bus clock directly

  genvar chip_sd_idx;
  generate
    for (chip_sd_idx = 0; chip_sd_idx < 4; chip_sd_idx = chip_sd_idx + 1) begin : gen_chip_sd_iobuf
      IOBUF chip_sd_iobuf (
        .I  (chip_sdo[chip_sd_idx]   ),
        .O  (chip_sdi[chip_sd_idx]   ),
        .T  (~chip_sd_oe[chip_sd_idx]),
        .IO (chip_sd_io[chip_sd_idx] )
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

  always @(posedge clk_pll_ctrl) begin
    rst_pll_ctrl_pipe <= {rst_pll_ctrl_pipe[1:0],(!user_w_write_8_open && !user_r_read_8_open)};
  end
  assign rst_pll_ctrl = rst_pll_ctrl_pipe[2];

  ///////////////////////////////
  ////    RTC CLOCK GEN       ////
  ///////////////////////////////
  // The chip's rtc_i is the Cheshire CLINT real-time-clock reference. The SoC is
  // configured for RtcFreq = 32_768 Hz (see lagd-im/hw/rtl/lagd_pkg.sv), so the
  // mtime counter assumes this exact tick rate. We approximate it by integer-
  // dividing the 100 MHz bus clock. The reference need not be clean or aligned
  // to clk_100 -- the CLINT just counts its edges.
  //   half period = 100e6 / (2 * 32768) = 1525 cycles  -> f = 100e6 / 3050
  //               = 32_787 Hz (~0.06% high), close enough for bring-up.
  localparam integer RTC_HZ          = 32_768;
  localparam integer RTC_HALF_CYCLES = 100_000_000 / (2 * RTC_HZ); // = 1525
  reg [11:0] rtc_div_cnt = 12'd0;
  reg        rtc_clk     = 1'b0;

  always @(posedge clk_100) begin
    if (rtc_div_cnt == RTC_HALF_CYCLES - 1) begin
      rtc_div_cnt <= 12'd0;
      rtc_clk     <= ~rtc_clk;
    end else begin
      rtc_div_cnt <= rtc_div_cnt + 12'd1;
    end
  end

  assign chip_rtc_o = rtc_clk;

  ///////////////////////////////
  ////    HEARTBEAT (LED)    ////
  ///////////////////////////////
  // ~1 Hz blink divided from clk_100, to show at a glance that the bitstream is
  // loaded and the clock is running. Toggle every CLK_HZ/2 cycles.
  localparam integer HEARTBEAT_HALF = 100_000_000 / 2; // = 50e6 -> 1 Hz toggle
  reg [25:0] heartbeat_cnt = 26'd0;

  initial heartbeat_led = 1'b0;
  always @(posedge clk_100) begin
    if (heartbeat_cnt == HEARTBEAT_HALF - 1) begin
      heartbeat_cnt <= 26'd0;
      heartbeat_led <= ~heartbeat_led;
    end else begin
      heartbeat_cnt <= heartbeat_cnt + 26'd1;
    end
  end

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
   .rst    (rst_chip_ctrl       ), // input wire rst
   .wr_clk (bus_clk             ), // input wire wr_clk
   .rd_clk (clk_chip_ctrl       ), // input wire rd_clk
   .din    (user_w_write_32_data), // input wire [31 : 0] din
   .wr_en  (user_w_write_32_wren), // input wire wr_en
   .rd_en  (fifo_chip_rd_en     ), // input wire rd_en
   .dout   (fifo_chip_dout      ), // output wire [31 : 0] dout
   .full   (user_w_write_32_full), // output wire full
   .empty  (fifo_chip_empty     ) // output wire empty
  );

  // READ FIFO
  wire fifo_chip_wr_en;
  wire fifo_chip_full;
  (* mark_debug = "true" *) wire [31:0] fifo_chip_din;

  fifo_dualport_32x512 fifo_chip_fpga_to_xillinux (
    .rst    (rst_chip_ctrl       ), // input wire rst
    .wr_clk (clk_chip_ctrl       ), // input wire wr_clk
    .rd_clk (bus_clk             ), // input wire rd_clk
    .din    (fifo_chip_din       ), // input wire [31 : 0] din
    .wr_en  (fifo_chip_wr_en     ), // input wire wr_en
    .rd_en  (user_r_read_32_rden ), // input wire rd_en
    .dout   (user_r_read_32_data ), // output wire [31 : 0] dout
    .full   (fifo_chip_full      ), // output wire full
    .empty  (user_r_read_32_empty) // output wire empty
  );

  assign  user_r_read_32_eof = 0;

  // 32-BIT PERIPHERY-CONTROLLER FIFOS
  //  signal naming: FIFO signals from/to perip_controller are "fifo_perip_XXX"

  // WRITE FIFO
  wire fifo_perip_rd_en;
  wire fifo_perip_empty;
  wire [31:0] fifo_perip_dout;

  fifo_dualport_32x512 fifo_perip_xillinux_to_fpga (
    .rst    (rst_perip_ctrl        ), // input wire rst
    .wr_clk (bus_clk               ), // input wire wr_clk
    .rd_clk (clk_perip_ctrl        ), // input wire rd_clk
    .din    (user_w_write_32_2_data), // input wire [7 : 0] din
    .wr_en  (user_w_write_32_2_wren), // input wire wr_en
    .rd_en  (fifo_perip_rd_en      ), // input wire rd_en
    .dout   (fifo_perip_dout       ), // output wire [7 : 0] dout
    .full   (user_w_write_32_2_full), // output wire full
    .empty  (fifo_perip_empty      ) // output wire empty
  );

  // READ FIFO
  wire fifo_perip_wr_en;
  wire fifo_perip_full;
  (* mark_debug = "true" *) wire [31:0] fifo_perip_din;

  fifo_dualport_32x512 fifo_perip_fpga_to_xillinux (
    .rst    (rst_perip_ctrl        ), // input wire rst
    .wr_clk (clk_perip_ctrl        ), // input wire wr_clk
    .rd_clk (bus_clk               ), // input wire rd_clk
    .din    (fifo_perip_din        ), // input wire [7 : 0] din
    .wr_en  (fifo_perip_wr_en      ), // input wire wr_en
    .rd_en  (user_r_read_32_2_rden ), // input wire rd_en
    .dout   (user_r_read_32_2_data ), // output wire [7 : 0] dout
    .full   (fifo_perip_full       ), // output wire full
    .empty  (user_r_read_32_2_empty) // output wire empty
  );

  assign  user_r_read_32_2_eof = 0;

  // LED indication (user_led[3:0] = board LD[7:4])
  //   LD4: ~1 Hz heartbeat from clk_100  -> bitstream alive / clock running
  //   LD5: chip clock enabled            -> chip_clk_en
  //   LD6: chip write activity (~1 s)    -> write_mem / verify_write_mem (not read)
  //   LD7: perip write activity (~1 s)   -> DAC write (not writeback/read)
  // The two activity LEDs stretch a single-cycle event to ~1 s so it is visible.
  pulse_stretch #(.STRETCH_CYCLES(100_000_000)) chip_write_blink (
    .clk_i   (clk_chip_ctrl   ),
    .rst_i   (rst_chip_ctrl   ),
    .pulse_i (chip_write_pulse ),
    .level_o (chip_write_led  )
  );

  pulse_stretch #(.STRETCH_CYCLES(100_000_000)) perip_write_blink (
    .clk_i   (clk_perip_ctrl   ),
    .rst_i   (rst_perip_ctrl   ),
    .pulse_i (perip_write_pulse ),
    .level_o (perip_write_led  )
  );

  assign user_led[0] = heartbeat_led;
  assign user_led[1] = chip_clk_en;
  assign user_led[2] = chip_write_led;
  assign user_led[3] = perip_write_led;

  // 8-BIT PLL-CONTROLLER FIFOS
  //  signal naming: FIFO signals from/to pll_controller are "fifo_pll_XXX".
  //  These reuse the Xillybus /dev/xillybus_{write,read}_8 streams to drive the
  //  Pomelo PLL serial configuration interface (see pll_controller.sv).

  // WRITE FIFO (xillinux -> fpga): host pushes byte-framed PLL commands
  wire fifo_pll_rd_en;
  wire fifo_pll_empty;
  wire [7:0] fifo_pll_dout;

  fifo_dualport_8x2048 fifo_pll_xillinux_to_fpga (
    .rst    (rst_pll_ctrl       ), // input wire rst
    .wr_clk (bus_clk            ), // input wire wr_clk
    .rd_clk (clk_pll_ctrl       ), // input wire rd_clk
    .din    (user_w_write_8_data), // input wire [7 : 0] din
    .wr_en  (user_w_write_8_wren), // input wire wr_en
    .rd_en  (fifo_pll_rd_en     ), // input wire rd_en
    .dout   (fifo_pll_dout      ), // output wire [7 : 0] dout
    .full   (user_w_write_8_full), // output wire full
    .empty  (fifo_pll_empty     ) // output wire empty
  );

  // READ FIFO (fpga -> xillinux): controller echoes writeback/loopback bytes
  wire fifo_pll_wr_en;
  wire fifo_pll_full;
  (* mark_debug = "true" *) wire [7:0] fifo_pll_din;

  fifo_dualport_8x2048 fifo_pll_fpga_to_xillinux (
    .rst    (rst_pll_ctrl       ), // input wire rst
    .wr_clk (clk_pll_ctrl       ), // input wire wr_clk
    .rd_clk (bus_clk            ), // input wire rd_clk
    .din    (fifo_pll_din       ), // input wire [7 : 0] din
    .wr_en  (fifo_pll_wr_en     ), // input wire wr_en
    .rd_en  (user_r_read_8_rden ), // input wire rd_en
    .dout   (user_r_read_8_data ), // output wire [7 : 0] dout
    .full   (fifo_pll_full      ), // output wire full
    .empty  (user_r_read_8_empty) // output wire empty
  );

  assign  user_r_read_8_eof = 0;

  /////////////////////////////////////////////////
  ////    CHIP and PERIP CONTROLLER MODULES    ////
  /////////////////////////////////////////////////
  parameter integer CLK_HZ = 100_000_000;       // 100 MHz bus clock
  parameter integer CHIP_SCK_HZ = 25_000_000;   // 25 MHz chip Quad-SPI clock
  parameter integer PERIP_SCK_HZ = 1_000_000;   // 1 MHz DAC SPI + HV9308 S2P shift clock
  parameter integer CSB_HOLD_CYCLES = 40 / (1000_000_000 / CLK_HZ); // 40 ns hold time for CSB signal (see DAC datasheet) converted to number of bus clock cycles

  // Controller for on-chip Quad-SPI
  chip_controller #(
    .CLK_HZ            (CLK_HZ         ),
    .SCK_HZ            (CHIP_SCK_HZ    )
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
    .clk_chip_o        (clk_chip_o      ),
    .chip_arst_no      (chip_arst_no    ),
    // status / activity for LEDs
    .chip_clk_en_o     (chip_clk_en     ),
    .chip_write_pulse_o(chip_write_pulse)
  );

  // Controller for the peripheral DAC (single-port SPI) and HV9308 S2P converter
  perip_controller #(
    .CLK_HZ             (CLK_HZ            ),
    .SCK_HZ             (PERIP_SCK_HZ      ),  // DAC SPI at 1 MHz
    .CSB_HOLD_CYCLES    (CSB_HOLD_CYCLES   ),
    .S2P_SCK_HZ         (PERIP_SCK_HZ      )   // HV9308 shift clock at 1 MHz
  ) perip_controller_inst (
    .clk_i              (clk_perip_ctrl    ),
    .rst_i              (rst_perip_ctrl    ),
    .fifo_perip_rd_en_o (fifo_perip_rd_en  ),
    .fifo_perip_empty_i (fifo_perip_empty  ),
    .fifo_perip_dout_i  (fifo_perip_dout   ),
    .fifo_perip_wr_en_o (fifo_perip_wr_en  ),
    .fifo_perip_full_i  (fifo_perip_full   ),
    .fifo_perip_din_o   (fifo_perip_din    ),
    .dac_clk_o          (dac_sclk_o        ),
    .dac_csb_o          (dac_csb_o         ),
    .dac_sdi_o          (dac_sdin_o        ),
    .dac_shdn_o         (dac_shdn_o        ),
    .dac_rstn_o         (dac_rstn_o        ),
    // HV9308 serial-to-parallel converter
    .s2p_din_o          (s2p_din_o         ),
    .s2p_clk_o          (s2p_clk_o         ),
    .s2p_le_o           (s2p_le_o          ),
    .s2p_oe_o           (s2p_oe_o          ),
    .s2p_dout_i         (s2p_dout_i        ),
    // activity for LED
    .perip_write_pulse_o(perip_write_pulse )
  );

  // Controller for the Pomelo PLL serial configuration (8-bit FIFO stream)
  pll_controller #(
    .STRB_HALF          (50                )  // 1 MHz strobe at clk_pll_ctrl = 100 MHz
  ) pll_controller_inst (
    .clk_i              (clk_pll_ctrl      ),
    .rst_i              (rst_pll_ctrl      ),
    .fifo_pll_rd_en_o   (fifo_pll_rd_en    ),
    .fifo_pll_empty_i   (fifo_pll_empty    ),
    .fifo_pll_dout_i    (fifo_pll_dout     ),
    .fifo_pll_wr_en_o   (fifo_pll_wr_en    ),
    .fifo_pll_full_i    (fifo_pll_full     ),
    .fifo_pll_din_o     (fifo_pll_din      ),
    .pll_clk_sel_o      (pll_clk_sel_o     ),
    .pll_data_strb_o    (pll_data_strb_o   ),
    .pll_data_o         (pll_data_o        ),
    .pll_cfg_vld_strb_o (pll_cfg_vld_strb_o),
    .pll_data_i         (pll_data_i        ),
    .pll_lock_i         (pll_lock_i        )
  );

  assign chip_bootmode_o = 2'b00; // default boot mode (00): passive boot

endmodule

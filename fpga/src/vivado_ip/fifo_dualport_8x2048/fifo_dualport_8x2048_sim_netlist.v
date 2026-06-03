// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// --------------------------------------------------------------------------------
// Tool Version: Vivado v.2025.2 (lin64) Build 6299465 Fri Nov 14 12:34:56 MST 2025
// Date        : Wed Jun  3 17:27:08 2026
// Host        : neptune.esat.kuleuven.be running 64-bit Rocky Linux release 8.10 (Green Obsidian)
// Command     : write_verilog -force -mode funcsim
//               /users/micas/jsun/sunjc/codes/aria_project/tapeout/lagd-meas/fpga/src/vivado_ip/fifo_dualport_8x2048/fifo_dualport_8x2048_sim_netlist.v
// Design      : fifo_dualport_8x2048
// Purpose     : This verilog netlist is a functional simulation representation of the design and should not be modified
//               or synthesized. This netlist cannot be used for SDF annotated simulation.
// Device      : xc7z020clg484-1
// --------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

(* CHECK_LICENSE_TYPE = "fifo_dualport_8x2048,fifo_generator_v13_2_14,{}" *) (* downgradeipidentifiedwarnings = "yes" *) (* x_core_info = "fifo_generator_v13_2_14,Vivado 2025.2" *) 
(* NotValidForBitStream *)
module fifo_dualport_8x2048
   (rst,
    wr_clk,
    rd_clk,
    din,
    wr_en,
    rd_en,
    dout,
    full,
    empty,
    wr_rst_busy,
    rd_rst_busy);
  input rst;
  (* x_interface_info = "xilinx.com:signal:clock:1.0 write_clk CLK" *) (* x_interface_mode = "slave write_clk" *) (* x_interface_parameter = "XIL_INTERFACENAME write_clk, FREQ_HZ 100000000, FREQ_TOLERANCE_HZ 0, PHASE 0.0, INSERT_VIP 0" *) input wr_clk;
  (* x_interface_info = "xilinx.com:signal:clock:1.0 read_clk CLK" *) (* x_interface_mode = "slave read_clk" *) (* x_interface_parameter = "XIL_INTERFACENAME read_clk, FREQ_HZ 100000000, FREQ_TOLERANCE_HZ 0, PHASE 0.0, INSERT_VIP 0" *) input rd_clk;
  (* x_interface_info = "xilinx.com:interface:fifo_write:1.0 FIFO_WRITE WR_DATA" *) (* x_interface_mode = "slave FIFO_WRITE" *) input [7:0]din;
  (* x_interface_info = "xilinx.com:interface:fifo_write:1.0 FIFO_WRITE WR_EN" *) input wr_en;
  (* x_interface_info = "xilinx.com:interface:fifo_read:1.0 FIFO_READ RD_EN" *) (* x_interface_mode = "slave FIFO_READ" *) input rd_en;
  (* x_interface_info = "xilinx.com:interface:fifo_read:1.0 FIFO_READ RD_DATA" *) output [7:0]dout;
  (* x_interface_info = "xilinx.com:interface:fifo_write:1.0 FIFO_WRITE FULL" *) output full;
  (* x_interface_info = "xilinx.com:interface:fifo_read:1.0 FIFO_READ EMPTY" *) output empty;
  output wr_rst_busy;
  output rd_rst_busy;

  wire [7:0]din;
  wire [7:0]dout;
  wire empty;
  wire full;
  wire rd_clk;
  wire rd_en;
  wire rd_rst_busy;
  wire rst;
  wire wr_clk;
  wire wr_en;
  wire wr_rst_busy;
  wire NLW_U0_almost_empty_UNCONNECTED;
  wire NLW_U0_almost_full_UNCONNECTED;
  wire NLW_U0_axi_ar_dbiterr_UNCONNECTED;
  wire NLW_U0_axi_ar_overflow_UNCONNECTED;
  wire NLW_U0_axi_ar_prog_empty_UNCONNECTED;
  wire NLW_U0_axi_ar_prog_full_UNCONNECTED;
  wire NLW_U0_axi_ar_sbiterr_UNCONNECTED;
  wire NLW_U0_axi_ar_underflow_UNCONNECTED;
  wire NLW_U0_axi_aw_dbiterr_UNCONNECTED;
  wire NLW_U0_axi_aw_overflow_UNCONNECTED;
  wire NLW_U0_axi_aw_prog_empty_UNCONNECTED;
  wire NLW_U0_axi_aw_prog_full_UNCONNECTED;
  wire NLW_U0_axi_aw_sbiterr_UNCONNECTED;
  wire NLW_U0_axi_aw_underflow_UNCONNECTED;
  wire NLW_U0_axi_b_dbiterr_UNCONNECTED;
  wire NLW_U0_axi_b_overflow_UNCONNECTED;
  wire NLW_U0_axi_b_prog_empty_UNCONNECTED;
  wire NLW_U0_axi_b_prog_full_UNCONNECTED;
  wire NLW_U0_axi_b_sbiterr_UNCONNECTED;
  wire NLW_U0_axi_b_underflow_UNCONNECTED;
  wire NLW_U0_axi_r_dbiterr_UNCONNECTED;
  wire NLW_U0_axi_r_overflow_UNCONNECTED;
  wire NLW_U0_axi_r_prog_empty_UNCONNECTED;
  wire NLW_U0_axi_r_prog_full_UNCONNECTED;
  wire NLW_U0_axi_r_sbiterr_UNCONNECTED;
  wire NLW_U0_axi_r_underflow_UNCONNECTED;
  wire NLW_U0_axi_w_dbiterr_UNCONNECTED;
  wire NLW_U0_axi_w_overflow_UNCONNECTED;
  wire NLW_U0_axi_w_prog_empty_UNCONNECTED;
  wire NLW_U0_axi_w_prog_full_UNCONNECTED;
  wire NLW_U0_axi_w_sbiterr_UNCONNECTED;
  wire NLW_U0_axi_w_underflow_UNCONNECTED;
  wire NLW_U0_axis_dbiterr_UNCONNECTED;
  wire NLW_U0_axis_overflow_UNCONNECTED;
  wire NLW_U0_axis_prog_empty_UNCONNECTED;
  wire NLW_U0_axis_prog_full_UNCONNECTED;
  wire NLW_U0_axis_sbiterr_UNCONNECTED;
  wire NLW_U0_axis_underflow_UNCONNECTED;
  wire NLW_U0_dbiterr_UNCONNECTED;
  wire NLW_U0_m_axi_arvalid_UNCONNECTED;
  wire NLW_U0_m_axi_awvalid_UNCONNECTED;
  wire NLW_U0_m_axi_bready_UNCONNECTED;
  wire NLW_U0_m_axi_rready_UNCONNECTED;
  wire NLW_U0_m_axi_wlast_UNCONNECTED;
  wire NLW_U0_m_axi_wvalid_UNCONNECTED;
  wire NLW_U0_m_axis_tlast_UNCONNECTED;
  wire NLW_U0_m_axis_tvalid_UNCONNECTED;
  wire NLW_U0_overflow_UNCONNECTED;
  wire NLW_U0_prog_empty_UNCONNECTED;
  wire NLW_U0_prog_full_UNCONNECTED;
  wire NLW_U0_s_axi_arready_UNCONNECTED;
  wire NLW_U0_s_axi_awready_UNCONNECTED;
  wire NLW_U0_s_axi_bvalid_UNCONNECTED;
  wire NLW_U0_s_axi_rlast_UNCONNECTED;
  wire NLW_U0_s_axi_rvalid_UNCONNECTED;
  wire NLW_U0_s_axi_wready_UNCONNECTED;
  wire NLW_U0_s_axis_tready_UNCONNECTED;
  wire NLW_U0_sbiterr_UNCONNECTED;
  wire NLW_U0_underflow_UNCONNECTED;
  wire NLW_U0_valid_UNCONNECTED;
  wire NLW_U0_wr_ack_UNCONNECTED;
  wire [4:0]NLW_U0_axi_ar_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_ar_rd_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_ar_wr_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_aw_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_aw_rd_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_aw_wr_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_b_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_b_rd_data_count_UNCONNECTED;
  wire [4:0]NLW_U0_axi_b_wr_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axi_r_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axi_r_rd_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axi_r_wr_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axi_w_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axi_w_rd_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axi_w_wr_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axis_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axis_rd_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_axis_wr_data_count_UNCONNECTED;
  wire [10:0]NLW_U0_data_count_UNCONNECTED;
  wire [31:0]NLW_U0_m_axi_araddr_UNCONNECTED;
  wire [1:0]NLW_U0_m_axi_arburst_UNCONNECTED;
  wire [3:0]NLW_U0_m_axi_arcache_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_arid_UNCONNECTED;
  wire [7:0]NLW_U0_m_axi_arlen_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_arlock_UNCONNECTED;
  wire [2:0]NLW_U0_m_axi_arprot_UNCONNECTED;
  wire [3:0]NLW_U0_m_axi_arqos_UNCONNECTED;
  wire [3:0]NLW_U0_m_axi_arregion_UNCONNECTED;
  wire [2:0]NLW_U0_m_axi_arsize_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_aruser_UNCONNECTED;
  wire [31:0]NLW_U0_m_axi_awaddr_UNCONNECTED;
  wire [1:0]NLW_U0_m_axi_awburst_UNCONNECTED;
  wire [3:0]NLW_U0_m_axi_awcache_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_awid_UNCONNECTED;
  wire [7:0]NLW_U0_m_axi_awlen_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_awlock_UNCONNECTED;
  wire [2:0]NLW_U0_m_axi_awprot_UNCONNECTED;
  wire [3:0]NLW_U0_m_axi_awqos_UNCONNECTED;
  wire [3:0]NLW_U0_m_axi_awregion_UNCONNECTED;
  wire [2:0]NLW_U0_m_axi_awsize_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_awuser_UNCONNECTED;
  wire [63:0]NLW_U0_m_axi_wdata_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_wid_UNCONNECTED;
  wire [7:0]NLW_U0_m_axi_wstrb_UNCONNECTED;
  wire [0:0]NLW_U0_m_axi_wuser_UNCONNECTED;
  wire [0:0]NLW_U0_m_axis_tdata_UNCONNECTED;
  wire [0:0]NLW_U0_m_axis_tdest_UNCONNECTED;
  wire [0:0]NLW_U0_m_axis_tid_UNCONNECTED;
  wire [0:0]NLW_U0_m_axis_tkeep_UNCONNECTED;
  wire [0:0]NLW_U0_m_axis_tstrb_UNCONNECTED;
  wire [3:0]NLW_U0_m_axis_tuser_UNCONNECTED;
  wire [10:0]NLW_U0_rd_data_count_UNCONNECTED;
  wire [0:0]NLW_U0_s_axi_bid_UNCONNECTED;
  wire [1:0]NLW_U0_s_axi_bresp_UNCONNECTED;
  wire [0:0]NLW_U0_s_axi_buser_UNCONNECTED;
  wire [63:0]NLW_U0_s_axi_rdata_UNCONNECTED;
  wire [0:0]NLW_U0_s_axi_rid_UNCONNECTED;
  wire [1:0]NLW_U0_s_axi_rresp_UNCONNECTED;
  wire [0:0]NLW_U0_s_axi_ruser_UNCONNECTED;
  wire [10:0]NLW_U0_wr_data_count_UNCONNECTED;

  (* C_ADD_NGC_CONSTRAINT = "0" *) 
  (* C_APPLICATION_TYPE_AXIS = "0" *) 
  (* C_APPLICATION_TYPE_RACH = "0" *) 
  (* C_APPLICATION_TYPE_RDCH = "0" *) 
  (* C_APPLICATION_TYPE_WACH = "0" *) 
  (* C_APPLICATION_TYPE_WDCH = "0" *) 
  (* C_APPLICATION_TYPE_WRCH = "0" *) 
  (* C_AXIS_TDATA_WIDTH = "1" *) 
  (* C_AXIS_TDEST_WIDTH = "1" *) 
  (* C_AXIS_TID_WIDTH = "1" *) 
  (* C_AXIS_TKEEP_WIDTH = "1" *) 
  (* C_AXIS_TSTRB_WIDTH = "1" *) 
  (* C_AXIS_TUSER_WIDTH = "4" *) 
  (* C_AXIS_TYPE = "0" *) 
  (* C_AXI_ADDR_WIDTH = "32" *) 
  (* C_AXI_ARUSER_WIDTH = "1" *) 
  (* C_AXI_AWUSER_WIDTH = "1" *) 
  (* C_AXI_BUSER_WIDTH = "1" *) 
  (* C_AXI_DATA_WIDTH = "64" *) 
  (* C_AXI_ID_WIDTH = "1" *) 
  (* C_AXI_LEN_WIDTH = "8" *) 
  (* C_AXI_LOCK_WIDTH = "1" *) 
  (* C_AXI_RUSER_WIDTH = "1" *) 
  (* C_AXI_TYPE = "1" *) 
  (* C_AXI_WUSER_WIDTH = "1" *) 
  (* C_COMMON_CLOCK = "0" *) 
  (* C_COUNT_TYPE = "0" *) 
  (* C_DATA_COUNT_WIDTH = "11" *) 
  (* C_DEFAULT_VALUE = "BlankString" *) 
  (* C_DIN_WIDTH = "8" *) 
  (* C_DIN_WIDTH_AXIS = "1" *) 
  (* C_DIN_WIDTH_RACH = "32" *) 
  (* C_DIN_WIDTH_RDCH = "64" *) 
  (* C_DIN_WIDTH_WACH = "1" *) 
  (* C_DIN_WIDTH_WDCH = "64" *) 
  (* C_DIN_WIDTH_WRCH = "2" *) 
  (* C_DOUT_RST_VAL = "0" *) 
  (* C_DOUT_WIDTH = "8" *) 
  (* C_ENABLE_RLOCS = "0" *) 
  (* C_ENABLE_RST_SYNC = "1" *) 
  (* C_EN_SAFETY_CKT = "1" *) 
  (* C_ERROR_INJECTION_TYPE = "0" *) 
  (* C_ERROR_INJECTION_TYPE_AXIS = "0" *) 
  (* C_ERROR_INJECTION_TYPE_RACH = "0" *) 
  (* C_ERROR_INJECTION_TYPE_RDCH = "0" *) 
  (* C_ERROR_INJECTION_TYPE_WACH = "0" *) 
  (* C_ERROR_INJECTION_TYPE_WDCH = "0" *) 
  (* C_ERROR_INJECTION_TYPE_WRCH = "0" *) 
  (* C_FAMILY = "zynq" *) 
  (* C_FULL_FLAGS_RST_VAL = "1" *) 
  (* C_HAS_ALMOST_EMPTY = "0" *) 
  (* C_HAS_ALMOST_FULL = "0" *) 
  (* C_HAS_AXIS_TDATA = "0" *) 
  (* C_HAS_AXIS_TDEST = "0" *) 
  (* C_HAS_AXIS_TID = "0" *) 
  (* C_HAS_AXIS_TKEEP = "0" *) 
  (* C_HAS_AXIS_TLAST = "0" *) 
  (* C_HAS_AXIS_TREADY = "1" *) 
  (* C_HAS_AXIS_TSTRB = "0" *) 
  (* C_HAS_AXIS_TUSER = "1" *) 
  (* C_HAS_AXI_ARUSER = "0" *) 
  (* C_HAS_AXI_AWUSER = "0" *) 
  (* C_HAS_AXI_BUSER = "0" *) 
  (* C_HAS_AXI_ID = "0" *) 
  (* C_HAS_AXI_RD_CHANNEL = "1" *) 
  (* C_HAS_AXI_RUSER = "0" *) 
  (* C_HAS_AXI_WR_CHANNEL = "1" *) 
  (* C_HAS_AXI_WUSER = "0" *) 
  (* C_HAS_BACKUP = "0" *) 
  (* C_HAS_DATA_COUNT = "0" *) 
  (* C_HAS_DATA_COUNTS_AXIS = "0" *) 
  (* C_HAS_DATA_COUNTS_RACH = "0" *) 
  (* C_HAS_DATA_COUNTS_RDCH = "0" *) 
  (* C_HAS_DATA_COUNTS_WACH = "0" *) 
  (* C_HAS_DATA_COUNTS_WDCH = "0" *) 
  (* C_HAS_DATA_COUNTS_WRCH = "0" *) 
  (* C_HAS_INT_CLK = "0" *) 
  (* C_HAS_MASTER_CE = "0" *) 
  (* C_HAS_MEMINIT_FILE = "0" *) 
  (* C_HAS_OVERFLOW = "0" *) 
  (* C_HAS_PROG_FLAGS_AXIS = "0" *) 
  (* C_HAS_PROG_FLAGS_RACH = "0" *) 
  (* C_HAS_PROG_FLAGS_RDCH = "0" *) 
  (* C_HAS_PROG_FLAGS_WACH = "0" *) 
  (* C_HAS_PROG_FLAGS_WDCH = "0" *) 
  (* C_HAS_PROG_FLAGS_WRCH = "0" *) 
  (* C_HAS_RD_DATA_COUNT = "0" *) 
  (* C_HAS_RD_RST = "0" *) 
  (* C_HAS_RST = "1" *) 
  (* C_HAS_SLAVE_CE = "0" *) 
  (* C_HAS_SRST = "0" *) 
  (* C_HAS_UNDERFLOW = "0" *) 
  (* C_HAS_VALID = "0" *) 
  (* C_HAS_WR_ACK = "0" *) 
  (* C_HAS_WR_DATA_COUNT = "0" *) 
  (* C_HAS_WR_RST = "0" *) 
  (* C_IMPLEMENTATION_TYPE = "2" *) 
  (* C_IMPLEMENTATION_TYPE_AXIS = "1" *) 
  (* C_IMPLEMENTATION_TYPE_RACH = "2" *) 
  (* C_IMPLEMENTATION_TYPE_RDCH = "1" *) 
  (* C_IMPLEMENTATION_TYPE_WACH = "2" *) 
  (* C_IMPLEMENTATION_TYPE_WDCH = "1" *) 
  (* C_IMPLEMENTATION_TYPE_WRCH = "2" *) 
  (* C_INIT_WR_PNTR_VAL = "0" *) 
  (* C_INTERFACE_TYPE = "0" *) 
  (* C_MEMORY_TYPE = "1" *) 
  (* C_MIF_FILE_NAME = "BlankString" *) 
  (* C_MSGON_VAL = "1" *) 
  (* C_OPTIMIZATION_MODE = "0" *) 
  (* C_OVERFLOW_LOW = "0" *) 
  (* C_POWER_SAVING_MODE = "0" *) 
  (* C_PRELOAD_LATENCY = "1" *) 
  (* C_PRELOAD_REGS = "0" *) 
  (* C_PRIM_FIFO_TYPE = "2kx9" *) 
  (* C_PRIM_FIFO_TYPE_AXIS = "1kx18" *) 
  (* C_PRIM_FIFO_TYPE_RACH = "512x36" *) 
  (* C_PRIM_FIFO_TYPE_RDCH = "1kx36" *) 
  (* C_PRIM_FIFO_TYPE_WACH = "512x36" *) 
  (* C_PRIM_FIFO_TYPE_WDCH = "1kx36" *) 
  (* C_PRIM_FIFO_TYPE_WRCH = "512x36" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL = "2" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL_AXIS = "1022" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL_RACH = "1022" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL_RDCH = "1022" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL_WACH = "1022" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL_WDCH = "1022" *) 
  (* C_PROG_EMPTY_THRESH_ASSERT_VAL_WRCH = "1022" *) 
  (* C_PROG_EMPTY_THRESH_NEGATE_VAL = "3" *) 
  (* C_PROG_EMPTY_TYPE = "0" *) 
  (* C_PROG_EMPTY_TYPE_AXIS = "0" *) 
  (* C_PROG_EMPTY_TYPE_RACH = "0" *) 
  (* C_PROG_EMPTY_TYPE_RDCH = "0" *) 
  (* C_PROG_EMPTY_TYPE_WACH = "0" *) 
  (* C_PROG_EMPTY_TYPE_WDCH = "0" *) 
  (* C_PROG_EMPTY_TYPE_WRCH = "0" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL = "2045" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL_AXIS = "1023" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL_RACH = "1023" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL_RDCH = "1023" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL_WACH = "1023" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL_WDCH = "1023" *) 
  (* C_PROG_FULL_THRESH_ASSERT_VAL_WRCH = "1023" *) 
  (* C_PROG_FULL_THRESH_NEGATE_VAL = "2044" *) 
  (* C_PROG_FULL_TYPE = "0" *) 
  (* C_PROG_FULL_TYPE_AXIS = "0" *) 
  (* C_PROG_FULL_TYPE_RACH = "0" *) 
  (* C_PROG_FULL_TYPE_RDCH = "0" *) 
  (* C_PROG_FULL_TYPE_WACH = "0" *) 
  (* C_PROG_FULL_TYPE_WDCH = "0" *) 
  (* C_PROG_FULL_TYPE_WRCH = "0" *) 
  (* C_RACH_TYPE = "0" *) 
  (* C_RDCH_TYPE = "0" *) 
  (* C_RD_DATA_COUNT_WIDTH = "11" *) 
  (* C_RD_DEPTH = "2048" *) 
  (* C_RD_FREQ = "1" *) 
  (* C_RD_PNTR_WIDTH = "11" *) 
  (* C_REG_SLICE_MODE_AXIS = "0" *) 
  (* C_REG_SLICE_MODE_RACH = "0" *) 
  (* C_REG_SLICE_MODE_RDCH = "0" *) 
  (* C_REG_SLICE_MODE_WACH = "0" *) 
  (* C_REG_SLICE_MODE_WDCH = "0" *) 
  (* C_REG_SLICE_MODE_WRCH = "0" *) 
  (* C_SELECT_XPM = "0" *) 
  (* C_SYNCHRONIZER_STAGE = "2" *) 
  (* C_UNDERFLOW_LOW = "0" *) 
  (* C_USE_COMMON_OVERFLOW = "0" *) 
  (* C_USE_COMMON_UNDERFLOW = "0" *) 
  (* C_USE_DEFAULT_SETTINGS = "0" *) 
  (* C_USE_DOUT_RST = "1" *) 
  (* C_USE_ECC = "0" *) 
  (* C_USE_ECC_AXIS = "0" *) 
  (* C_USE_ECC_RACH = "0" *) 
  (* C_USE_ECC_RDCH = "0" *) 
  (* C_USE_ECC_WACH = "0" *) 
  (* C_USE_ECC_WDCH = "0" *) 
  (* C_USE_ECC_WRCH = "0" *) 
  (* C_USE_EMBEDDED_REG = "0" *) 
  (* C_USE_FIFO16_FLAGS = "0" *) 
  (* C_USE_FWFT_DATA_COUNT = "0" *) 
  (* C_USE_PIPELINE_REG = "0" *) 
  (* C_VALID_LOW = "0" *) 
  (* C_WACH_TYPE = "0" *) 
  (* C_WDCH_TYPE = "0" *) 
  (* C_WRCH_TYPE = "0" *) 
  (* C_WR_ACK_LOW = "0" *) 
  (* C_WR_DATA_COUNT_WIDTH = "11" *) 
  (* C_WR_DEPTH = "2048" *) 
  (* C_WR_DEPTH_AXIS = "1024" *) 
  (* C_WR_DEPTH_RACH = "16" *) 
  (* C_WR_DEPTH_RDCH = "1024" *) 
  (* C_WR_DEPTH_WACH = "16" *) 
  (* C_WR_DEPTH_WDCH = "1024" *) 
  (* C_WR_DEPTH_WRCH = "16" *) 
  (* C_WR_FREQ = "1" *) 
  (* C_WR_PNTR_WIDTH = "11" *) 
  (* C_WR_PNTR_WIDTH_AXIS = "10" *) 
  (* C_WR_PNTR_WIDTH_RACH = "4" *) 
  (* C_WR_PNTR_WIDTH_RDCH = "10" *) 
  (* C_WR_PNTR_WIDTH_WACH = "4" *) 
  (* C_WR_PNTR_WIDTH_WDCH = "10" *) 
  (* C_WR_PNTR_WIDTH_WRCH = "4" *) 
  (* C_WR_RESPONSE_LATENCY = "1" *) 
  (* is_du_within_envelope = "true" *) 
  fifo_dualport_8x2048_fifo_generator_v13_2_14 U0
       (.almost_empty(NLW_U0_almost_empty_UNCONNECTED),
        .almost_full(NLW_U0_almost_full_UNCONNECTED),
        .axi_ar_data_count(NLW_U0_axi_ar_data_count_UNCONNECTED[4:0]),
        .axi_ar_dbiterr(NLW_U0_axi_ar_dbiterr_UNCONNECTED),
        .axi_ar_injectdbiterr(1'b0),
        .axi_ar_injectsbiterr(1'b0),
        .axi_ar_overflow(NLW_U0_axi_ar_overflow_UNCONNECTED),
        .axi_ar_prog_empty(NLW_U0_axi_ar_prog_empty_UNCONNECTED),
        .axi_ar_prog_empty_thresh({1'b0,1'b0,1'b0,1'b0}),
        .axi_ar_prog_full(NLW_U0_axi_ar_prog_full_UNCONNECTED),
        .axi_ar_prog_full_thresh({1'b0,1'b0,1'b0,1'b0}),
        .axi_ar_rd_data_count(NLW_U0_axi_ar_rd_data_count_UNCONNECTED[4:0]),
        .axi_ar_sbiterr(NLW_U0_axi_ar_sbiterr_UNCONNECTED),
        .axi_ar_underflow(NLW_U0_axi_ar_underflow_UNCONNECTED),
        .axi_ar_wr_data_count(NLW_U0_axi_ar_wr_data_count_UNCONNECTED[4:0]),
        .axi_aw_data_count(NLW_U0_axi_aw_data_count_UNCONNECTED[4:0]),
        .axi_aw_dbiterr(NLW_U0_axi_aw_dbiterr_UNCONNECTED),
        .axi_aw_injectdbiterr(1'b0),
        .axi_aw_injectsbiterr(1'b0),
        .axi_aw_overflow(NLW_U0_axi_aw_overflow_UNCONNECTED),
        .axi_aw_prog_empty(NLW_U0_axi_aw_prog_empty_UNCONNECTED),
        .axi_aw_prog_empty_thresh({1'b0,1'b0,1'b0,1'b0}),
        .axi_aw_prog_full(NLW_U0_axi_aw_prog_full_UNCONNECTED),
        .axi_aw_prog_full_thresh({1'b0,1'b0,1'b0,1'b0}),
        .axi_aw_rd_data_count(NLW_U0_axi_aw_rd_data_count_UNCONNECTED[4:0]),
        .axi_aw_sbiterr(NLW_U0_axi_aw_sbiterr_UNCONNECTED),
        .axi_aw_underflow(NLW_U0_axi_aw_underflow_UNCONNECTED),
        .axi_aw_wr_data_count(NLW_U0_axi_aw_wr_data_count_UNCONNECTED[4:0]),
        .axi_b_data_count(NLW_U0_axi_b_data_count_UNCONNECTED[4:0]),
        .axi_b_dbiterr(NLW_U0_axi_b_dbiterr_UNCONNECTED),
        .axi_b_injectdbiterr(1'b0),
        .axi_b_injectsbiterr(1'b0),
        .axi_b_overflow(NLW_U0_axi_b_overflow_UNCONNECTED),
        .axi_b_prog_empty(NLW_U0_axi_b_prog_empty_UNCONNECTED),
        .axi_b_prog_empty_thresh({1'b0,1'b0,1'b0,1'b0}),
        .axi_b_prog_full(NLW_U0_axi_b_prog_full_UNCONNECTED),
        .axi_b_prog_full_thresh({1'b0,1'b0,1'b0,1'b0}),
        .axi_b_rd_data_count(NLW_U0_axi_b_rd_data_count_UNCONNECTED[4:0]),
        .axi_b_sbiterr(NLW_U0_axi_b_sbiterr_UNCONNECTED),
        .axi_b_underflow(NLW_U0_axi_b_underflow_UNCONNECTED),
        .axi_b_wr_data_count(NLW_U0_axi_b_wr_data_count_UNCONNECTED[4:0]),
        .axi_r_data_count(NLW_U0_axi_r_data_count_UNCONNECTED[10:0]),
        .axi_r_dbiterr(NLW_U0_axi_r_dbiterr_UNCONNECTED),
        .axi_r_injectdbiterr(1'b0),
        .axi_r_injectsbiterr(1'b0),
        .axi_r_overflow(NLW_U0_axi_r_overflow_UNCONNECTED),
        .axi_r_prog_empty(NLW_U0_axi_r_prog_empty_UNCONNECTED),
        .axi_r_prog_empty_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .axi_r_prog_full(NLW_U0_axi_r_prog_full_UNCONNECTED),
        .axi_r_prog_full_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .axi_r_rd_data_count(NLW_U0_axi_r_rd_data_count_UNCONNECTED[10:0]),
        .axi_r_sbiterr(NLW_U0_axi_r_sbiterr_UNCONNECTED),
        .axi_r_underflow(NLW_U0_axi_r_underflow_UNCONNECTED),
        .axi_r_wr_data_count(NLW_U0_axi_r_wr_data_count_UNCONNECTED[10:0]),
        .axi_w_data_count(NLW_U0_axi_w_data_count_UNCONNECTED[10:0]),
        .axi_w_dbiterr(NLW_U0_axi_w_dbiterr_UNCONNECTED),
        .axi_w_injectdbiterr(1'b0),
        .axi_w_injectsbiterr(1'b0),
        .axi_w_overflow(NLW_U0_axi_w_overflow_UNCONNECTED),
        .axi_w_prog_empty(NLW_U0_axi_w_prog_empty_UNCONNECTED),
        .axi_w_prog_empty_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .axi_w_prog_full(NLW_U0_axi_w_prog_full_UNCONNECTED),
        .axi_w_prog_full_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .axi_w_rd_data_count(NLW_U0_axi_w_rd_data_count_UNCONNECTED[10:0]),
        .axi_w_sbiterr(NLW_U0_axi_w_sbiterr_UNCONNECTED),
        .axi_w_underflow(NLW_U0_axi_w_underflow_UNCONNECTED),
        .axi_w_wr_data_count(NLW_U0_axi_w_wr_data_count_UNCONNECTED[10:0]),
        .axis_data_count(NLW_U0_axis_data_count_UNCONNECTED[10:0]),
        .axis_dbiterr(NLW_U0_axis_dbiterr_UNCONNECTED),
        .axis_injectdbiterr(1'b0),
        .axis_injectsbiterr(1'b0),
        .axis_overflow(NLW_U0_axis_overflow_UNCONNECTED),
        .axis_prog_empty(NLW_U0_axis_prog_empty_UNCONNECTED),
        .axis_prog_empty_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .axis_prog_full(NLW_U0_axis_prog_full_UNCONNECTED),
        .axis_prog_full_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .axis_rd_data_count(NLW_U0_axis_rd_data_count_UNCONNECTED[10:0]),
        .axis_sbiterr(NLW_U0_axis_sbiterr_UNCONNECTED),
        .axis_underflow(NLW_U0_axis_underflow_UNCONNECTED),
        .axis_wr_data_count(NLW_U0_axis_wr_data_count_UNCONNECTED[10:0]),
        .backup(1'b0),
        .backup_marker(1'b0),
        .clk(1'b0),
        .data_count(NLW_U0_data_count_UNCONNECTED[10:0]),
        .dbiterr(NLW_U0_dbiterr_UNCONNECTED),
        .din(din),
        .dout(dout),
        .empty(empty),
        .full(full),
        .injectdbiterr(1'b0),
        .injectsbiterr(1'b0),
        .int_clk(1'b0),
        .m_aclk(1'b0),
        .m_aclk_en(1'b0),
        .m_axi_araddr(NLW_U0_m_axi_araddr_UNCONNECTED[31:0]),
        .m_axi_arburst(NLW_U0_m_axi_arburst_UNCONNECTED[1:0]),
        .m_axi_arcache(NLW_U0_m_axi_arcache_UNCONNECTED[3:0]),
        .m_axi_arid(NLW_U0_m_axi_arid_UNCONNECTED[0]),
        .m_axi_arlen(NLW_U0_m_axi_arlen_UNCONNECTED[7:0]),
        .m_axi_arlock(NLW_U0_m_axi_arlock_UNCONNECTED[0]),
        .m_axi_arprot(NLW_U0_m_axi_arprot_UNCONNECTED[2:0]),
        .m_axi_arqos(NLW_U0_m_axi_arqos_UNCONNECTED[3:0]),
        .m_axi_arready(1'b0),
        .m_axi_arregion(NLW_U0_m_axi_arregion_UNCONNECTED[3:0]),
        .m_axi_arsize(NLW_U0_m_axi_arsize_UNCONNECTED[2:0]),
        .m_axi_aruser(NLW_U0_m_axi_aruser_UNCONNECTED[0]),
        .m_axi_arvalid(NLW_U0_m_axi_arvalid_UNCONNECTED),
        .m_axi_awaddr(NLW_U0_m_axi_awaddr_UNCONNECTED[31:0]),
        .m_axi_awburst(NLW_U0_m_axi_awburst_UNCONNECTED[1:0]),
        .m_axi_awcache(NLW_U0_m_axi_awcache_UNCONNECTED[3:0]),
        .m_axi_awid(NLW_U0_m_axi_awid_UNCONNECTED[0]),
        .m_axi_awlen(NLW_U0_m_axi_awlen_UNCONNECTED[7:0]),
        .m_axi_awlock(NLW_U0_m_axi_awlock_UNCONNECTED[0]),
        .m_axi_awprot(NLW_U0_m_axi_awprot_UNCONNECTED[2:0]),
        .m_axi_awqos(NLW_U0_m_axi_awqos_UNCONNECTED[3:0]),
        .m_axi_awready(1'b0),
        .m_axi_awregion(NLW_U0_m_axi_awregion_UNCONNECTED[3:0]),
        .m_axi_awsize(NLW_U0_m_axi_awsize_UNCONNECTED[2:0]),
        .m_axi_awuser(NLW_U0_m_axi_awuser_UNCONNECTED[0]),
        .m_axi_awvalid(NLW_U0_m_axi_awvalid_UNCONNECTED),
        .m_axi_bid(1'b0),
        .m_axi_bready(NLW_U0_m_axi_bready_UNCONNECTED),
        .m_axi_bresp({1'b0,1'b0}),
        .m_axi_buser(1'b0),
        .m_axi_bvalid(1'b0),
        .m_axi_rdata({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .m_axi_rid(1'b0),
        .m_axi_rlast(1'b0),
        .m_axi_rready(NLW_U0_m_axi_rready_UNCONNECTED),
        .m_axi_rresp({1'b0,1'b0}),
        .m_axi_ruser(1'b0),
        .m_axi_rvalid(1'b0),
        .m_axi_wdata(NLW_U0_m_axi_wdata_UNCONNECTED[63:0]),
        .m_axi_wid(NLW_U0_m_axi_wid_UNCONNECTED[0]),
        .m_axi_wlast(NLW_U0_m_axi_wlast_UNCONNECTED),
        .m_axi_wready(1'b0),
        .m_axi_wstrb(NLW_U0_m_axi_wstrb_UNCONNECTED[7:0]),
        .m_axi_wuser(NLW_U0_m_axi_wuser_UNCONNECTED[0]),
        .m_axi_wvalid(NLW_U0_m_axi_wvalid_UNCONNECTED),
        .m_axis_tdata(NLW_U0_m_axis_tdata_UNCONNECTED[0]),
        .m_axis_tdest(NLW_U0_m_axis_tdest_UNCONNECTED[0]),
        .m_axis_tid(NLW_U0_m_axis_tid_UNCONNECTED[0]),
        .m_axis_tkeep(NLW_U0_m_axis_tkeep_UNCONNECTED[0]),
        .m_axis_tlast(NLW_U0_m_axis_tlast_UNCONNECTED),
        .m_axis_tready(1'b0),
        .m_axis_tstrb(NLW_U0_m_axis_tstrb_UNCONNECTED[0]),
        .m_axis_tuser(NLW_U0_m_axis_tuser_UNCONNECTED[3:0]),
        .m_axis_tvalid(NLW_U0_m_axis_tvalid_UNCONNECTED),
        .overflow(NLW_U0_overflow_UNCONNECTED),
        .prog_empty(NLW_U0_prog_empty_UNCONNECTED),
        .prog_empty_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .prog_empty_thresh_assert({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .prog_empty_thresh_negate({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .prog_full(NLW_U0_prog_full_UNCONNECTED),
        .prog_full_thresh({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .prog_full_thresh_assert({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .prog_full_thresh_negate({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .rd_clk(rd_clk),
        .rd_data_count(NLW_U0_rd_data_count_UNCONNECTED[10:0]),
        .rd_en(rd_en),
        .rd_rst(1'b0),
        .rd_rst_busy(rd_rst_busy),
        .rst(rst),
        .s_aclk(1'b0),
        .s_aclk_en(1'b0),
        .s_aresetn(1'b0),
        .s_axi_araddr({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .s_axi_arburst({1'b0,1'b0}),
        .s_axi_arcache({1'b0,1'b0,1'b0,1'b0}),
        .s_axi_arid(1'b0),
        .s_axi_arlen({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .s_axi_arlock(1'b0),
        .s_axi_arprot({1'b0,1'b0,1'b0}),
        .s_axi_arqos({1'b0,1'b0,1'b0,1'b0}),
        .s_axi_arready(NLW_U0_s_axi_arready_UNCONNECTED),
        .s_axi_arregion({1'b0,1'b0,1'b0,1'b0}),
        .s_axi_arsize({1'b0,1'b0,1'b0}),
        .s_axi_aruser(1'b0),
        .s_axi_arvalid(1'b0),
        .s_axi_awaddr({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .s_axi_awburst({1'b0,1'b0}),
        .s_axi_awcache({1'b0,1'b0,1'b0,1'b0}),
        .s_axi_awid(1'b0),
        .s_axi_awlen({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .s_axi_awlock(1'b0),
        .s_axi_awprot({1'b0,1'b0,1'b0}),
        .s_axi_awqos({1'b0,1'b0,1'b0,1'b0}),
        .s_axi_awready(NLW_U0_s_axi_awready_UNCONNECTED),
        .s_axi_awregion({1'b0,1'b0,1'b0,1'b0}),
        .s_axi_awsize({1'b0,1'b0,1'b0}),
        .s_axi_awuser(1'b0),
        .s_axi_awvalid(1'b0),
        .s_axi_bid(NLW_U0_s_axi_bid_UNCONNECTED[0]),
        .s_axi_bready(1'b0),
        .s_axi_bresp(NLW_U0_s_axi_bresp_UNCONNECTED[1:0]),
        .s_axi_buser(NLW_U0_s_axi_buser_UNCONNECTED[0]),
        .s_axi_bvalid(NLW_U0_s_axi_bvalid_UNCONNECTED),
        .s_axi_rdata(NLW_U0_s_axi_rdata_UNCONNECTED[63:0]),
        .s_axi_rid(NLW_U0_s_axi_rid_UNCONNECTED[0]),
        .s_axi_rlast(NLW_U0_s_axi_rlast_UNCONNECTED),
        .s_axi_rready(1'b0),
        .s_axi_rresp(NLW_U0_s_axi_rresp_UNCONNECTED[1:0]),
        .s_axi_ruser(NLW_U0_s_axi_ruser_UNCONNECTED[0]),
        .s_axi_rvalid(NLW_U0_s_axi_rvalid_UNCONNECTED),
        .s_axi_wdata({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .s_axi_wid(1'b0),
        .s_axi_wlast(1'b0),
        .s_axi_wready(NLW_U0_s_axi_wready_UNCONNECTED),
        .s_axi_wstrb({1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0,1'b0}),
        .s_axi_wuser(1'b0),
        .s_axi_wvalid(1'b0),
        .s_axis_tdata(1'b0),
        .s_axis_tdest(1'b0),
        .s_axis_tid(1'b0),
        .s_axis_tkeep(1'b0),
        .s_axis_tlast(1'b0),
        .s_axis_tready(NLW_U0_s_axis_tready_UNCONNECTED),
        .s_axis_tstrb(1'b0),
        .s_axis_tuser({1'b0,1'b0,1'b0,1'b0}),
        .s_axis_tvalid(1'b0),
        .sbiterr(NLW_U0_sbiterr_UNCONNECTED),
        .sleep(1'b0),
        .srst(1'b0),
        .underflow(NLW_U0_underflow_UNCONNECTED),
        .valid(NLW_U0_valid_UNCONNECTED),
        .wr_ack(NLW_U0_wr_ack_UNCONNECTED),
        .wr_clk(wr_clk),
        .wr_data_count(NLW_U0_wr_data_count_UNCONNECTED[10:0]),
        .wr_en(wr_en),
        .wr_rst(1'b0),
        .wr_rst_busy(wr_rst_busy));
endmodule

(* DEST_SYNC_FF = "2" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_gray" *) 
(* REG_OUTPUT = "1" *) (* SIM_ASSERT_CHK = "0" *) (* SIM_LOSSLESS_GRAY_CHK = "0" *) 
(* VERSION = "0" *) (* WIDTH = "11" *) (* XPM_MODULE = "TRUE" *) 
(* is_du_within_envelope = "true" *) (* keep_hierarchy = "soft" *) (* xpm_cdc = "GRAY" *) 
module fifo_dualport_8x2048_xpm_cdc_gray
   (src_clk,
    src_in_bin,
    dest_clk,
    dest_out_bin);
  input src_clk;
  input [10:0]src_in_bin;
  input dest_clk;
  output [10:0]dest_out_bin;

  wire [10:0]async_path;
  wire [9:0]binval;
  wire dest_clk;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "GRAY" *) wire [10:0]\dest_graysync_ff[0] ;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "GRAY" *) wire [10:0]\dest_graysync_ff[1] ;
  wire [10:0]dest_out_bin;
  wire [9:0]gray_enc;
  wire src_clk;
  wire [10:0]src_in_bin;

  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[0]),
        .Q(\dest_graysync_ff[0] [0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][10] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[10]),
        .Q(\dest_graysync_ff[0] [10]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[1]),
        .Q(\dest_graysync_ff[0] [1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[2]),
        .Q(\dest_graysync_ff[0] [2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[3]),
        .Q(\dest_graysync_ff[0] [3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[4]),
        .Q(\dest_graysync_ff[0] [4]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][5] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[5]),
        .Q(\dest_graysync_ff[0] [5]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][6] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[6]),
        .Q(\dest_graysync_ff[0] [6]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][7] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[7]),
        .Q(\dest_graysync_ff[0] [7]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][8] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[8]),
        .Q(\dest_graysync_ff[0] [8]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][9] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[9]),
        .Q(\dest_graysync_ff[0] [9]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [0]),
        .Q(\dest_graysync_ff[1] [0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][10] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [10]),
        .Q(\dest_graysync_ff[1] [10]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [1]),
        .Q(\dest_graysync_ff[1] [1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [2]),
        .Q(\dest_graysync_ff[1] [2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [3]),
        .Q(\dest_graysync_ff[1] [3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [4]),
        .Q(\dest_graysync_ff[1] [4]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][5] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [5]),
        .Q(\dest_graysync_ff[1] [5]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][6] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [6]),
        .Q(\dest_graysync_ff[1] [6]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][7] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [7]),
        .Q(\dest_graysync_ff[1] [7]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][8] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [8]),
        .Q(\dest_graysync_ff[1] [8]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][9] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [9]),
        .Q(\dest_graysync_ff[1] [9]),
        .R(1'b0));
  LUT6 #(
    .INIT(64'h6996966996696996)) 
    \dest_out_bin_ff[0]_i_1 
       (.I0(\dest_graysync_ff[1] [0]),
        .I1(\dest_graysync_ff[1] [2]),
        .I2(\dest_graysync_ff[1] [4]),
        .I3(binval[5]),
        .I4(\dest_graysync_ff[1] [3]),
        .I5(\dest_graysync_ff[1] [1]),
        .O(binval[0]));
  LUT5 #(
    .INIT(32'h96696996)) 
    \dest_out_bin_ff[1]_i_1 
       (.I0(\dest_graysync_ff[1] [1]),
        .I1(\dest_graysync_ff[1] [3]),
        .I2(binval[5]),
        .I3(\dest_graysync_ff[1] [4]),
        .I4(\dest_graysync_ff[1] [2]),
        .O(binval[1]));
  LUT4 #(
    .INIT(16'h6996)) 
    \dest_out_bin_ff[2]_i_1 
       (.I0(\dest_graysync_ff[1] [2]),
        .I1(\dest_graysync_ff[1] [4]),
        .I2(binval[5]),
        .I3(\dest_graysync_ff[1] [3]),
        .O(binval[2]));
  LUT3 #(
    .INIT(8'h96)) 
    \dest_out_bin_ff[3]_i_1 
       (.I0(\dest_graysync_ff[1] [3]),
        .I1(binval[5]),
        .I2(\dest_graysync_ff[1] [4]),
        .O(binval[3]));
  LUT2 #(
    .INIT(4'h6)) 
    \dest_out_bin_ff[4]_i_1 
       (.I0(\dest_graysync_ff[1] [4]),
        .I1(binval[5]),
        .O(binval[4]));
  LUT6 #(
    .INIT(64'h6996966996696996)) 
    \dest_out_bin_ff[5]_i_1 
       (.I0(\dest_graysync_ff[1] [5]),
        .I1(\dest_graysync_ff[1] [7]),
        .I2(\dest_graysync_ff[1] [9]),
        .I3(\dest_graysync_ff[1] [10]),
        .I4(\dest_graysync_ff[1] [8]),
        .I5(\dest_graysync_ff[1] [6]),
        .O(binval[5]));
  LUT5 #(
    .INIT(32'h96696996)) 
    \dest_out_bin_ff[6]_i_1 
       (.I0(\dest_graysync_ff[1] [6]),
        .I1(\dest_graysync_ff[1] [8]),
        .I2(\dest_graysync_ff[1] [10]),
        .I3(\dest_graysync_ff[1] [9]),
        .I4(\dest_graysync_ff[1] [7]),
        .O(binval[6]));
  LUT4 #(
    .INIT(16'h6996)) 
    \dest_out_bin_ff[7]_i_1 
       (.I0(\dest_graysync_ff[1] [7]),
        .I1(\dest_graysync_ff[1] [9]),
        .I2(\dest_graysync_ff[1] [10]),
        .I3(\dest_graysync_ff[1] [8]),
        .O(binval[7]));
  LUT3 #(
    .INIT(8'h96)) 
    \dest_out_bin_ff[8]_i_1 
       (.I0(\dest_graysync_ff[1] [8]),
        .I1(\dest_graysync_ff[1] [10]),
        .I2(\dest_graysync_ff[1] [9]),
        .O(binval[8]));
  LUT2 #(
    .INIT(4'h6)) 
    \dest_out_bin_ff[9]_i_1 
       (.I0(\dest_graysync_ff[1] [9]),
        .I1(\dest_graysync_ff[1] [10]),
        .O(binval[9]));
  FDRE \dest_out_bin_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[0]),
        .Q(dest_out_bin[0]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[10] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[1] [10]),
        .Q(dest_out_bin[10]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[1]),
        .Q(dest_out_bin[1]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[2]),
        .Q(dest_out_bin[2]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[3]),
        .Q(dest_out_bin[3]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[4]),
        .Q(dest_out_bin[4]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[5] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[5]),
        .Q(dest_out_bin[5]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[6] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[6]),
        .Q(dest_out_bin[6]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[7] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[7]),
        .Q(dest_out_bin[7]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[8] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[8]),
        .Q(dest_out_bin[8]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[9] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[9]),
        .Q(dest_out_bin[9]),
        .R(1'b0));
  (* SOFT_HLUTNM = "soft_lutpair5" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[0]_i_1 
       (.I0(src_in_bin[1]),
        .I1(src_in_bin[0]),
        .O(gray_enc[0]));
  (* SOFT_HLUTNM = "soft_lutpair5" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[1]_i_1 
       (.I0(src_in_bin[2]),
        .I1(src_in_bin[1]),
        .O(gray_enc[1]));
  (* SOFT_HLUTNM = "soft_lutpair6" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[2]_i_1 
       (.I0(src_in_bin[3]),
        .I1(src_in_bin[2]),
        .O(gray_enc[2]));
  (* SOFT_HLUTNM = "soft_lutpair6" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[3]_i_1 
       (.I0(src_in_bin[4]),
        .I1(src_in_bin[3]),
        .O(gray_enc[3]));
  (* SOFT_HLUTNM = "soft_lutpair7" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[4]_i_1 
       (.I0(src_in_bin[5]),
        .I1(src_in_bin[4]),
        .O(gray_enc[4]));
  (* SOFT_HLUTNM = "soft_lutpair7" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[5]_i_1 
       (.I0(src_in_bin[6]),
        .I1(src_in_bin[5]),
        .O(gray_enc[5]));
  (* SOFT_HLUTNM = "soft_lutpair8" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[6]_i_1 
       (.I0(src_in_bin[7]),
        .I1(src_in_bin[6]),
        .O(gray_enc[6]));
  (* SOFT_HLUTNM = "soft_lutpair8" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[7]_i_1 
       (.I0(src_in_bin[8]),
        .I1(src_in_bin[7]),
        .O(gray_enc[7]));
  (* SOFT_HLUTNM = "soft_lutpair9" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[8]_i_1 
       (.I0(src_in_bin[9]),
        .I1(src_in_bin[8]),
        .O(gray_enc[8]));
  (* SOFT_HLUTNM = "soft_lutpair9" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[9]_i_1 
       (.I0(src_in_bin[10]),
        .I1(src_in_bin[9]),
        .O(gray_enc[9]));
  FDRE \src_gray_ff_reg[0] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[0]),
        .Q(async_path[0]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[10] 
       (.C(src_clk),
        .CE(1'b1),
        .D(src_in_bin[10]),
        .Q(async_path[10]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[1] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[1]),
        .Q(async_path[1]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[2] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[2]),
        .Q(async_path[2]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[3] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[3]),
        .Q(async_path[3]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[4] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[4]),
        .Q(async_path[4]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[5] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[5]),
        .Q(async_path[5]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[6] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[6]),
        .Q(async_path[6]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[7] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[7]),
        .Q(async_path[7]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[8] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[8]),
        .Q(async_path[8]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[9] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[9]),
        .Q(async_path[9]),
        .R(1'b0));
endmodule

(* DEST_SYNC_FF = "2" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_gray" *) 
(* REG_OUTPUT = "1" *) (* SIM_ASSERT_CHK = "0" *) (* SIM_LOSSLESS_GRAY_CHK = "0" *) 
(* VERSION = "0" *) (* WIDTH = "11" *) (* XPM_MODULE = "TRUE" *) 
(* is_du_within_envelope = "true" *) (* keep_hierarchy = "soft" *) (* xpm_cdc = "GRAY" *) 
module fifo_dualport_8x2048_xpm_cdc_gray__1
   (src_clk,
    src_in_bin,
    dest_clk,
    dest_out_bin);
  input src_clk;
  input [10:0]src_in_bin;
  input dest_clk;
  output [10:0]dest_out_bin;

  wire [10:0]async_path;
  wire [9:0]binval;
  wire dest_clk;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "GRAY" *) wire [10:0]\dest_graysync_ff[0] ;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "GRAY" *) wire [10:0]\dest_graysync_ff[1] ;
  wire [10:0]dest_out_bin;
  wire [9:0]gray_enc;
  wire src_clk;
  wire [10:0]src_in_bin;

  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[0]),
        .Q(\dest_graysync_ff[0] [0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][10] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[10]),
        .Q(\dest_graysync_ff[0] [10]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[1]),
        .Q(\dest_graysync_ff[0] [1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[2]),
        .Q(\dest_graysync_ff[0] [2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[3]),
        .Q(\dest_graysync_ff[0] [3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[4]),
        .Q(\dest_graysync_ff[0] [4]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][5] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[5]),
        .Q(\dest_graysync_ff[0] [5]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][6] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[6]),
        .Q(\dest_graysync_ff[0] [6]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][7] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[7]),
        .Q(\dest_graysync_ff[0] [7]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][8] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[8]),
        .Q(\dest_graysync_ff[0] [8]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[0][9] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(async_path[9]),
        .Q(\dest_graysync_ff[0] [9]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [0]),
        .Q(\dest_graysync_ff[1] [0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][10] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [10]),
        .Q(\dest_graysync_ff[1] [10]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [1]),
        .Q(\dest_graysync_ff[1] [1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [2]),
        .Q(\dest_graysync_ff[1] [2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [3]),
        .Q(\dest_graysync_ff[1] [3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [4]),
        .Q(\dest_graysync_ff[1] [4]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][5] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [5]),
        .Q(\dest_graysync_ff[1] [5]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][6] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [6]),
        .Q(\dest_graysync_ff[1] [6]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][7] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [7]),
        .Q(\dest_graysync_ff[1] [7]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][8] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [8]),
        .Q(\dest_graysync_ff[1] [8]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "GRAY" *) 
  FDRE \dest_graysync_ff_reg[1][9] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[0] [9]),
        .Q(\dest_graysync_ff[1] [9]),
        .R(1'b0));
  LUT6 #(
    .INIT(64'h6996966996696996)) 
    \dest_out_bin_ff[0]_i_1 
       (.I0(\dest_graysync_ff[1] [0]),
        .I1(\dest_graysync_ff[1] [2]),
        .I2(\dest_graysync_ff[1] [4]),
        .I3(binval[5]),
        .I4(\dest_graysync_ff[1] [3]),
        .I5(\dest_graysync_ff[1] [1]),
        .O(binval[0]));
  LUT5 #(
    .INIT(32'h96696996)) 
    \dest_out_bin_ff[1]_i_1 
       (.I0(\dest_graysync_ff[1] [1]),
        .I1(\dest_graysync_ff[1] [3]),
        .I2(binval[5]),
        .I3(\dest_graysync_ff[1] [4]),
        .I4(\dest_graysync_ff[1] [2]),
        .O(binval[1]));
  LUT4 #(
    .INIT(16'h6996)) 
    \dest_out_bin_ff[2]_i_1 
       (.I0(\dest_graysync_ff[1] [2]),
        .I1(\dest_graysync_ff[1] [4]),
        .I2(binval[5]),
        .I3(\dest_graysync_ff[1] [3]),
        .O(binval[2]));
  LUT3 #(
    .INIT(8'h96)) 
    \dest_out_bin_ff[3]_i_1 
       (.I0(\dest_graysync_ff[1] [3]),
        .I1(binval[5]),
        .I2(\dest_graysync_ff[1] [4]),
        .O(binval[3]));
  LUT2 #(
    .INIT(4'h6)) 
    \dest_out_bin_ff[4]_i_1 
       (.I0(\dest_graysync_ff[1] [4]),
        .I1(binval[5]),
        .O(binval[4]));
  LUT6 #(
    .INIT(64'h6996966996696996)) 
    \dest_out_bin_ff[5]_i_1 
       (.I0(\dest_graysync_ff[1] [5]),
        .I1(\dest_graysync_ff[1] [7]),
        .I2(\dest_graysync_ff[1] [9]),
        .I3(\dest_graysync_ff[1] [10]),
        .I4(\dest_graysync_ff[1] [8]),
        .I5(\dest_graysync_ff[1] [6]),
        .O(binval[5]));
  LUT5 #(
    .INIT(32'h96696996)) 
    \dest_out_bin_ff[6]_i_1 
       (.I0(\dest_graysync_ff[1] [6]),
        .I1(\dest_graysync_ff[1] [8]),
        .I2(\dest_graysync_ff[1] [10]),
        .I3(\dest_graysync_ff[1] [9]),
        .I4(\dest_graysync_ff[1] [7]),
        .O(binval[6]));
  LUT4 #(
    .INIT(16'h6996)) 
    \dest_out_bin_ff[7]_i_1 
       (.I0(\dest_graysync_ff[1] [7]),
        .I1(\dest_graysync_ff[1] [9]),
        .I2(\dest_graysync_ff[1] [10]),
        .I3(\dest_graysync_ff[1] [8]),
        .O(binval[7]));
  LUT3 #(
    .INIT(8'h96)) 
    \dest_out_bin_ff[8]_i_1 
       (.I0(\dest_graysync_ff[1] [8]),
        .I1(\dest_graysync_ff[1] [10]),
        .I2(\dest_graysync_ff[1] [9]),
        .O(binval[8]));
  LUT2 #(
    .INIT(4'h6)) 
    \dest_out_bin_ff[9]_i_1 
       (.I0(\dest_graysync_ff[1] [9]),
        .I1(\dest_graysync_ff[1] [10]),
        .O(binval[9]));
  FDRE \dest_out_bin_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[0]),
        .Q(dest_out_bin[0]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[10] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(\dest_graysync_ff[1] [10]),
        .Q(dest_out_bin[10]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[1]),
        .Q(dest_out_bin[1]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[2]),
        .Q(dest_out_bin[2]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[3]),
        .Q(dest_out_bin[3]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[4]),
        .Q(dest_out_bin[4]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[5] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[5]),
        .Q(dest_out_bin[5]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[6] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[6]),
        .Q(dest_out_bin[6]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[7] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[7]),
        .Q(dest_out_bin[7]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[8] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[8]),
        .Q(dest_out_bin[8]),
        .R(1'b0));
  FDRE \dest_out_bin_ff_reg[9] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(binval[9]),
        .Q(dest_out_bin[9]),
        .R(1'b0));
  (* SOFT_HLUTNM = "soft_lutpair0" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[0]_i_1 
       (.I0(src_in_bin[1]),
        .I1(src_in_bin[0]),
        .O(gray_enc[0]));
  (* SOFT_HLUTNM = "soft_lutpair0" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[1]_i_1 
       (.I0(src_in_bin[2]),
        .I1(src_in_bin[1]),
        .O(gray_enc[1]));
  (* SOFT_HLUTNM = "soft_lutpair1" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[2]_i_1 
       (.I0(src_in_bin[3]),
        .I1(src_in_bin[2]),
        .O(gray_enc[2]));
  (* SOFT_HLUTNM = "soft_lutpair1" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[3]_i_1 
       (.I0(src_in_bin[4]),
        .I1(src_in_bin[3]),
        .O(gray_enc[3]));
  (* SOFT_HLUTNM = "soft_lutpair2" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[4]_i_1 
       (.I0(src_in_bin[5]),
        .I1(src_in_bin[4]),
        .O(gray_enc[4]));
  (* SOFT_HLUTNM = "soft_lutpair2" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[5]_i_1 
       (.I0(src_in_bin[6]),
        .I1(src_in_bin[5]),
        .O(gray_enc[5]));
  (* SOFT_HLUTNM = "soft_lutpair3" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[6]_i_1 
       (.I0(src_in_bin[7]),
        .I1(src_in_bin[6]),
        .O(gray_enc[6]));
  (* SOFT_HLUTNM = "soft_lutpair3" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[7]_i_1 
       (.I0(src_in_bin[8]),
        .I1(src_in_bin[7]),
        .O(gray_enc[7]));
  (* SOFT_HLUTNM = "soft_lutpair4" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[8]_i_1 
       (.I0(src_in_bin[9]),
        .I1(src_in_bin[8]),
        .O(gray_enc[8]));
  (* SOFT_HLUTNM = "soft_lutpair4" *) 
  LUT2 #(
    .INIT(4'h6)) 
    \src_gray_ff[9]_i_1 
       (.I0(src_in_bin[10]),
        .I1(src_in_bin[9]),
        .O(gray_enc[9]));
  FDRE \src_gray_ff_reg[0] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[0]),
        .Q(async_path[0]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[10] 
       (.C(src_clk),
        .CE(1'b1),
        .D(src_in_bin[10]),
        .Q(async_path[10]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[1] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[1]),
        .Q(async_path[1]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[2] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[2]),
        .Q(async_path[2]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[3] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[3]),
        .Q(async_path[3]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[4] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[4]),
        .Q(async_path[4]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[5] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[5]),
        .Q(async_path[5]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[6] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[6]),
        .Q(async_path[6]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[7] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[7]),
        .Q(async_path[7]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[8] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[8]),
        .Q(async_path[8]),
        .R(1'b0));
  FDRE \src_gray_ff_reg[9] 
       (.C(src_clk),
        .CE(1'b1),
        .D(gray_enc[9]),
        .Q(async_path[9]),
        .R(1'b0));
endmodule

(* DEST_SYNC_FF = "5" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_single" *) 
(* SIM_ASSERT_CHK = "0" *) (* SRC_INPUT_REG = "0" *) (* VERSION = "0" *) 
(* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) (* keep_hierarchy = "soft" *) 
(* xpm_cdc = "SINGLE" *) 
module fifo_dualport_8x2048_xpm_cdc_single
   (src_clk,
    src_in,
    dest_clk,
    dest_out);
  input src_clk;
  input src_in;
  input dest_clk;
  output dest_out;

  wire dest_clk;
  wire src_in;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "SINGLE" *) wire [4:0]syncstages_ff;

  assign dest_out = syncstages_ff[4];
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(src_in),
        .Q(syncstages_ff[0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[0]),
        .Q(syncstages_ff[1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[1]),
        .Q(syncstages_ff[2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[2]),
        .Q(syncstages_ff[3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[3]),
        .Q(syncstages_ff[4]),
        .R(1'b0));
endmodule

(* DEST_SYNC_FF = "5" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_single" *) 
(* SIM_ASSERT_CHK = "0" *) (* SRC_INPUT_REG = "0" *) (* VERSION = "0" *) 
(* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) (* keep_hierarchy = "soft" *) 
(* xpm_cdc = "SINGLE" *) 
module fifo_dualport_8x2048_xpm_cdc_single__1
   (src_clk,
    src_in,
    dest_clk,
    dest_out);
  input src_clk;
  input src_in;
  input dest_clk;
  output dest_out;

  wire dest_clk;
  wire src_in;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "SINGLE" *) wire [4:0]syncstages_ff;

  assign dest_out = syncstages_ff[4];
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(src_in),
        .Q(syncstages_ff[0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[0]),
        .Q(syncstages_ff[1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[1]),
        .Q(syncstages_ff[2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[2]),
        .Q(syncstages_ff[3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SINGLE" *) 
  FDRE \syncstages_ff_reg[4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[3]),
        .Q(syncstages_ff[4]),
        .R(1'b0));
endmodule

(* DEF_VAL = "1'b1" *) (* DEST_SYNC_FF = "5" *) (* INIT = "1" *) 
(* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_sync_rst" *) (* SIM_ASSERT_CHK = "0" *) 
(* VERSION = "0" *) (* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) 
(* keep_hierarchy = "soft" *) (* xpm_cdc = "SYNC_RST" *) 
module fifo_dualport_8x2048_xpm_cdc_sync_rst
   (src_rst,
    dest_clk,
    dest_rst);
  input src_rst;
  input dest_clk;
  output dest_rst;

  wire dest_clk;
  wire src_rst;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "SYNC_RST" *) wire [4:0]syncstages_ff;

  assign dest_rst = syncstages_ff[4];
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(src_rst),
        .Q(syncstages_ff[0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[0]),
        .Q(syncstages_ff[1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[1]),
        .Q(syncstages_ff[2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[2]),
        .Q(syncstages_ff[3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[3]),
        .Q(syncstages_ff[4]),
        .R(1'b0));
endmodule

(* DEF_VAL = "1'b1" *) (* DEST_SYNC_FF = "5" *) (* INIT = "1" *) 
(* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_sync_rst" *) (* SIM_ASSERT_CHK = "0" *) 
(* VERSION = "0" *) (* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) 
(* keep_hierarchy = "soft" *) (* xpm_cdc = "SYNC_RST" *) 
module fifo_dualport_8x2048_xpm_cdc_sync_rst__1
   (src_rst,
    dest_clk,
    dest_rst);
  input src_rst;
  input dest_clk;
  output dest_rst;

  wire dest_clk;
  wire src_rst;
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "SYNC_RST" *) wire [4:0]syncstages_ff;

  assign dest_rst = syncstages_ff[4];
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(src_rst),
        .Q(syncstages_ff[0]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[0]),
        .Q(syncstages_ff[1]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[2] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[1]),
        .Q(syncstages_ff[2]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[3] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[2]),
        .Q(syncstages_ff[3]),
        .R(1'b0));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "SYNC_RST" *) 
  FDRE #(
    .INIT(1'b1)) 
    \syncstages_ff_reg[4] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(syncstages_ff[3]),
        .Q(syncstages_ff[4]),
        .R(1'b0));
endmodule
`pragma protect begin_protected
`pragma protect version = 1
`pragma protect encrypt_agent = "XILINX"
`pragma protect encrypt_agent_info = "Xilinx Encryption Tool 2025.2"
`pragma protect key_keyowner="Synopsys", key_keyname="SNPS-VCS-RSA-2", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=128)
`pragma protect key_block
YqH9kwIC39+qbZg4PSfFsXuB9k9wnuxNryS/CfnEri6Ci9fSC6fsrQ/T/hnt3u/yolbJ8DJa1Qu6
Qnm24A9jLbA+fu3Nsmm6/rM6a4vU6OfVl/gTFd/CiWDutv6Dhn6Lim4uUNPahoOR/A2Yc4Zo2tdI
kMLO9gn9WlH2l3O2oXs=

`pragma protect key_keyowner="Aldec", key_keyname="ALDEC15_001", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
XJYO2VHd/cnMxQd3i7/2qRhl57dl+doEKuhAunQyv3vpGRG/jlNxj8PqrgLoF0HMdqE3qJUVE/oq
kBSapqjVjLDMOrNGQ+Tc6VGsKMZH8FE/TXHQJ/IM5Iuiu2eozEwwVUomF+7cfqn+9OsVsqCONQ1M
g0oRlangiqasJDhhMfnlGGqwAwmgWRGQA6dmhTuua1s8zdvIv540zY6p5au8cAKVhqyyKK7wbxEE
SGuFqX+NYoyRV+rfWCcWM+hJEmnWS8LNAKkd13YE2+17sPYzUdZ23DmTxXK6KlAxKFW27CBySUfg
qdNXp2DSs2KAQYih27pBNMuHfGbM/ATFPWFvxg==

`pragma protect key_keyowner="Mentor Graphics Corporation", key_keyname="MGC-VELOCE-RSA", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=128)
`pragma protect key_block
lYoEi/e8HsDTz6N11EDe/B/iitERmeYndlCklmCluwgb0N4W80JUGVlkd7NlRZHRNhxaNBJPkcjC
n61nO0tb17NwsMwjbY5TF8JWRYTNw1JXCFacvQYrdKv4/7QNQEtwVGiCLxFhOA8aHlWMZIrc2fri
VRMVWaEBcPwCGorlVIM=

`pragma protect key_keyowner="Mentor Graphics Corporation", key_keyname="MGC-VERIF-SIM-RSA-2", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
QEw9fEsWFbdX0OQLvYs/gl+zyEOW3ak9TdQVaq+0AXXOT3LIqF7wDxJ6ZBnlf9mNbdsUVH5tAz1o
H8u7ihJl1L3THEvugW+TS8hkvVbEA9rKO2vV15KAj4Lla7UdFT/xDfe79RFarlLI7yGrubjgdoRi
QWy//UKsffG7IWNwmoSuppWiWB4ZHJtkunNyIkm70JPGyZF62VxJg1MTT+5LUbZG5vZjjuHZud9w
xJaKv1tFP/x8RVqLU5gPOqGqTW7/nKO2S+450Vo4D9vAmBVVcXpaL1EbSmCvQ+qJmcQKtf9qYFRV
Zko08hbpHjPxstqvTDro01jRzB8592m4xU2TWA==

`pragma protect key_keyowner="Real Intent", key_keyname="RI-RSA-KEY-1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
TC7q853CWBPPJgbRfgDV1lmjUwSAtliljShAyNFg8sfRfwDzchthzoSPH1UCHV++E2JXacEKq1lB
UWsNP92U4Xh0/Gu+6esOI0pJb8I+TRTxyBN1I4cRQEfQHcwfhbSdeH3yX9OV3opLEqYmT37hWU+J
zCawYnxVESI0FtRzEXve9gdEWlrKKckrT/hp4mvxxOjvOkOSQBvy0elgUOqh6mEOZl+JnUbsR+Wm
CoZLE1eefMZy3FnVmyDNPv3JPXi88aLXMyimal0MYFkTiS4XJiGT3eAIMIbksehXY+eYi/KFpZWQ
GHpX+lG3UmiWWLwyPakFwKEHbrBc70AlJ2eV9g==

`pragma protect key_keyowner="Xilinx", key_keyname="xilinxt_2025.1-2029.x", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
j9nmCKgjPWNChPbpSW6EWLrMA6oCG2JGPoum8px09v0PEAh0DRXZi0J8HPzXUsZgOEMcKpA7X54u
YFcDDCLAQ+urha/eSPbQYHQh4yGCursxAQ1C6LEyNQ2wJ0eLlO2bJeAl/gof06zqsYVM2lLJVNv5
wao1k2bmgPdfpfY3c9vPD0fSMuZPS41EoRS0cQhO5GTZnKdjxm6tEUL3GnTjB8ynSCIbCJUsMtAX
4FRHNa52gudx5B5fagR+lXgFhE7e++rWTJELr7SYB+r5Es8qZLTpCH8TrQxEkV0rY/+e4sAjNE2D
gHw8GD7VcUtc15B8y1BbVmh29qc8Nd3V2i/miA==

`pragma protect key_keyowner="Metrics Technologies Inc.", key_keyname="DSim", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
UkCD6I/Vye4qNoNoa3hIexBXG3xyKUJPAHAjIo7UcNVCDXpMQiYEtPDqExZMfiPlJn2nswCYIfIJ
FYWqMCloKSQyyI/7yZ2EtbyWEklb/P5IyZyvGi6hhFUo/JFTb12b4bK0gZPr+bCDdlVQKTx5GVHz
wptdUJO2omSj8axVMPbLRRtVzlJIZ29dTJ2ATXVXAcBxPnFfHRAMnYYKLeeLExX61vQvpqrkLQHm
XG7hpVzJi56gYKAzxa2BLq072OCVpVS70bfWlhlSTVcSlCrUf+EcarEk4FD8+Ih2NCvrqremG6yn
TtcBn8Xr8M/6zhOYvLi6AD6eArDMKA8n+Ccv8A==

`pragma protect key_keyowner="Atrenta", key_keyname="ATR-SG-RSA-1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=384)
`pragma protect key_block
A5y5QVZU8yjPexRVPioSiAGohCHD5DX5FVobuMyhcgQRExLUhPvnnS8HOtxTj/2IapEcz68gFMGG
Hpi+m725u85/om/Vze9pGIW9Mn328Kz2FIg3W5EvGstfGwY+48LiAGAmTR269JS4lJGVYWYOz7Xk
S8cEsFd2m7j8iyKtARJzD90+UdXq/cIIh725jC9i8nbgxB364zddvm1Z/DF3JRw1qFp6GGcuRai1
KNcJ1j8c9wtIgktpsteU3e5+bxHEw8NT3gWXUFYjm00NDq97Jals8Jjktmum2nQxoF7ivPacfEey
gnSF6jRMkTsZObzc30hAhs0CEtc33hZLhPLHSn8pQ0WyvKJLHdd5s2yckgTZtqxC1Sbwe7WEgNXe
ZMX3pIkz+aoXsAL7GBLyVBMVQcyMoF0w8QGAaTe8sqatABwPqXidYRqNROTf62IYcMpV89XYgaTv
EwIn/oni9KOFd2BFVxRZbFGGC4IjvigsTBUijI+Dk6kVnDh240clGcc4

`pragma protect key_keyowner="Cadence Design Systems.", key_keyname="CDS_RSA_KEY_VER_1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
Omtp+lCaqUx7Z4qdFj2zrN8LpCkit2eX4hlMtig+ielGm/x4FSZkpjoFmiqdKFPi2eg0pg09MSai
XyGH68UzAR7Xrj8f1jlIoUmMKp4GcxfdqfTeuu7kWGOJEP6cvgTjSJFj2gawDv7f4yZcltnK2x0L
e4GW/rBTmGvZtKWb2ahjINLxPuh3dDaSaWdb+zVgbtyrI5FrjxBkq+aOxSjyNsqnCx1L0uWbxnkl
88NbXN3dTaECXHNm/fsleayM5hKis7kTv9BFajJMGy+BhQlmIYpE+F5zchnTTFUFJZCz1sX9Fc8e
HcY7irB8mR3ajdzjUZLBQEMktp096Nheq3U75A==

`pragma protect key_keyowner="Synplicity", key_keyname="SYNP15_1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
hpeBLwN9x2ZFDwroYLlUe5GjjDepHik2l0c2s3/6S7JPCRkzQSyt2V1Ad/JewAs/QNp5SXSbYYB4
rQl0My1LDMF3xw43r0g2IbcyHVpPhGp0W5msuQdF67afnsRv90iJYWLMI3QkYGCTWAzl4HrLxFSg
3z8XZRK670IcxznOrlvgHmIKsvubZrBkuc1EynrVb9Nw16QnIx2rc4WgcEXeFf+4i1RoYLDd3gXK
NFCNMdtaRYUThunFP6Z4ViZ5UnDmKq+IMhd31jTaqIlWOBDxPI1+v5RJYxIyTbn4rxlKR2fNbl5/
z4OUjBTd+1GH3I2OXlqmAOvIhpe2Z2HH7nZu/A==

`pragma protect key_keyowner="Mentor Graphics Corporation", key_keyname="MGC-PREC-RSA", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
Mt2RhTSUwEIEWeNARbyL+EdfS1UF6nPaL/fKl/7oO2gina93egwCWDLl1fbBtkfaPco0cu4MJ9K3
OraAsyHRlY+MNShmJ1LzAIA1LjZx4y55lu9dlQqSUXR7AW7wVbkg1864mK+hM/1XygU0jvebKNW9
B7xSER+asLO6pxi0mt7uC2PHxLPAYEszFhmnap82TtbDGdQ2qtyekY+ngs+N2fAdsblxVwJruiMl
e6XJ127M8N1mYwhWU2HtRpBOSnnKoHgD9fG51XK/rhk8DxT66QnX9uLPB+H25eDupBJGi1Y5o6x8
hOwZiSUVlBLh7brfzevh7+eRn+7es6wBas0+3w==

`pragma protect data_method = "AES128-CBC"
`pragma protect encoding = (enctype = "BASE64", line_length = 76, bytes = 125760)
`pragma protect data_block
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
jFeTSuTeGhYnQ5uGPm7D+dn3
`pragma protect end_protected
`ifndef GLBL
`define GLBL
`timescale  1 ps / 1 ps

module glbl ();

    parameter ROC_WIDTH = 100000;
    parameter TOC_WIDTH = 0;
    parameter GRES_WIDTH = 10000;
    parameter GRES_START = 10000;

//--------   STARTUP Globals --------------
    wire GSR;
    wire GTS;
    wire GWE;
    wire PRLD;
    wire GRESTORE;
    tri1 p_up_tmp;
    tri (weak1, strong0) PLL_LOCKG = p_up_tmp;

    wire PROGB_GLBL;
    wire CCLKO_GLBL;
    wire FCSBO_GLBL;
    wire [3:0] DO_GLBL;
    wire [3:0] DI_GLBL;
   
    reg GSR_int;
    reg GTS_int;
    reg PRLD_int;
    reg GRESTORE_int;

//--------   JTAG Globals --------------
    wire JTAG_TDO_GLBL;
    wire JTAG_TCK_GLBL;
    wire JTAG_TDI_GLBL;
    wire JTAG_TMS_GLBL;
    wire JTAG_TRST_GLBL;

    reg JTAG_CAPTURE_GLBL;
    reg JTAG_RESET_GLBL;
    reg JTAG_SHIFT_GLBL;
    reg JTAG_UPDATE_GLBL;
    reg JTAG_RUNTEST_GLBL;

    reg JTAG_SEL1_GLBL = 0;
    reg JTAG_SEL2_GLBL = 0 ;
    reg JTAG_SEL3_GLBL = 0;
    reg JTAG_SEL4_GLBL = 0;

    reg JTAG_USER_TDO1_GLBL = 1'bz;
    reg JTAG_USER_TDO2_GLBL = 1'bz;
    reg JTAG_USER_TDO3_GLBL = 1'bz;
    reg JTAG_USER_TDO4_GLBL = 1'bz;

    assign (strong1, weak0) GSR = GSR_int;
    assign (strong1, weak0) GTS = GTS_int;
    assign (weak1, weak0) PRLD = PRLD_int;
    assign (strong1, weak0) GRESTORE = GRESTORE_int;

    initial begin
	GSR_int = 1'b1;
	PRLD_int = 1'b1;
	#(ROC_WIDTH)
	GSR_int = 1'b0;
	PRLD_int = 1'b0;
    end

    initial begin
	GTS_int = 1'b1;
	#(TOC_WIDTH)
	GTS_int = 1'b0;
    end

    initial begin 
	GRESTORE_int = 1'b0;
	#(GRES_START);
	GRESTORE_int = 1'b1;
	#(GRES_WIDTH);
	GRESTORE_int = 1'b0;
    end

endmodule
`endif

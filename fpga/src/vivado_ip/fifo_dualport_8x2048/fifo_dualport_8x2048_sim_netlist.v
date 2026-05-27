// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2024 Advanced Micro Devices, Inc. All Rights Reserved.
// --------------------------------------------------------------------------------
// Tool Version: Vivado v.2023.2.2 (lin64) Build 4126759 Thu Feb  8 23:52:05 MST 2024
// Date        : Wed May  6 15:49:20 2026
// Host        : cassiopeia.esat.kuleuven.be running 64-bit Rocky Linux release 8.10 (Green Obsidian)
// Command     : write_verilog -force -mode funcsim
//               /esat/micas-lapserv11/users/rgeens/zedboard_bitstream/src/vivado_ip/fifo_dualport_8x2048/fifo_dualport_8x2048_sim_netlist.v
// Design      : fifo_dualport_8x2048
// Purpose     : This verilog netlist is a functional simulation representation of the design and should not be modified
//               or synthesized. This netlist cannot be used for SDF annotated simulation.
// Device      : xc7z020clg484-1
// --------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

(* CHECK_LICENSE_TYPE = "fifo_dualport_8x2048,fifo_generator_v13_2_9,{}" *) (* downgradeipidentifiedwarnings = "yes" *) (* x_core_info = "fifo_generator_v13_2_9,Vivado 2023.2.2" *) 
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
    empty);
  input rst;
  (* x_interface_info = "xilinx.com:signal:clock:1.0 write_clk CLK" *) (* x_interface_parameter = "XIL_INTERFACENAME write_clk, FREQ_HZ 100000000, FREQ_TOLERANCE_HZ 0, PHASE 0.0, INSERT_VIP 0" *) input wr_clk;
  (* x_interface_info = "xilinx.com:signal:clock:1.0 read_clk CLK" *) (* x_interface_parameter = "XIL_INTERFACENAME read_clk, FREQ_HZ 100000000, FREQ_TOLERANCE_HZ 0, PHASE 0.0, INSERT_VIP 0" *) input rd_clk;
  (* x_interface_info = "xilinx.com:interface:fifo_write:1.0 FIFO_WRITE WR_DATA" *) input [7:0]din;
  (* x_interface_info = "xilinx.com:interface:fifo_write:1.0 FIFO_WRITE WR_EN" *) input wr_en;
  (* x_interface_info = "xilinx.com:interface:fifo_read:1.0 FIFO_READ RD_EN" *) input rd_en;
  (* x_interface_info = "xilinx.com:interface:fifo_read:1.0 FIFO_READ RD_DATA" *) output [7:0]dout;
  (* x_interface_info = "xilinx.com:interface:fifo_write:1.0 FIFO_WRITE FULL" *) output full;
  (* x_interface_info = "xilinx.com:interface:fifo_read:1.0 FIFO_READ EMPTY" *) output empty;

  wire [7:0]din;
  wire [7:0]dout;
  wire empty;
  wire full;
  wire rd_clk;
  wire rd_en;
  wire rst;
  wire wr_clk;
  wire wr_en;
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
  wire NLW_U0_rd_rst_busy_UNCONNECTED;
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
  wire NLW_U0_wr_rst_busy_UNCONNECTED;
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
  (* C_EN_SAFETY_CKT = "0" *) 
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
  fifo_dualport_8x2048_fifo_generator_v13_2_9 U0
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
        .rd_rst_busy(NLW_U0_rd_rst_busy_UNCONNECTED),
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
        .wr_rst_busy(NLW_U0_wr_rst_busy_UNCONNECTED));
endmodule

(* DEF_VAL = "1'b0" *) (* DEST_SYNC_FF = "2" *) (* INIT_SYNC_FF = "0" *) 
(* INV_DEF_VAL = "1'b1" *) (* ORIG_REF_NAME = "xpm_cdc_async_rst" *) (* RST_ACTIVE_HIGH = "1" *) 
(* VERSION = "0" *) (* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) 
(* keep_hierarchy = "true" *) (* xpm_cdc = "ASYNC_RST" *) 
module fifo_dualport_8x2048_xpm_cdc_async_rst
   (src_arst,
    dest_clk,
    dest_arst);
  input src_arst;
  input dest_clk;
  output dest_arst;

  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "ASYNC_RST" *) wire [1:0]arststages_ff;
  wire dest_clk;
  wire src_arst;

  assign dest_arst = arststages_ff[1];
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "ASYNC_RST" *) 
  FDPE #(
    .INIT(1'b0)) 
    \arststages_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(1'b0),
        .PRE(src_arst),
        .Q(arststages_ff[0]));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "ASYNC_RST" *) 
  FDPE #(
    .INIT(1'b0)) 
    \arststages_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(arststages_ff[0]),
        .PRE(src_arst),
        .Q(arststages_ff[1]));
endmodule

(* DEF_VAL = "1'b0" *) (* DEST_SYNC_FF = "2" *) (* INIT_SYNC_FF = "0" *) 
(* INV_DEF_VAL = "1'b1" *) (* ORIG_REF_NAME = "xpm_cdc_async_rst" *) (* RST_ACTIVE_HIGH = "1" *) 
(* VERSION = "0" *) (* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) 
(* keep_hierarchy = "true" *) (* xpm_cdc = "ASYNC_RST" *) 
module fifo_dualport_8x2048_xpm_cdc_async_rst__1
   (src_arst,
    dest_clk,
    dest_arst);
  input src_arst;
  input dest_clk;
  output dest_arst;

  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "ASYNC_RST" *) wire [1:0]arststages_ff;
  wire dest_clk;
  wire src_arst;

  assign dest_arst = arststages_ff[1];
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "ASYNC_RST" *) 
  FDPE #(
    .INIT(1'b0)) 
    \arststages_ff_reg[0] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(1'b0),
        .PRE(src_arst),
        .Q(arststages_ff[0]));
  (* ASYNC_REG *) 
  (* KEEP = "true" *) 
  (* XPM_CDC = "ASYNC_RST" *) 
  FDPE #(
    .INIT(1'b0)) 
    \arststages_ff_reg[1] 
       (.C(dest_clk),
        .CE(1'b1),
        .D(arststages_ff[0]),
        .PRE(src_arst),
        .Q(arststages_ff[1]));
endmodule

(* DEST_SYNC_FF = "2" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_gray" *) 
(* REG_OUTPUT = "1" *) (* SIM_ASSERT_CHK = "0" *) (* SIM_LOSSLESS_GRAY_CHK = "0" *) 
(* VERSION = "0" *) (* WIDTH = "11" *) (* XPM_MODULE = "TRUE" *) 
(* is_du_within_envelope = "true" *) (* keep_hierarchy = "true" *) (* xpm_cdc = "GRAY" *) 
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
(* is_du_within_envelope = "true" *) (* keep_hierarchy = "true" *) (* xpm_cdc = "GRAY" *) 
module fifo_dualport_8x2048_xpm_cdc_gray__2
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

(* DEST_SYNC_FF = "4" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_single" *) 
(* SIM_ASSERT_CHK = "0" *) (* SRC_INPUT_REG = "0" *) (* VERSION = "0" *) 
(* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) (* keep_hierarchy = "true" *) 
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
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "SINGLE" *) wire [3:0]syncstages_ff;

  assign dest_out = syncstages_ff[3];
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
endmodule

(* DEST_SYNC_FF = "4" *) (* INIT_SYNC_FF = "0" *) (* ORIG_REF_NAME = "xpm_cdc_single" *) 
(* SIM_ASSERT_CHK = "0" *) (* SRC_INPUT_REG = "0" *) (* VERSION = "0" *) 
(* XPM_MODULE = "TRUE" *) (* is_du_within_envelope = "true" *) (* keep_hierarchy = "true" *) 
(* xpm_cdc = "SINGLE" *) 
module fifo_dualport_8x2048_xpm_cdc_single__2
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
  (* RTL_KEEP = "true" *) (* async_reg = "true" *) (* xpm_cdc = "SINGLE" *) wire [3:0]syncstages_ff;

  assign dest_out = syncstages_ff[3];
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
endmodule
`pragma protect begin_protected
`pragma protect version = 1
`pragma protect encrypt_agent = "XILINX"
`pragma protect encrypt_agent_info = "Xilinx Encryption Tool 2023.2.2"
`pragma protect key_keyowner="Synopsys", key_keyname="SNPS-VCS-RSA-2", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=128)
`pragma protect key_block
JbZQ00Iyh+vxfaesUQJ5dPMt+lxUImJ4DAcKdwv+gJxBzL4kYu7g4Vh3LKiJxxULLJqoHHMnaZQQ
hOktvQ7bL1lY7zYDH0aFfWHkN9SluvQLEzvTDm4CRF02B9iMQ+zCVttXpzpUmYGhCebjq9FbkMbL
acV6ptLjZvGRhm+QPjc=

`pragma protect key_keyowner="Aldec", key_keyname="ALDEC15_001", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
inoQQ91QzDvPOhlT2eY2ii2gLcSCE1x5pZHB74kaq+5F14mFeYDp+4w/lwvZdZkZKcCmbX5xOm8Z
spBY7SvFNrDbZA+SZtoHPjHwxX2cKfZST5pDwUDYU/ZuJSWXILo2dBFsyZY4IOLgZyx0bO1hee5f
MkDVAGcKW7C6sUYyUj/ApP+nsaBMu0Q+BxRZdWQbaCsn8wPfpXYplFFaRCAW8T3eveoycXCGY/bT
SUWfkGtnkiQHmmcpZ9mS7dHQV66rXeCAao3qJvzQYRPaoq6lcuZG+Fzelx9XTWTX0YtX83CD5KWn
UH+of4DCpp3oTwXNuzlOxsJjUXn74HPvDRVQqA==

`pragma protect key_keyowner="Mentor Graphics Corporation", key_keyname="MGC-VELOCE-RSA", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=128)
`pragma protect key_block
fWxnTvX9UkzrgORwlsCsXTw3QrToI8OHuF6mWc2oL/PSNWEWkSKKxhXwOPvZMA6VrDGh+1PbeFAu
DWBiK/AgxDjMS/scu9+3nQ0COZZ2Lszm8DJjCiNasELrHJ5xEyzim1ZWD+SD56s+oChAUqLRTNlW
HWyWr9UlaMlKchJjOoM=

`pragma protect key_keyowner="Mentor Graphics Corporation", key_keyname="MGC-VERIF-SIM-RSA-2", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
h4MHRlBvGKMId8UKxxGRvn0taOTaTfKS/dxL5t5sfxeL1O/Nr43BWV7Kt5ZvDsKdKaYNHdRaBZrm
NdSTLe4yT19dnw/UOrzsC6oFlQSX1/xgjWj+dc37QvyqR85owQ0Qy3ABcKQShXWRPg8GYW4I+Ms8
j/35+EKM+mpMBNAvf6k9w/BfC233OrNHJiAezW8JEH65zOkSmZlrgqp1+vmKNQQext7+Oy0dLfjU
rlibdZwAlg4zw89rQzwmLsik5+uaRhMDCpwT//pdQz9TO2XgjVSpCF+SLAiWy3N0OK8v5TnqP9mL
HnDyetFtuLlPysF7bkHjbA5R+SR1uP6dI/qdVQ==

`pragma protect key_keyowner="Real Intent", key_keyname="RI-RSA-KEY-1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
eAk9YbWT6ygGjnTfFTAMafbk2M6HYgxUZbVx5sksbPEnt1RxYv7UHGMLPh18sL2vfLO3XCf/kwX5
gXqEVj65IjdhlutevU9pqZFMd5el80BM9BL8pK+5K0fVE2sh5YJF8WEd4ZiAX4I5lRAtlycIYk6l
wwPkEiC+AWCGcX4kmj8ixcQ3bmBW24RceKmSgL3wH4K39Tf6t9foBOtkI8LCZUs0sIaghft49ygm
wtobLj2y+UrzK7Zc6jkI9TxfNJcCCwlfhH8mnW7UmX+tw0+i1RBbnQhb9iVCF5ac1LEbnIxPh8JO
vKnnIJaNLZxuQuJr71qRMd+G6InZaH9KP2o/dQ==

`pragma protect key_keyowner="Xilinx", key_keyname="xilinxt_2022_10", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
XPHZz+z39UzonXyXWrbz/eLBOnP3VbB7FvNYJ4HJGzfmJyFJ7So4wft5JR/YhGpWURv9FncqlPlq
3iKpmaAhWbIaMcpNG9J9hW6pmORCll8BGMzGDt21yuPVqxrAnxfXqwlDzvjTMlIXvmJ1HCwA3C/+
7nF8eV+1wHpLvWTgf0tvbZRGvMtV80AE1VZd1ENfrNHYB/EP8TvURPPF85sBskRTikz3HnOjFOI7
esN/Nf5dr/wZZjmJllP/oLriOJyLNlr31DpRtOaQwYOv+EXCKftNkaTde7IKGYTPT3b/AkGH1Uxt
Y4LP8c1QW1pGFeJ3tJuDTmfQLDPW9Eq6P/aSlw==

`pragma protect key_keyowner="Metrics Technologies Inc.", key_keyname="DSim", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
kIV70h1b6z/fQHjhnae/JgWhLgaSvoCoNOR6VgZADmLXBDLgFNsjm3qYhUkSpCY6jtmbyUM9wWRd
XbtRNPLgo3LRtnHtn8M0GwqEM1XtJ1VQrTkVr4tMvfpZnsp544oaXfFgShB556oEQHIND7f0or59
rA0OzBcjkA7BhuWNsnC0k1mw/F9EdTC3qaFDIt2cuv5KSvHSPqQDIKeKt9kNQvqrVsz3S6dyBRSX
3pCs3ewU9y7DBhOSiFnlG4xMPAR4qOm97CQZ4fGTPzW9mY9t6WWBXEKM44mP8QiEonNthgAA9otx
u3gxXpxfLh/phHVlKN6+dvM8XcLShmr4EurrgQ==

`pragma protect key_keyowner="Atrenta", key_keyname="ATR-SG-RSA-1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=384)
`pragma protect key_block
C+TOkJ/qIw8cmFR4R9qAUb64QBa8p5XIE0cyD4KnTILybVNoHM0X7OqLMLryXmyu9JhW4tfEWAa5
PMKK9rReZDj80UGpf3UtCYmV/PyQchxKcmu6HtZrEzBQ3JvmR7u0B2xtVu+CTS418pOb+XnoIx2r
5xPq2BfrPyXdF0qn8Xf2EHEE9sy9AJ5ziySMJBip6atH3QxfJ/ZDDbxVh9aN2T5E5KwzXosZOgDx
fcKcDGpGw3+xsNxeIY3K7ppcg0T52kqENHuawa6Zvv7HaDoR0K/hVWMuj1cYtxyU3X+bUToHgirk
emGWOYKllVagv6O0/2c8qQMrsi9b7TqLP5MsXCaawELfw3XBLvVGqAGG1kP/NDiaQ5qvf7US2/j5
VudKUuE06mxUK8yTV/JarGsRaYFYePjcXzjAJfSK5s2rnH1/RmrSKYR4nFFnanyHm42QDaDB8C3X
LjNvtQWrzseaUU9yPnIniQFN927L+zHOHJ5cdXiO2XIOpIhEtNaTtmN+

`pragma protect key_keyowner="Cadence Design Systems.", key_keyname="CDS_RSA_KEY_VER_1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
Fv7WaVmRGMBscMdW3AIhtVWzNhO5tzTh1b11syxRsceYZDdnHATPx48/lj6kzL6cHYbDaLu8sEfy
9UDsBIbx3Ajgfn7BtePdtl0gGnoqeI3QrKcoRq9GwuRuzZspkS7s9kFyXOKlwKq7jXfyC+ujf/Bu
s9EAVSyuUMlBtvEDO3zOHyH7HB6awqe6RzuO0x96/ORmNIfRPZcGocuC+nfiEb6aOeh/nNe4MXVW
2AV0MiXthp9C+GZCuhUGevkpXD8pT5If6MzaE+KACNTcqB6NZHAWo2KxcqipOKEUeoQjouuB8nN0
yQrsPOeIP4FUECJHWkCvkK9Nc849yVVvEYkBYg==

`pragma protect key_keyowner="Synplicity", key_keyname="SYNP15_1", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
ejfeTUeQRg+buv2WuWTrhper7y+w2meqKlH62QbIpC6uOJnbx6rvZzBnKsNVtOvThxrrB1x0I9Zz
H/eMO52CMD0CkoCrgbRteg/GOjI2uUoVvfdhsqR/BalBj3ibkbrlwPbeIpSrXeQmPh4fOOCmna8L
mYyJHzv679nxspjB7VmcePJyODd/pPTNut/RdqIyfeqJWJ4E4xPyBPPxs3wvjbAKVDU2eX/Ed3kQ
IGvZlY+ArcRS778MUB3hWdIcYxwoMZ5KWrGUATZIzoPZy7PCBRXBSBe9ZoDkMGi42Q8CKIIaGyul
dFpk4ARWsgxhmiWFLB7tUk/qU4hvMToT5Hl9VQ==

`pragma protect key_keyowner="Mentor Graphics Corporation", key_keyname="MGC-PREC-RSA", key_method="rsa"
`pragma protect encoding = (enctype="BASE64", line_length=76, bytes=256)
`pragma protect key_block
J39yfTwp4JkyHkN2USc/YZ3ufnfrXEQqv9iJTaZsp2NMOSPDE0C8HItih84xnZli2Ypksvmm2SyY
fvK84x/qteezTBQfk/FGck2BY4+/DnDLroIlYNeRSgqeeI1ctO8q3l6+sI+fZ3nWH3+kqruCklox
lihoq+ArAirGG79WYGsG3j11hb4vFYg0SPk0YwYpO/I0OB9tt8hOAvaPRHFdcdCH2CzQLVi9BDg0
lGA9x7FwMgM5UfbsmIvFqPLHqRAM/pFeW2Rdzet6mbqIOnwlq731HFWmzVgb78Cua2hLIveEE3v3
CgUNASAHcHQi5alLlJg2DLSMpjpRVmXZ7ECjAw==

`pragma protect data_method = "AES128-CBC"
`pragma protect encoding = (enctype = "BASE64", line_length = 76, bytes = 108560)
`pragma protect data_block
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
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

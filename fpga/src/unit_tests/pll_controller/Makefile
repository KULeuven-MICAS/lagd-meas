# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Unit testbench for pll_controller (Pomelo PLL serial-config path).
#
# Usage (from this folder, or via the top Makefile / `make -C`):
#   make sim         # run the self-checking suite (console pass/fail)
#   make sim DUMP=1  # ... and dump a VCD into vivado-runs/
#   make wave        # shortcut for `make sim DUMP=1`
#   make clean       # remove vivado-runs/

SIM_TOP := tb_pll_controller

# pll_command_api.sv must be listed first: it holds the shared $unit
# typedefs/constants (the bitstream flow marks it IS_GLOBAL_INCLUDE; a single
# xvlog command keeps it in the same compilation unit for the simulation).
# '=' (deferred) so $(VERILOG_DIR) / $(CURDIR) resolve after common.mk runs.
SIM_SRCS = \
	$(VERILOG_DIR)/pll_command_api.sv \
	$(VERILOG_DIR)/fifo_to_axi_stream_adapter.sv \
	$(VERILOG_DIR)/pll_controller.sv \
	$(CURDIR)/pll_shift_model.sv \
	$(CURDIR)/tb_pll_controller.sv

include ../common.mk

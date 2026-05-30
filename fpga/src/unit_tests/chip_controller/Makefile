# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Unit testbench for chip_controller.
#
# Usage (from this folder, or via the top Makefile / `make -C`):
#   make sim         # run the self-checking suite (console pass/fail)
#   make sim DUMP=1  # ... and dump a VCD into vivado-runs/
#   make wave        # shortcut for `make sim DUMP=1`
#   make clean       # remove vivado-runs/

SIM_TOP := tb_chip_controller

# chip_command_api.sv must be listed first: it holds the shared $unit
# typedefs/enums (the bitstream flow marks it IS_GLOBAL_INCLUDE; a single xvlog
# command keeps it in the same compilation unit for the simulation).
# '=' (deferred) so $(VERILOG_DIR) / $(CURDIR) resolve after common.mk runs.
SIM_SRCS = \
	$(VERILOG_DIR)/chip_command_api.sv \
	$(VERILOG_DIR)/fifo_to_axi_stream_adapter.sv \
	$(VERILOG_DIR)/quad_spi_master.sv \
	$(VERILOG_DIR)/chip_controller.sv \
	$(CURDIR)/spi_slave_model.sv \
	$(CURDIR)/tb_chip_controller.sv

include ../common.mk

# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Common simulation rules for the unit testbenches (Xilinx xsim).
#
# A per-testbench Makefile sets SIM_TOP and SIM_SRCS, then includes this file:
#
#     SIM_TOP := tb_foo
#     SIM_SRCS = $(VERILOG_DIR)/foo.sv $(CURDIR)/tb_foo.sv   # use '=' (deferred)
#     include ../common.mk
#
# Targets:
#   sim   - compile + run, console pass/fail (add DUMP=1 to also write a VCD)
#   wave  - shortcut for `sim DUMP=1`
#   clean - remove the generated run directory
#
# All run artifacts (xvlog/xelab/xsim outputs and the optional VCD) are written
# to ./$(RUN_DIR)/ under the calling testbench folder.

# Locate this common.mk and the shared project RTL (../verilog).
COMMON_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VERILOG_DIR := $(abspath $(COMMON_DIR)/../verilog)

# Auto-generated simulation directory (per testbench).
RUN_DIR ?= vivado-runs
DUMP    ?= 0

ifeq ($(DUMP),1)
SIM_PLUSARGS += -testplusarg dump
endif

.PHONY: sim wave clean check-xsim

check-xsim: # Verify the Vivado simulator is on PATH
	@if ! which xvlog >/dev/null 2>&1; then \
		echo "ERROR: Vivado simulator (xvlog) not found on PATH. Source your Vivado settings first (e.g. 'source /path/to/Vivado/settings64.sh')."; \
		exit 1; \
	fi

sim: check-xsim # Compile and run the testbench (DUMP=1 to also write a VCD)
	@mkdir -p "$(RUN_DIR)"
	cd "$(RUN_DIR)" && \
	xvlog -sv $(SIM_SRCS) && \
	xelab -debug typical -timescale 1ns/1ps $(SIM_TOP) -s $(SIM_TOP)_snap && \
	xsim $(SIM_TOP)_snap $(SIM_PLUSARGS) -runall

wave: # Run the testbench with waveform dumping enabled
	@$(MAKE) sim DUMP=1

clean: # Remove the generated run directory
	rm -rf "$(RUN_DIR)"

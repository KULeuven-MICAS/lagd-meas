# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

SHELL := /bin/bash

export FPGA_ROOT ?= $(shell realpath ./)
export FPGA_OUTPUT_DIR ?= $(FPGA_ROOT)/output

export TEMPLATE_DIR ?= $(FPGA_ROOT)/xillinux_template
export COREBUNDLE_DIR ?= $(TEMPLATE_DIR)/corebundle-bv_testcore_2022
export XILLINUX_ZIP ?= $(TEMPLATE_DIR)/xillinux-eval-zedboard-2.0c.zip
export XILLINUX_DIR ?= $(FPGA_OUTPUT_DIR)/xillinux-eval-zedboard-2.0c
export LOGS_DIR ?= $(FPGA_OUTPUT_DIR)/logs
export LINKS_DIR ?= $(FPGA_OUTPUT_DIR)/bitstream
export IMPL_DIR ?= $(XILLINUX_DIR)/verilog/vivado/xillydemo.runs/impl_1
export SYNTH_DIR ?= $(XILLINUX_DIR)/verilog/vivado/xillydemo.runs/synth_1

export BITSTREAM_SRC ?= $(FPGA_ROOT)/scripts/build_batch.tcl
export OUTPUT_XPR ?= $(XILLINUX_DIR)/verilog/vivado/xillydemo.xpr

.PHONY: links check-vivado sim sim-clean

all: links bitstream

check-vivado: # Check if 'vivado' is available on the PATH
	@if ! which vivado >/dev/null 2>&1; then \
		echo "ERROR: 'vivado' not found on PATH. Please source your Vivado settings script first (e.g. 'source /path/to/Vivado/settings64.sh')."; \
		exit 1; \
	fi

links: $(XILLINUX_DIR)

links: # Create logs and links directories, and set up symlinks for logs and bitstream
	mkdir -p "$(LOGS_DIR)" "$(LINKS_DIR)"
	test -L "$(LOGS_DIR)/synth.log" || ln -s "$(SYNTH_DIR)/runme.log" "$(LOGS_DIR)/synth.log"
	test -L "$(LOGS_DIR)/impl.log" || ln -s "$(IMPL_DIR)/runme.log" "$(LOGS_DIR)/impl.log"
	test -L "$(LINKS_DIR)/xillydemo.bit" || ln -s "$(IMPL_DIR)/xillydemo.bit" "$(LINKS_DIR)/xillydemo.bit"

$(XILLINUX_DIR): $(XILLINUX_ZIP) # Unzip the Xillinux template if not already done, and copy the core files
	mkdir -p $(FPGA_OUTPUT_DIR)
	if [ -d "$(XILLINUX_DIR)" ]; then \
		echo "$(XILLINUX_DIR) already exists; skipping unzip"; \
	else \
		unzip -o $(XILLINUX_ZIP) -d $(FPGA_OUTPUT_DIR); \
	fi
	mkdir -p $(XILLINUX_DIR)/verilog/src $(XILLINUX_DIR)/cores
	cp "$(COREBUNDLE_DIR)/xillybus.v" "$(XILLINUX_DIR)/verilog/src/xillybus.v"
	cp "$(COREBUNDLE_DIR)/xillybus_core.v" "$(XILLINUX_DIR)/verilog/src/xillybus_core.v"
	cp "$(COREBUNDLE_DIR)/xillybus_core.ngc" "$(XILLINUX_DIR)/cores/xillybus_core.ngc"

bitstream: check-vivado $(BITSTREAM_SRC) # Generate the bitstream using Vivado in batch mode, and clean up intermediate files
	mkdir -p "$(LOGS_DIR)"
	cd "$(LOGS_DIR)" && \
	rm -f vivado*.jou vivado*.log && \
	vivado -mode batch -source $(BITSTREAM_SRC) \
		-tclargs "$(FPGA_ROOT)" \
		-log "bitstream.log" \
		-journal "bitstream.jou"
	@rm -f $(LOGS_DIR)/*.pb
	@echo "Bitstream generation ($(LINKS_DIR)/xillydemo.bit) completed at: $(shell date)"
	@echo "Synthesis log: $(LOGS_DIR)/synth.log"
	@echo "Implementation log: $(LOGS_DIR)/impl.log"

gui: check-vivado $(OUTPUT_XPR) # Open the Vivado GUI with the generated project
	cd "$(LOGS_DIR)" && \
	vivado -mode gui $(OUTPUT_XPR)

# ---- Unit-test simulation ----
# Each testbench has its own Makefile under src/unit_tests/<tb>/ that includes
# src/unit_tests/common.mk. Pick one with TB=<name> (default: chip_controller).
TB ?= chip_controller

sim: # Run a unit-test simulation (TB=<name>; add DUMP=1 for a VCD)
	$(MAKE) -C src/unit_tests/$(TB) sim

sim-clean: # Remove a unit-test's generated run directory
	$(MAKE) -C src/unit_tests/$(TB) clean

clean:
	rm -rf "$(XILLINUX_DIR)" "$(LOGS_DIR)" "$(LINKS_DIR)"
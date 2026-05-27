# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

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

.PHONY: links

all: links bitstream

links: $(XILLINUX_DIR)

links:
	mkdir -p "$(LOGS_DIR)" "$(LINKS_DIR)"
	test -L "$(LOGS_DIR)/synth.log" || ln -s "$(SYNTH_DIR)/runme.log" "$(LOGS_DIR)/synth.log"
	test -L "$(LOGS_DIR)/impl.log" || ln -s "$(IMPL_DIR)/runme.log" "$(LOGS_DIR)/impl.log"
	test -L "$(LINKS_DIR)/xillydemo.bit" || ln -s "$(IMPL_DIR)/xillydemo.bit" "$(LINKS_DIR)/xillydemo.bit"

$(XILLINUX_DIR): $(XILLINUX_ZIP)
	mkdir -p $(FPGA_OUTPUT_DIR)
	unzip -o $(XILLINUX_ZIP) -d $(FPGA_OUTPUT_DIR)
	mkdir -p $(XILLINUX_DIR)/verilog/src $(XILLINUX_DIR)/cores
	cp "$(COREBUNDLE_DIR)/xillybus.v" "$(XILLINUX_DIR)/verilog/src/xillybus.v"
	cp "$(COREBUNDLE_DIR)/xillybus_core.v" "$(XILLINUX_DIR)/verilog/src/xillybus_core.v"
	cp "$(COREBUNDLE_DIR)/xillybus_core.ngc" "$(XILLINUX_DIR)/cores/xillybus_core.ngc"

bitstream: $(BITSTREAM_SRC)
	vivado -mode batch -source $(BITSTREAM_SRC) \
		-tclargs "$(FPGA_ROOT)" \
		-log "$(LOGS_DIR)/bitstream.log" \
		-journal "$(LOGS_DIR)/bitstream.jou"
	echo "Bitstream generation ($(LINKS_DIR)/xillydemo.bit) completed at: $(shell date)""
	echo "Synthesis log: $(LOGS_DIR)/synth.log"
	echo "Implementation log: $(LOGS_DIR)/impl.log"

clean:
	rm -rf "$(XILLINUX_DIR)" "$(LOGS_DIR)" "$(LINKS_DIR)"
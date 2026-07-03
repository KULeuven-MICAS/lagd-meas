# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Inspired from HeMAiA/target/fpga/jtag/openocd_configs/hemaia.cfg, HeMAiA repository [commit: 6a9dfa2]
# and cheshire/util/openocd.hs2.tcl, Cheshire repository [commit: 55650af]

adapter driver ftdi
# adapter speed 12000 # 12MHz
adapter speed 100 # 100kHz for first bring-up
transport select jtag

# FT4232
ftdi vid_pid 0x0403 0x6011
ftdi layout_init 0x0088 0x000b
ftdi channel 0
set irlen 5

source [file dirname [info script]]/openocd.common.tcl

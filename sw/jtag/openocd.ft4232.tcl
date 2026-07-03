# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Inspired from HeMAiA/target/fpga/jtag/openocd_configs/hemaia.cfg, HeMAiA repository [commit: 6a9dfa2]
# and cheshire/util/openocd.hs2.tcl, Cheshire repository [commit: 55650af]
#
# ADAPTER config only: the on-board FT4232H, channel A (ADBUS) = JTAG.
# Defines NO target -- source openocd.common.tcl after this for the tap/target.
# Entry points that use it: openocd.run.tcl (batch load & run), openocd.server.tcl
# (interactive GDB server).
#
# Speed defaults to 100 kHz (safe for bring-up). Override before sourcing, e.g.:
#   openocd -c "set ADAPTER_KHZ 4000" -f ...

adapter driver ftdi
transport select jtag

if {![info exists ADAPTER_KHZ]} { set ADAPTER_KHZ 100 }
adapter speed $ADAPTER_KHZ

# FT4232H: default USB PID; JTAG on channel 0 (ADBUS); standard MPSSE pinout
# (TCK=AD0, TDI=AD1, TDO=AD2, TMS=AD3). AD4-7 unconnected.
ftdi vid_pid 0x0403 0x6011
ftdi channel 0
ftdi layout_init 0x0088 0x000b

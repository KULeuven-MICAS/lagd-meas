# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Minimal JTAG bring-up probe: read and print the TAP IDCODE, then exit.
# Decoupled from the debug module / target so it works even if the core clock
# is off or the hart can't be halted yet. Expected IDCODE: 0x1c5e5db3.
#
#   openocd -f openocd.scan.tcl
#
# Look for:  "tap/device found: 0x1c5e5db3"

adapter driver ftdi
adapter speed 100
transport select jtag

ftdi vid_pid 0x0403 0x6011
ftdi channel 0
ftdi layout_init 0x0088 0x000b

# No -expected-id on purpose: report whatever is on the chain without aborting,
# so a mismatch still prints the value instead of erroring out.
jtag newtap riscv cpu -irlen 5

init
scan_chain
shutdown

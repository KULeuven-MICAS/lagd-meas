# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Interactive OpenOCD server for the LAGD / Cheshire chip: bring up the adapter and
# target, halt the hart, and keep running so you can attach GDB / telnet / tcl.
# (This reproduces the previous openocd.ft4232.tcl behaviour after the split.)
#
#   openocd -f openocd.server.tcl
#   # then, in another terminal:  riscv64-unknown-elf-gdb ... -ex "target extended-remote :3333"
#
# GDB on :3333, telnet on :4444, tcl on :6666 (OpenOCD defaults).

set HERE [file dirname [info script]]
source [file join $HERE openocd.ft4232.tcl]
source [file join $HERE openocd.common.tcl]

# End the session when the debugger detaches.
$_TARGETNAME configure -event gdb-detach {
    echo "GDB detached; ending debugging session."
    shutdown
}

init
halt
echo "Ready for Remote Connections."

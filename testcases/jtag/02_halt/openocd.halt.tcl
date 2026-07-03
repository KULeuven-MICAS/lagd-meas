# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# JTAG halt test: examine the debug module, halt the hart, and read a few CSRs.
# This is the step that also requires the CHIP CORE CLOCK to be running.
# Expected IDCODE: 0x1c5e5db3.
#
#   openocd -f openocd.halt.tcl
#
# PASS prints "PASS: hart halted" followed by mhartid / misa / pc.

adapter driver ftdi
adapter speed 100
transport select jtag

ftdi vid_pid 0x0403 0x6011
ftdi channel 0
ftdi layout_init 0x0088 0x000b

reset_config none

set _CHIPNAME riscv
# This time we DO assert -expected-id, so a wrong IDCODE fails here too.
jtag newtap $_CHIPNAME cpu -irlen 5 -expected-id 0x1c5e5db3

set _TARGETNAME $_CHIPNAME.cpu
target create $_TARGETNAME riscv -chain-position $_TARGETNAME -coreid 0

# Keep timeouts short so bring-up fails fast (raise later for normal use).
riscv set_command_timeout_sec 10
riscv set_reset_timeout_sec 10
riscv set_prefer_sba off

proc fail_clock {stage err} {
    echo "=================================================================="
    echo "FAIL ($stage): $err"
    echo ""
    echo "  The JTAG link itself is fine if 01_idcode passed. This failure is"
    echo "  the debug module / hart, and the usual cause is that the CHIP CORE"
    echo "  CLOCK is not running: examine and halt happen in the core clock"
    echo "  domain, so with no clock the DMI/abstract commands time out."
    echo ""
    echo "  -> Provide a clock to the chip (external clk pad and/or PLL"
    echo "     configured, clk_sel set) BEFORE halting via JTAG."
    echo "=================================================================="
    shutdown error
}

if {[catch {init} err]}  { fail_clock "init/examine" $err }
if {[catch {halt} err]}  { fail_clock "halt" $err }

set state [$_TARGETNAME curstate]
if {$state ne "halted"} {
    echo "FAIL: unexpected target state after halt: $state"
    shutdown error
}

echo "=================================================================="
echo "PASS: hart halted (debug module reachable, core clock running)."
echo "--- register readout (proves debug abstract/register access) ---"
reg mhartid
reg misa
reg pc
echo "=================================================================="

shutdown

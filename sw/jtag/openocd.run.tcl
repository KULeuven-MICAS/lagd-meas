# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# JTAG load-and-run flow for the LAGD / Cheshire chip: halt, load an ELF, resume at
# its entry, then wait for completion by polling the end-of-computation (EOC) scratch
# register. This is the primary "run a program on the chip over JTAG" tool.
#
# Prefer the shell wrapper:   ./run_elf.sh <file.elf>
# Or invoke directly:         openocd -c "set ELF /abs/path/app.spm.elf" -f openocd.run.tcl
#
# Parameters (override with -c "set NAME value" before -f):
#   ELF          required : path to the ELF to load
#   ENTRY        0x80000000: PC to start at (all *.spm.elf link here)
#   EOC_ADDR     0x03000008: regs.SCRATCH_2 (bit0 = done, bits[31:1] = return code)
#   RUN_TIMEOUT  30         : seconds to wait for EOC
#   ADAPTER_KHZ  100        : JTAG clock (see openocd.ft4232.tcl)

set HERE [file dirname [info script]]
source [file join $HERE openocd.ft4232.tcl]
source [file join $HERE openocd.common.tcl]

if {![info exists ELF]} {
    echo "ERROR: no ELF specified."
    echo "  use the wrapper:  ./run_elf.sh <file.elf>"
    echo "  or:               openocd -c \"set ELF /abs/path/app.elf\" -f openocd.run.tcl"
    shutdown error
}
if {![info exists ENTRY]}       { set ENTRY 0x80000000 }
if {![info exists EOC_ADDR]}    { set EOC_ADDR 0x03000008 }
if {![info exists RUN_TIMEOUT]} { set RUN_TIMEOUT 30 }

# Batch run: no lingering servers.
gdb_port disabled
telnet_port disabled
tcl_port disabled

# Use the debug module's system bus for memory: matches the sim VIP, and lets us poll
# the EOC register while the core RUNS without halting it. If SBA misbehaves on the
# bench, set this 'off' (progbuf) -- polling then halts the core briefly each read.
riscv set_prefer_sba on

proc bail {msg err} {
    echo "=================================================================="
    echo "FAIL ($msg): $err"
    echo "=================================================================="
    shutdown error
}

if {[catch {init} err]} { bail "init/examine -- core clock running? (see testcases/jtag/02_halt)" $err }
if {[catch {halt} err]} { bail "halt -- core clock running? (see testcases/jtag/02_halt)" $err }

echo "Loading ELF : $ELF"
if {[catch {load_image $ELF} err]} { bail "load_image" $err }
echo "Entry point : $ENTRY"

# Clear EOC scratch so a stale value from a previous run isn't read as 'done'.
mww $EOC_ADDR 0

echo "Resuming    : at $ENTRY"
if {[catch {resume $ENTRY} err]} { bail "resume" $err }

echo "Waiting     : poll $EOC_ADDR (timeout ${RUN_TIMEOUT}s) ..."
set found 0
set eoc 0
set deadline [expr {[clock seconds] + $RUN_TIMEOUT}]
while {[clock seconds] < $deadline} {
    set eoc [lindex [read_memory $EOC_ADDR 32 1] 0]
    if {$eoc & 1} { set found 1; break }
    sleep 50
}

catch {halt}

if {!$found} {
    echo "=================================================================="
    echo "FAIL: timed out after ${RUN_TIMEOUT}s waiting for EOC."
    echo "  bit0 of $EOC_ADDR never set. Possible causes:"
    echo "  - program trapped/crashed before reaching _exit"
    echo "  - wrong ENTRY ($ENTRY) or ELF not placed where expected"
    echo "  - SBA memory access not working (try 'riscv set_prefer_sba off')"
    echo "=================================================================="
    shutdown error
}

set code [expr {$eoc >> 1}]
echo "=================================================================="
if {$code == 0} {
    echo "PASS: program finished, return code 0."
    echo "=================================================================="
    shutdown
} else {
    echo "FAIL: program returned non-zero code $code (raw EOC = [format 0x%08x $eoc])."
    echo "=================================================================="
    shutdown error
}

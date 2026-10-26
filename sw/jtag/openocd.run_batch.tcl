# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
# Load and run every ELF listed in ELF_LIST_FILE while keeping one OpenOCD and
# FTDI/JTAG session alive.  The manifest contains one absolute ELF path per line.

set HERE [file dirname [info script]]
source [file join $HERE openocd.ft4232.tcl]
source [file join $HERE openocd.common.tcl]

if {![info exists ELF_LIST_FILE]} {
    echo "ERROR: no ELF_LIST_FILE specified."
    shutdown error
}
if {![info exists ENTRY]}       { set ENTRY 0x80000000 }
if {![info exists EOC_ADDR]}    { set EOC_ADDR 0x03000008 }
if {![info exists RUN_TIMEOUT]} { set RUN_TIMEOUT 30 }

gdb port disabled
telnet port disabled
tcl port disabled

# Poll EOC through the system bus while the core is running.
riscv set_mem_access sysbus progbuf

proc batch_bail {run_index elf msg err} {
    catch {halt}
    echo "\[batch\] RUN_ERROR $run_index $elf 1"
    echo "=================================================================="
    echo "FAIL ($msg): $err"
    echo "=================================================================="
    shutdown error
}

if {[catch {set manifest [open $ELF_LIST_FILE r]} err]} {
    echo "ERROR: cannot open ELF manifest $ELF_LIST_FILE: $err"
    shutdown error
}
set manifest_data [read $manifest]
close $manifest

set ELFS {}
foreach line [split $manifest_data "\n"] {
    set elf [string trimright $line "\r"]
    if {$elf ne ""} { lappend ELFS $elf }
}
if {[llength $ELFS] == 0} {
    echo "ERROR: ELF manifest is empty: $ELF_LIST_FILE"
    shutdown error
}

if {[catch {init} err]} {
    echo "ERROR: init/examine failed -- core clock running? $err"
    shutdown error
}

set run_index 0
foreach elf $ELFS {
    echo "\[batch\] RUN_START $run_index $elf"

    if {![file exists $elf]} {
        batch_bail $run_index $elf "ELF not found" $elf
    }
    if {[catch {halt} err]} {
        batch_bail $run_index $elf "halt -- core clock running?" $err
    }

    echo "Loading ELF : $elf"
    if {[catch {load_image $elf} err]} {
        batch_bail $run_index $elf "load_image" $err
    }
    echo "Entry point : $ENTRY"

    # Prevent a completed previous run from satisfying this run's EOC poll.
    if {[catch {mww $EOC_ADDR 0} err]} {
        batch_bail $run_index $elf "clear EOC" $err
    }

    echo "Resuming    : at $ENTRY"
    if {[catch {resume $ENTRY} err]} {
        batch_bail $run_index $elf "resume" $err
    }

    echo "Waiting     : poll $EOC_ADDR (timeout ${RUN_TIMEOUT}s) ..."
    set found 0
    set eoc 0
    set deadline [expr {[clock seconds] + $RUN_TIMEOUT}]
    while {[clock seconds] < $deadline} {
        if {[catch {set eoc [lindex [read_memory $EOC_ADDR 32 1 phys] 0]} err]} {
            batch_bail $run_index $elf "poll EOC via physical SBA" $err
        }
        if {$eoc & 1} { set found 1; break }
        sleep 50
    }

    catch {halt}
    if {!$found} {
        batch_bail $run_index $elf \
            "timed out waiting for EOC" \
            "bit0 of $EOC_ADDR did not set within ${RUN_TIMEOUT}s"
    }

    # EOC is observed through JTAG, independently of the UART console.  Give
    # bytes already in flight time to reach the Python console reader before
    # emitting the boundary marker for this run.
    sleep 250

    set code [expr {$eoc >> 1}]
    if {$code != 0} {
        batch_bail $run_index $elf \
            "program returned non-zero" \
            "return code $code (raw EOC = [format 0x%08x $eoc])"
    }

    echo "PASS: program finished, return code 0."
    echo "\[batch\] RUN_END $run_index $elf 0"
    incr run_index
}

shutdown

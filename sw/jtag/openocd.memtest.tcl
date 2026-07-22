# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# JTAG memory integrity + volume test: write several patterns over a memory region via
# the debug system bus, read each back, and compare. Catches stuck bits, addressing
# errors, and (at larger sizes) stresses sustained transfer.
#
#   openocd -f openocd.memtest.tcl
#   openocd -c "set MEM_WORDS 8192" -f openocd.memtest.tcl   # larger / more stress
#
# Parameters (override with -c "set NAME value" before -f):
#   MEM_BASE   0x80000000 : region base (L2 SPM)
#   MEM_WORDS  2048        : region size in 32-bit words (2048 = 8 KiB)
#   SEED       0xC0FFEE    : PRNG seed (reproducible)
#   ADAPTER_KHZ 100        : JTAG clock -- raise it (after 01_idcode) for a faster test

set HERE [file dirname [info script]]
source [file join $HERE openocd.ft4232.tcl]
source [file join $HERE openocd.common.tcl]

if {![info exists MEM_BASE]}  { set MEM_BASE 0x80000000 }
if {![info exists MEM_WORDS]} { set MEM_WORDS 2048 }
if {![info exists SEED]}      { set SEED 12648430 }

gdb_port disabled
telnet_port disabled
tcl_port disabled
riscv set_mem_access sysbus progbuf

proc bail {msg err} {
    echo "=================================================================="
    echo "FAIL ($msg): $err"
    echo "=================================================================="
    shutdown error
}

if {[catch {init} err]} { bail "init/examine -- core clock running? (see testcases/jtag/02_halt)" $err }
if {[catch {halt} err]} { bail "halt -- core clock running? (see testcases/jtag/02_halt)" $err }

# Generate a list of MEM_WORDS 32-bit values for the named pattern (decimal ints).
proc gen {kind words base seed} {
    set out {}
    switch -- $kind {
        zero { for {set i 0} {$i < $words} {incr i} { lappend out 0 } }
        ones { for {set i 0} {$i < $words} {incr i} { lappend out 4294967295 } }
        alt  { for {set i 0} {$i < $words} {incr i} {
                   lappend out [expr {($i & 1) ? 2863311530 : 1431655765}] } }
        addr { for {set i 0} {$i < $words} {incr i} {
                   lappend out [expr {($base + $i * 4) & 0xffffffff}] } }
        rand { set x $seed
               for {set i 0} {$i < $words} {incr i} {
                   set x [expr {(1103515245 * $x + 12345) & 0x7fffffff}]
                   lappend out $x } }
    }
    return $out
}

proc runpat {name kind} {
    global MEM_BASE MEM_WORDS SEED
    set data [gen $kind $MEM_WORDS $MEM_BASE $SEED]
    if {[catch {write_memory $MEM_BASE 32 $data} err]}          { bail "write ($name)" $err }
    if {[catch {set rb [read_memory $MEM_BASE 32 $MEM_WORDS]} err]} { bail "read ($name)" $err }
    for {set i 0} {$i < $MEM_WORDS} {incr i} {
        if {[lindex $data $i] != [lindex $rb $i]} {
            set a [expr {$MEM_BASE + $i * 4}]
            echo [format "FAIL: memtest '%s' MISMATCH at 0x%08x: wrote 0x%08x read 0x%08x" \
                  $name $a [lindex $data $i] [lindex $rb $i]]
            shutdown error
        }
    }
    echo [format "  \[%-12s\] OK  (%d words)" $name $MEM_WORDS]
}

echo [format "Memtest: 0x%08x .. 0x%08x  (%d words / %d bytes)" \
      $MEM_BASE [expr {$MEM_BASE + $MEM_WORDS * 4}] $MEM_WORDS [expr {$MEM_WORDS * 4}]]
runpat "0x00000000"   zero
runpat "0xffffffff"   ones
runpat "0x55/0xAA"    alt
runpat "addr-as-data" addr
runpat "random"       rand

echo "=================================================================="
echo [format "PASS: memtest OK over %d bytes at 0x%08x." [expr {$MEM_WORDS * 4}] $MEM_BASE]
echo "=================================================================="
shutdown

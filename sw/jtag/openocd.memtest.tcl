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
#   MEM_ACCESS sysbus      : access method(s), in preference order (see below)
#   DEBUG_LEVEL 2          : OpenOCD verbosity; 3 traces every memory access
#
# WHY THIS TEST MUST USE THE SYSTEM BUS
#
# OpenOCD can reach memory two ways, and only one of them tests memory:
#   - sysbus  : the debug module's own AXI master (SBA). Debug module -> AXI -> SRAM.
#               The core is not involved and its D$ is not in the path.
#   - progbuf : the halted hart is made to execute ld/sd on the debugger's behalf.
#               That goes through CVA6's write-back L1 D$, which can absorb the whole
#               region (32 KiB, 8-way) and answer the read-back from cache -- so a
#               broken SRAM cell at a cacheable address would still PASS.
# Everything from 0x8000_0000 up is a CVA6 cacheable region in this design
# (cheshire_pkg::gen_cva6_cfg -> CachedRegionAddrBase, LlcOutRegionStart = 0x8000_0000),
# so progbuf here is NOT a valid memory test. MEM_ACCESS therefore defaults to `sysbus`
# ALONE: with no fallback, a PASS proves the transfers went over the debug system bus.
# Pass `-c "set MEM_ACCESS {sysbus progbuf}"` to re-enable the CPU fallback, but then
# read the "Access" line below to see what was actually permitted.

set HERE [file dirname [info script]]
source [file join $HERE openocd.ft4232.tcl]
source [file join $HERE openocd.common.tcl]

if {![info exists MEM_BASE]}    { set MEM_BASE 0x80000000 }
if {![info exists MEM_WORDS]}   { set MEM_WORDS 2048 }
if {![info exists SEED]}        { set SEED 12648430 }
if {![info exists MEM_ACCESS]}  { set MEM_ACCESS sysbus }
if {![info exists DEBUG_LEVEL]} { set DEBUG_LEVEL 2 }

gdb_port disabled
telnet_port disabled
tcl_port disabled

# Set verbosity before init so the examine/DMI traffic is traced too at level 3.
debug_level $DEBUG_LEVEL
# `eval` (rather than {*}) so the list expands on older jimtcl builds too.
eval riscv set_mem_access $MEM_ACCESS

proc bail {msg err} {
    echo "=================================================================="
    echo "FAIL ($msg): $err"
    echo "=================================================================="
    shutdown error
}

# Read sbcs, the debug module's System Bus Access control/status register (DMI 0x38),
# and report whether SBA actually exists in hardware. sbasize == 0 means the debug
# module has NO system bus master, so OpenOCD could only ever reach memory through the
# CPU -- exactly the case this test must not silently degrade into.
# Field layout (RISC-V debug spec 0.13.2 / 1.0, sbcs):
#   31:29 sbversion   14:12 sberror   11:5 sbasize   4:0 sbaccess128/64/32/16/8
proc report_sba {} {
    set sbcs ""
    foreach cmd {dmi_read dm_read} {
        if {![catch {riscv $cmd 0x38} val]} { set sbcs $val; break }
    }
    if {$sbcs eq ""} {
        echo "SBA probe: this OpenOCD has no 'riscv dmi_read'/'dm_read' -- cannot read sbcs."
        echo "           Confirm the access method empirically instead:"
        echo "             ./run.sh -c \"set DEBUG_LEVEL 3\" 2>&1 | grep -c bus_v1"
        return
    }
    # Normalise: dmi_read may return "0x20040404" or a decimal string.
    if {[catch {set sbcs [expr {$sbcs + 0}]}]} {
        echo "SBA probe: could not parse sbcs value '$sbcs'."
        return
    }
    set sbversion [expr {($sbcs >> 29) & 0x7}]
    set sberror   [expr {($sbcs >> 12) & 0x7}]
    set sbasize   [expr {($sbcs >> 5)  & 0x7f}]
    set sizes {}
    foreach {bit width} {0 8 1 16 2 32 3 64 4 128} {
        if {($sbcs >> $bit) & 1} { lappend sizes $width }
    }
    echo [format "SBA probe: sbcs=0x%08x  sbversion=%d  sbasize=%d bit  sbaccess=%s bit  sberror=%d" \
          $sbcs $sbversion $sbasize [join $sizes /] $sberror]
    if {$sbasize == 0} {
        bail "SBA" "sbasize=0 -- the debug module has no system bus master, so memory\
                    could only be reached through the CPU (progbuf) and its D\$. This is\
                    not a valid memory test; fix the debug module before trusting it."
    }
}

if {[catch {init} err]} { bail "init/examine -- core clock running? (see testcases/jtag/02_halt)" $err }
if {[catch {halt} err]} { bail "halt -- core clock running? (see testcases/jtag/02_halt)" $err }

echo [format "Access   : %s   (debug_level %d)" $MEM_ACCESS $DEBUG_LEVEL]
report_sba

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

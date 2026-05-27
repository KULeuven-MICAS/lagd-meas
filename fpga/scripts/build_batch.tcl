# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# The source script is from Robin Geens
#
# Self-contained Vivado batch script: project setup + synth + impl + bitstream.
# your_dir is passed in by build.sh via: vivado -tclargs <path>
#

set your_dir [lindex $argv 0]
set xillinux   "$your_dir/output/xillinux-eval-zedboard-2.0c"
set origin_dir "$xillinux/verilog"
set ess_dir    "$xillinux/vivado-essentials"
set thepart    "xc7z020clg484-1"

if {[string first { } $your_dir] >= 0} {
    error "Path contains spaces: $your_dir"
}

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
create_project -force xillydemo "$origin_dir/vivado/"

set obj [get_projects xillydemo]
set_property default_lib         xil_defaultlib $obj
set_property part                $thepart       $obj
set_property simulator_language  Mixed          $obj
set_property source_mgmt_mode    DisplayOnly    $obj
set_property target_language     Verilog        $obj
set_property ip_repo_paths       "$ess_dir/vivado-ip" [current_fileset]
update_ip_catalog

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
if {[string equal [get_filesets sources_1] ""]} { create_fileset -srcset sources_1 }
set obj [get_filesets sources_1]
set_property edif_extra_search_paths "$xillinux/cores" $obj
set_property top xillydemo $obj

# Standard xillinux files (smbus, audio, xillybus; xillydemo.v replaced by ours)
add_files -norecurse -fileset $obj [list \
    $origin_dir/src/smbus.v \
    $origin_dir/src/i2s_audio.v \
    $origin_dir/src/xillybus.v \
    $origin_dir/src/xillybus_core.v \
    $ess_dir/system.v \
    $ess_dir/vga_fifo/vga_fifo.xci \
    $ess_dir/fifo_8x2048/fifo_8x2048.xci \
    $ess_dir/fifo_32x512/fifo_32x512.xci \
    $ess_dir/vivado_system/vivado_system.bd \
]

# Our RTL sources
foreach f [glob         $your_dir/src/verilog/*.v ] { add_files -norecurse -fileset $obj $f }
foreach f [glob -nocomplain $your_dir/src/verilog/*.sv] { add_files -norecurse -fileset $obj $f }

# Our Vivado IP
foreach f [glob $your_dir/src/vivado_ip/*/*.xci] { add_files -norecurse -fileset $obj $f }

upgrade_ip [get_ips]

# AXI wiring in block design
open_bd_design $ess_dir/vivado_system/vivado_system.bd
startgroup
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/processing_system7_0/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins xillybus_ip_0/S_AXI]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/processing_system7_0/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins xillyvga_0/S_AXI]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/processing_system7_0/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins xillybus_lite_0/S_AXI]
set_property range  4K [get_bd_addr_segs {processing_system7_0/Data/SEG_xillybus_ip_0_reg0}]
set_property range  4K [get_bd_addr_segs {processing_system7_0/Data/SEG_xillyvga_0_reg0}]
set_property range  4K [get_bd_addr_segs {processing_system7_0/Data/SEG_xillybus_lite_0_reg0}]
set_property offset 0x50000000 [get_bd_addr_segs {processing_system7_0/Data/SEG_xillybus_ip_0_reg0}]
set_property offset 0x50001000 [get_bd_addr_segs {processing_system7_0/Data/SEG_xillyvga_0_reg0}]
set_property offset 0x50002000 [get_bd_addr_segs {processing_system7_0/Data/SEG_xillybus_lite_0_reg0}]
endgroup
save_bd_design
close_bd_design vivado_system

# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------
if {[string equal [get_filesets constrs_1] ""]} { create_fileset -constrset constrs_1 }
add_files -fileset constrs_1 -norecurse "$your_dir/src/constraints/xillydemo.xdc"

# ---------------------------------------------------------------------------
# Sim fileset (empty)
# ---------------------------------------------------------------------------
if {[string equal [get_filesets sim_1] ""]} { create_fileset -simset sim_1 }
set_property top                   unknown  [get_filesets sim_1]
set_property xsim.simulate.runtime "1000 ns" [get_filesets sim_1]

# ---------------------------------------------------------------------------
# Synth / impl runs
# ---------------------------------------------------------------------------
if {[string equal [get_runs synth_1] ""]} {
    create_run -name synth_1 -part $thepart \
        -flow {Vivado Synthesis 2013} \
        -strategy "Vivado Synthesis Defaults" \
        -constrset constrs_1
}
set_property part $thepart [get_runs synth_1]

if {[string equal [get_runs impl_1] ""]} {
    create_run -name impl_1 -part $thepart \
        -flow {Vivado Implementation 2013} \
        -strategy "Vivado Implementation Defaults" \
        -constrset constrs_1 -parent_run synth_1
}
set_property part $thepart [get_runs impl_1]

# Suppress known-OK warnings (verbatim from original xillydemo-vivado.tcl)
set_msg_config -new_severity INFO -id {BD 41-968}       -string {{xillybus_S_AXI} }
set_msg_config -new_severity INFO -id {BD 41-968}       -string {{xillybus_M_AXI} }
set_msg_config -new_severity INFO -id {BD 41-967}       -string {{xillybus_ip_0/xillybus_M_AXI} }
set_msg_config -new_severity INFO -id {BD 41-967}       -string {{xillybus_ip_0/xillybus_S_AXI} }
set_msg_config -new_severity INFO -id {BD 41-678}       -string {{xillybus_S_AXI/Reg} }
set_msg_config -new_severity INFO -id {BD 41-1356}      -string {{xillybus_S_AXI/Reg} }
set_msg_config -new_severity INFO -id {BD 41-759}       -string {{xlconcat_0/In} }
set_msg_config -new_severity INFO -id {filemgmt 20-1440} -string {{xillybus_lite.ngc} }
set_msg_config -new_severity INFO -id {Netlist 29-160}  -string {{vivado_system_processing_system7} }

# ---------------------------------------------------------------------------
# Global includes
# ---------------------------------------------------------------------------
set_property IS_GLOBAL_INCLUDE 1 [get_files $your_dir/src/verilog/register_and_macros_xilinx.sv]
set_property IS_GLOBAL_INCLUDE 1 [get_files $your_dir/src/verilog/perip_command_api.sv]
set_property IS_GLOBAL_INCLUDE 1 [get_files $your_dir/src/verilog/chip_command_api.sv]

# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------
puts "=== Starting synthesis ==="
reset_run synth_1
launch_runs synth_1 -jobs 8
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
    error "Synthesis failed — check synth_1/runme.log"
}

# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------
puts "=== Starting implementation ==="
reset_run impl_1
launch_runs impl_1 -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {
    error "Implementation failed — check impl_1/runme.log"
}

# ---------------------------------------------------------------------------
# Bitstream
# ---------------------------------------------------------------------------
puts "=== Generating bitstream ==="

# PS_GPIO[24:29] are processor native pads intentionally detached from PL logic —
# no IOSTANDARD/LOC by design. Apply the waiver as a pre-hook so it runs inside
# the write_bitstream subprocess (set_property here would not propagate there).
set_property STEPS.WRITE_BITSTREAM.TCL.PRE \
    "$your_dir/scripts/drc_waiver.tcl" [get_runs impl_1]

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {
    error "Bitstream generation failed — check impl_1/runme.log"
}

puts "=== Done: $origin_dir/vivado/xillydemo.runs/impl_1/xillydemo.bit ==="

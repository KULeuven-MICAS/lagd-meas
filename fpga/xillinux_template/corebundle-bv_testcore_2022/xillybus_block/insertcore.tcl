# add_ip_repo: Add a path to IP repository if it's not there already

proc add_ip_repo {path} {
    set old [get_property ip_repo_paths [current_fileset]]

    foreach r $old {
	if [string equal $r $path] {
	    return;
	}
    }
    set_property ip_repo_paths [linsert $old end $path] [current_fileset]
    update_ip_catalog
}

########################

set origin_dir [file dirname [info script]]
set corename bv_testcore_2022
set iszynq 1

if $iszynq {
    set blockpath {blockdesign/}

    set connect_ifs { S_AXI m_axi \
			  from_host_audio from_host_smb \
			  to_host_audio to_host_smb }

    set connect_nets { GPIO_LED ap_clk bus_clk bus_rst_n from_host_smb_open \
			   host_interrupt quiesce }
} else {
    set blockpath {}
    set connect_ifs {}
    set connect_nets { GPIO_LED PCIE_PERST_B_LS PCIE_REFCLK_N PCIE_REFCLK_P \
			   PCIE_RX_N PCIE_RX_P PCIE_TX_N PCIE_TX_P }
}

add_ip_repo $origin_dir

# Remove previous Xillybus IP if present
if [catch {set delete_ip [get_bd_cells -hier -filter path=~/${blockpath}xillybus_*]}] {
    send_msg_id xillybuscore-1 error "Please open the block design before running this script"
    return -code error
}

if [llength $delete_ip] {
    delete_bd_objs $delete_ip
}

# Add new Xillybus IP
create_bd_cell -type ip -vlnv [get_ipdefs *:xillybus_${corename}:*] ${blockpath}xillybus_$corename

# Upgrade IP if required
upgrade_bd_cells [get_bd_cells -hier -filter path=~/${blockpath}xillybus_*]

# And now connect pins as applicable. If some fail, just go on

foreach n $connect_ifs {
    set p [get_bd_intf_pins ${blockpath}xillybus_${corename}/$n]
    if { [llength $p] == 0 } { continue }

    catch {connect_bd_intf_net [get_bd_intf_pins ${blockpath}$n] $p }
}

foreach n $connect_nets {
    set p [get_bd_pins ${blockpath}xillybus_${corename}/$n]
    if { [llength $p] == 0 } { continue }

    catch {connect_bd_net [get_bd_pins ${blockpath}$n] $p }
}

if $iszynq {
    assign_bd_address [get_bd_addr_segs "${blockpath}${corename}*"]
    set_property range 4K [get_bd_addr_segs "processing_system7_0/Data/SEG_xillybus_${corename}*"]
    set_property offset 0x50000000 [get_bd_addr_segs "processing_system7_0/Data/SEG_xillybus_${corename}*"]

    regenerate_bd_layout -hierarchy [get_bd_cells /blockdesign]

} else {
    connect_bd_net [get_bd_pins stream_clk_gen/clk_in1] [get_bd_pins xillybus_${corename}/bus_clk]
    connect_bd_net [get_bd_pins stream_clk_gen/clk_out1] [get_bd_pins xillybus_${corename}/ap_clk]
    connect_bd_net [get_bd_pins stream_clk_gen/reset] [get_bd_pins xillybus_${corename}/quiesce]

    regenerate_bd_layout
}

reset_run [get_runs synth*]

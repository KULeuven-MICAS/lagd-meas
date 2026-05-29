#!/usr/bin/env python
# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Higher level functions for PCB supply control

from lib.Bcolors import Bcolors
from lib.WritePort import WritePort
from lib.ReadPort import ReadPort
import lib.perip_ISA as instructions
import lib.commands_DAC5724 as dacc
import time

def startup_afe_vdd_to_nominal(dacc, writePort, readPort):
    cm = get_channel_map()
    afe_vdd_list = ["afe_vddrxd", "afe_vddrxd2", "afe_vddrxa", "afe_vddrxa2", "afe_vddrxt"]

    print("resetting dac")
    dacc.DAC_reset(writePort)

    print("setting all AFE LV vdd to 0.0V")
    for vdd in afe_vdd_list:
        dacc.DAC_set_voltage_cm(cm.dac[vdd],0.0,writePort)
        time.sleep(0.1)

    print("setting AFE vdd3v3 to 0.0V")
    dacc.DAC_set_voltage_cm(cm.dac["afe_vdd3v3"],0.0,writePort)

    print("setting AFE vddio to 0.0V")
    dacc.DAC_set_voltage_cm(cm.dac["afe_vddio"],0.0,writePort)

    print("setting all AFE vdd to 1.8V")
    for vdd in afe_vdd_list:
        dacc.DAC_set_voltage_cm(cm.dac[vdd],1.0,writePort)
        time.sleep(0.1)
        dacc.DAC_set_voltage_cm(cm.dac[vdd],1.8,writePort)
        time.sleep(0.1)

    print("setting AFE vddio to 1.8V")
    dacc.DAC_set_voltage_cm(cm.dac["afe_vddio"],1.8,writePort)

    print("Ready setting AFE to nominal VDD")



def get_channel_map():
    channel_map_module_name = 'lib.voltage_configs.channel_map_class'
    cmpkg = __import__(channel_map_module_name,globals(),locals(),['channel_map_class'])
    cm = cmpkg.channel_map_class()
    return cm

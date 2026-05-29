#!/usr/bin/env python
# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Commands to control the LEDs mounted on the Zedboard.

from lib.Bcolors import Bcolors as bc
from lib.WritePort import WritePort
from lib.ReadPort import ReadPort
import lib.perip_ISA as instructions

def leds_reset(writePort):
	# Reset all USER_LED
    led_command = (instructions.led_ctrl << 28) | 0
    writePort.sendInt(led_command)

def turn_on_single(writePort, ledIndex):
	# Turn on the specified single led (other LEDs are reset to 0)
    # Allowed indices: [0..3]
    if (ledIndex > 3) | (ledIndex < 0):
        bc.printError("ledIndex out of range [0..3]")
        return -1

    led_command = (instructions.led_ctrl << 28) | (1 << ledIndex)
    writePort.sendInt(led_command)

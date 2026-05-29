#!/usr/bin/env python
#
# Commands for controlling the DAC DAC5724
#
# CHANGELOG
#	v1.0, 20/12/2021	Copied from bvanhoof. Update to my specific project settings.

from lib.Bcolors import Bcolors
from lib.WritePort import WritePort
from lib.ReadPort import ReadPort
import lib.perip_ISA as instructions

single_ended = True

def DAC_reset(writePort):
	# Reset DAC bus 0 and 1
	DAC_single_reset(writePort,0)
	DAC_single_reset(writePort,1)
	DAC_single_reset(writePort,2)
	DAC_single_reset(writePort,3)

def DAC_single_reset(writePort,bus):
	# Basic settings for the DAC
	# output select range register
	# todo:check if this is still required...
	channel = 4
	register = 1
	if single_ended:
		data = 0 # + 5V range
	else:
		data = 3 # +/- 5V range
	dac_setup_part1 = (instructions.dac_config << 28) | (bus << 26) | (channel << 23) | (register << 16) | data
	# power control register
	channel = 0
	register = 2
	data = 15 # enable 4 dacs
	dac_setup_part2 = (instructions.dac_config << 28) | (bus << 26) | (channel << 23) | (register << 16) | data
	# control register
	channel = 1
	register = 3
	data = 4 # tsd enabled, clamp disabled, clr=0V, sdo enabled
	dac_setup_part3 = (instructions.dac_config << 28) | (bus << 26) | (channel << 23) | (register << 16) | data
	# Set the basic settings for the DAC
	writePort.sendInt(dac_setup_part1)
	writePort.sendInt(dac_setup_part2)
	writePort.sendInt(dac_setup_part3)

def DAC_set_voltage_cm(channel_dict, voltage, writePort):
	if voltage <= channel_dict['max'] and voltage >= channel_dict['min']:
		DAC_set_voltage(channel_dict['bus'], channel_dict['channel'], voltage, writePort)
	else:
		Bcolors.printError(str(voltage)+" out of bounds: ["+str(channel_dict['min'])+","+str(channel_dict['max'])+"]")

def DAC_set_voltage(bus, channel, voltage, writePort):
	# set max/min hard for testing
	# note that channel_dict already checks on max and min range
	if single_ended:
		max_volt = 3.5
		min_volt = 0.01 # for single-ended designs
	else:
		max_volt = 4.08
		min_volt = -4.105 # for +/-5V operation
	# checkers for max range
	if voltage > max_volt:
		voltage = max_volt
		print('overvoltage corrected')
	if voltage < min_volt:
		voltage = min_volt
		print('undervoltage corrected')
	# hex value calculation
	if voltage >= 0:
		if single_ended:
			# my design (REFIN = 2.048V, UNIPOLAR +5V range)
			# gives 1LSB (=0x001 in python) == 1mV
			hexval = int( 1000*voltage ) << 4
		else:
			# REFIN: 2048, +/- 5V range
			hexval = int( 1.0*2047/max_volt*voltage ) << 4
	else:
		if single_ended:
			Bcolors.printError("Error requesting voltage<0. The DACs in this design are all UNIPOLAR.")
		else:
			hexval = ( (1<<12) - int(1.0*2048/min_volt*voltage) ) << 4
#	print('writing value: ' + hex(hexval) + ' to channel ' + str(channel) + ', bus ' + str(bus) )
	DAC_set_value(bus, channel, hexval, writePort)

def DAC_set_value(bus, channel, hexval, writePort):
	if hexval > 0xffff:
		print('too large value: ' + hex(hexval) + ' corrected to 0xffff')
		hexval = 0xffff
	register = 0
	instruction = (instructions.dac_config << 28) | (bus << 26) | (channel << 23) | (register << 16) | hexval
	writePort.sendInt(instruction)

def DAC_write_all_zero(pwp):
	for bus in range(0,4):
		for channel in range(0,8):
			DAC_set_value(bus,channel,0x0,pwp)

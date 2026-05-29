#!/usr/bin/env python
#
# Commands for controlling the ADC ADS8331
#
# CHANGELOG
#	v1.0, 20/12/2021	Copied from bvanhoof. Update to my specific project settings.

import time
import numpy as np
import statistics as stat
from lib.Bcolors import Bcolors
from lib.WritePort import WritePort
from lib.ReadPort import ReadPort
import lib.perip_ISA as instructions
import lib.commands_DAC5724 as dacc

def ADC_reset(writePort):
	for bus in range(0,3):
		ADC_single_reset(writePort, bus)

def ADC_single_reset(writePort, bus):
	# Basic settings for the ADC (datasheet Table 5)
	#	2^10: CCLK = internal OSC
	# 	1021: all D[10-0] except D[1] are 1
	#		-- manual-trigger; EOC active low; no power-down modes; TAG bits disabled
	sw_reset = 0
	start_config = 1021 + 1024
	# reset adc 0
	adc_setup_part1 = (instructions.adc_config << 28) | (bus << 26) | sw_reset
	adc_setup_part2 = (instructions.adc_config << 28) | (bus << 26) | start_config
	# Set the basic settings for the ADC
	writePort.sendInt(adc_setup_part1)
	time.sleep(0.1)
	writePort.sendInt(adc_setup_part2)

def ADC_configure_channel(bus, channel, writePort):
	if channel >= 8 or channel < 0:
		Bcolors.printError("channel "+str(channel)+" out of bounds: [0,7]")
	instruction = (instructions.adc_command << 28) | (bus << 26) | (channel << 23)
	writePort.sendInt(instruction)

def ADC_measure_all(channel_map_adc, writePort, readPort):
	nb_samples = 1000
	for chan in channel_map_adc:
		I_avg_millamp = ADC_measure_current(channel_map_adc[chan], nb_samples, writePort, readPort, 0)
		print(" - chan " + chan + ": " + str(round(I_avg_millamp,4)) + "mA")

def ADC_measure_samples_cm(channel_dict, nb_samples, writePort, readPort):
	return ADC_measure_samples(channel_dict['bus'], channel_dict['channel'], nb_samples, writePort, readPort)

def ADC_measure_current(channel_dict, nb_samples, writePort, readPort, print_info=1):
	if (channel_dict["type"]=="voltage"):
		return None
	else:
		samples = ADC_measure_samples(channel_dict['bus'],channel_dict['channel'], nb_samples, writePort, readPort)
		I_samples = ADC_convert_hex_to_current(samples,channel_dict)
		I_avg_millamp = np.average(I_samples)*1e3
		if print_info:
			print("I measure on channel["+channel_dict['name']+"]: "+str(round(I_avg_millamp,4))+"mA")
		return I_avg_millamp

def ADC_measure_samples(bus, channel, nb_samples, writePort, readPort):
	result = []
	if nb_samples == 0:
		nb_samples = 1
	ADC_configure_channel(bus, channel, writePort)
	i = 0
	while readPort.readInt() != None:
		i = i + 1
	if i > 0:
		Bcolors.printWarning("There were still " + str(i) + " items in the buffer")
	#time.sleep(1)
	instruction = (instructions.adc_sample << 28) | (bus << 26) | (channel << 23) | nb_samples-1
	writePort.sendInt(instruction)
	for i in range(0,nb_samples):
		#print(i)
		hexvalue = readPort.readInt()
		loopctr = 0
		# check if value is not none, then add to array and so on...
		t = time.time()
		while hexvalue == None:
			hexvalue = readPort.readInt()
			time.sleep(0.01)
			loopctr  = loopctr + 1
			if loopctr > 500:
				print("loopcounter overflow reached in " + str(i) + "( took "+str(time.time()-t)+" s)")
				return result
		# note: only the lower 16 bits are valid, the upper 16 bits contain info like the bus and are not required.
		result.append(hexvalue & 0x0000ffff)
		# check for out-of-range
		if len(result)>=3:
			if result[-3] == 0x7fff and result[-2] == 0x7fff and result[-1] == 0x7fff:
				Bcolors.printWarning("bus " + str(bus) + ", channel " + str(channel) + ": max-range detected! (3 in a row)")
	return result
	#optioneel: generator yield

def ADC_convert_hex_to_current(hexval,channel_dict):
	if isinstance(hexval,list):
		current = []
		for val in hexval:
			current.append(ADC_convert_hex_to_current_single(val,channel_dict))
	else :
		current = ADC_convert_hex_to_current_single(hexval,channel_dict)
	return current

def ADC_convert_hex_to_current_single(hexval,channel_dict):
	# My ADC PCB setup: 1LSB = 1/16 mV
	v_midpoint = channel_dict['midpoint_volt']	# midpoint voltage [V]
	gain_ina = channel_dict['gain_ina']
	r_shunt = channel_dict['r_shunt_ohm']		# shunt R [Ohm]
	current = (hexval*1/(16*1000) - v_midpoint)*1/(r_shunt*gain_ina)
	return current

def moving_avg(numbers,window_size):
	i = 0
	result = []
	while(i<len(numbers)-window_size+1):
		this_window = numbers[i : i + window_size]
		window_average = sum(this_window) / window_size
		result.append(window_average)
		i += 1
	return result

def ADC_calibrate_channel(dac_channel, adc_channel, writeport, readport, dumpall=False):
	# set channel to 0V
	dacc.DAC_set_voltage(dac_channel['bus'], dac_channel['channel'], 0, writeport)
	time.sleep(1)
	
	nb_samples = 20000
	window_size = 500
	hex_samples = ADC_measure_samples(adc_channel['bus'], adc_channel['channel'], nb_samples, writeport, readport)
	
	# check if the samples are sampled correctly
	if len(hex_samples) == 0:
		Bcolors.printError("number of samples is 0")
		return -1
	
	if len(hex_samples) < nb_samples:
		Bcolors.printWarning("only "+str(len(hex_samples))+" acquired during calibration")
	
	samples = np.array(hex_samples)*1/(16*1000)
	#print(samples)
	
	# moving avg
	filtered_samples = moving_avg(samples,window_size)
	#filtered_samples = samples
	
	# check if the stdev is less then 1mv
	#if stat.stdev(filtered_samples) >= 0.002: # resolution is 0.001
	#	Bcolors.printError("standard deviation is larger than min. resolution: "+str(stat.stdev(filtered_samples)))
	#	if dumpall:
	#		return filtered_samples
	#	else:
	#		return -2
	
	if dumpall:
		return filtered_samples
	else:
		return round(stat.mean(filtered_samples),3)


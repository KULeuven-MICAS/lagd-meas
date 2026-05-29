# Python scripts and libs for Xillybus/Zedboard control

This python library holds example scripts and libraries for controlling your Xillybus on Zedboard environment.

## requirements
Since you are root on the zedboard, we do not bother using anaconda to install packages. We install them using the debian package manager apt (tutorial: https://itsfoss.com/apt-get-linux-guide/)

- python > 3.5
- numpy
- ipython (optional, but very much recommended)

## Get started

1. Configure your Zedboard as described in this gitlab repo **[todo create and link]**.
2. Copy, clone, ... this library
3. Start your interactive python session:

```bash
cd Python
ipython
In [1]: run perip_interactive.py
```

## architectural description
The fpga side of the zedboard is supposed to be set up with the bv_testcore: 2 read fifos and 2 write fifos.
This way, the control of the chip and the control of the peripherals (eg: adcs and dacs) is serperated if wanted.
This results in a linux device tree with the following files:
- /dev/xillybus_read_32: the first readport, used for chip control, also called 'chip read port': crp
- /dev/xillybus_write_32: the first writeport, used for chip control, also called 'chip write port': cwp
- /dev/xillybus_read_32_2: the second readport, used for periphery control, also called 'periphery read port': prp
- /dev/xillybus_write_32_2: the second writeport, used for periphery control, also called 'periphery write port': pwp

When using the zedboard with the bare minimum fpga code from the zedboard_bitstream project, the following holds:
- the periphery write port acts as a command + data buffer, where the 4 MSBs are the opcode
- the periphery read port acts as a result dump
- an opcode is implemented for loop-back: 0xf (all bits of the 4-bit opcode are 1): the whole command is dumped into the prp.
- the controller for the ADC(ADS8331) and DAC (DAC5724) are implemented on the fpga

## directory and file description
The ipython interpreter (or whatever files you are running) is supposed to be run in this main folder.
Some main example files are in the top level:
- perip_interactive.py : this is the most basic file: it opens the periphery read and write ports in pwp and prp and shows a few test commands, for instance the leds and loop-back.
- adc_dac_interactive: this file opens the prp and pwp and resets the adc and dac. Then, it shows a few examples for the usage of the ADC/DAC functions. NOTE: the channel map needs to be configured correctly (see further)
- chip_interactive: this opens the crp and cwp and shows the loopback command. Now, it is up to you to first modify the verilog code and add your own chip library (see further: some skeleton files are provided...)

Furthermore, the lib folder contains all files that assemble instructions and read back results in a more human-readable way.
Common stuff is:
- Bcolors.py: a library to print nice colors on your terminal.
- ReadPort.py: handles the readports
- WritePort.py: handles the writeports

Specific periphery stuff is:
- perip_ISA: a mapping of the opcodes to a more human-readable format. This should hold the same ops as the perip_command_api.sv
- commands_leds_zedboard: lib to handle the leds
- commands_ADS8331: lib to configure and pull data from the adcs, requires channel map to be configured
- commands_DAC5724: lib to configure and push data to the dacs, requires channel map to be configured
- supply: high level file to set the supplies using the channel map
- voltage_configs: this folder contains your voltage configurations. channel_map_class.py an example. you could add multiple copies of this file in this folder, each with a specific configuration. Then, it''s just the matter of loading the correct one.

Specific chip stuff is:
- chipc_ISA

## channel maps ##
The channel maps are located in the lib/voltage_configs folder.
A channel map contains two dictionaries:
- a dac dictionary: contains for each named supply: the channel and bus number, minimum, maximum and nominal voltages. This is useful in combination with the dac file, since it checks if a user-input voltage is within range and there is a function to set all the channels to their nominal voltage.
- an adc dictionary: contains for each named channel: the channel and number, the midpoint voltage, gain and shunt resistance: this enables a correct current measurement using the adc file



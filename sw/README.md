# Python scripts and libs for Xillybus/Zedboard control

Author: Jiacong Sun <jiacong.sun@kuleuven.be>. (Built based on MICAS inheritance)

This folder holds python scripts and libraries for LAGD project for controlling Xillybus on Zedboard environment.

## Environment requirements
The Xillinux used by LAGD has installed a python, version: 3.6.15; and the pip, version: 21.3.1

ipython can be triggered by command: `python -m IPython`

Following packages have been installed:

| Package | Version |
| --- | --- |
| anyio | 3.6.2 |
| argon2-cffi | 21.3.0 |
| argon2-cffi-bindings | 21.2.0 |
| async-generator | 1.10 |
| attrs | 22.2.0 |
| Babel | 2.11.0 |
| backcall | 0.2.0 |
| bleach | 4.1.0 |
| certifi | 2025.4.26 |
| cffi | 1.15.1 |
| charset-normalizer | 2.0.12 |
| contextvars | 2.4 |
| dataclasses | 0.8 |
| decorator | 5.1.1 |
| defusedxml | 0.7.1 |
| entrypoints | 0.4 |
| idna | 3.10 |
| immutables | 0.19 |
| importlib-metadata | 4.8.3 |
| ipykernel | 5.5.6 |
| ipython | 7.16.3 |
| ipython-genutils | 0.2.0 |
| jedi | 0.17.2 |
| Jinja2 | 3.0.3 |
| json5 | 0.9.16 |
| jsonschema | 3.2.0 |
| jupyter-client | 7.1.2 |
| jupyter-core | 4.9.2 |
| jupyter-server | 1.13.1 |
| jupyterlab | 3.2.9 |
| jupyterlab-pygments | 0.1.2 |
| jupyterlab-server | 2.10.3 |
| MarkupSafe | 2.0.1 |
| mistune | 0.8.4 |
| nbclassic | 0.3.5 |
| nbclient | 0.5.9 |
| nbconvert | 6.0.7 |
| nbformat | 5.1.3 |
| nest-asyncio | 1.6.0 |
| notebook | 6.4.10 |
| numpy | 1.19.5 |
| packaging | 21.3 |
| pandocfilters | 1.5.1 |
| parso | 0.7.1 |
| pexpect | 4.9.0 |
| pickleshare | 0.7.5 |
| pip | 21.3.1 |
| prometheus-client | 0.17.1 |
| prompt-toolkit | 3.0.36 |
| ptyprocess | 0.7.0 |
| pycparser | 2.21 |
| Pygments | 2.14.0 |
| pyparsing | 3.1.4 |
| pyrsistent | 0.18.0 |
| python-dateutil | 2.9.0.post0 |
| pytz | 2025.2 |
| pyzmq | 25.1.2 |
| requests | 2.27.1 |
| Send2Trash | 1.8.3 |
| setuptools | 40.6.2 |
| six | 1.17.0 |
| sniffio | 1.2.0 |
| terminado | 0.12.1 |
| testpath | 0.6.0 |
| tornado | 6.1 |
| traitlets | 4.3.3 |
| typing_extensions | 4.1.1 |
| urllib3 | 1.26.20 |
| wcwidth | 0.2.13 |
| webencodings | 0.5.1 |
| websocket-client | 1.3.1 |
| zipp | 3.6.0 |

## architectural description
The fpga side of the zedboard is supposed to be set up with the bv_testcore: 2 read fifos and 2 write fifos.
This way, the control of the chip and the control of the peripherals (eg: adcs and dacs) is separate if wanted.
This results in a linux device tree with the following files:
- /dev/xillybus_read_32: the first readport, used for chip control, also called 'chip read port': crp
- /dev/xillybus_write_32: the first writeport, used for chip control, also called 'chip write port': cwp
- /dev/xillybus_read_32_2: the second readport, used for periphery control, also called 'periphery read port': prp
- /dev/xillybus_write_32_2: the second writeport, used for periphery control, also called 'periphery write port': pwp

When using the zedboard with the bare minimum fpga code from the zedboard_bitstream project, the following holds:
- the periphery write port acts as a command + data buffer, where the 4 MSBs are the opcode
- the periphery read port acts as a result dump
- an opcode is implemented for loop-back: 0xe: the whole command is dumped into the prp.
- the controller for the DAC is implemented on the fpga

## directory and file description
The ipython interpreter (or whatever files you are running) is supposed to be run in this folder.
Some main example files are in the top level:
- chip_test.py:

Furthermore, the lib folder contains all files that assemble instructions and read back results in a more human-readable way.
Common stuff is:
- Bcolors.py: a library to print nice colors on your terminal.
- ReadPort.py: handles the readports
- WritePort.py: handles the writeports

## TODO: below is to be clean

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



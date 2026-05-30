# Python scripts and libs for Xillybus/Zedboard control

Author: Jiacong Sun <jiacong.sun@kuleuven.be>

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

The chip control protocol is defined by `fpga/src/verilog/chip_command_api.sv`: a 32-bit
word is a command only when its top nibble (the handshake marker) equals 0xF; the next byte
is the opcode. The software mirror of this ISA lives in `lib/chip_command_api.py`.

The periphery port (prp/pwp) drives the on-chip DAC via `fpga/src/verilog/perip_command_api.sv`,
which uses the same framing as the chip controller: a 32-bit word is a command only when its top
nibble (marker) equals 0xF, with the opcode in the next byte (0xFF selects writeback, any other
value performs a DAC transaction). The whole DAC payload (rstn/shdn/addr/data) fits in that single
word. The software mirror of this ISA lives in `lib/perip_command_api.py`.

## directory and file description
The ipython interpreter (or whatever files you are running) is supposed to be run in this folder.
The two top-level scripts test one controller each (interactive session + writeback stress test):
- chip_test.py: wires up a ChipDriver on the chip ports (cwp/crp) and runs main()
- perip_test.py: wires up a PeripDriver on the periphery ports (pwp/prp) and runs main()

Furthermore, the lib folder contains the reusable building blocks:
- port_driver.py: PortDriver -- shared base owning a read+write port (open/close as a context manager, word send, read polling, writeback loopback); subclassed by the two drivers below
- chip_driver.py: ChipDriver -- exposes the chip command set (init_spi, config_clk_rst, write_mem, read_mem, writeback)
- chip_command_api.py: chip controller ISA (command-word builders + opcodes); the software mirror of `chip_command_api.sv` and must stay in sync with it
- perip_driver.py: PeripDriver -- exposes the periphery/DAC command set (dac_write, dac_reset, writeback)
- perip_command_api.py: periphery controller ISA (command-word builders + opcodes); the software mirror of `perip_command_api.sv` and must stay in sync with it
- read_port.py: ReadPort -- handles the readports
- write_port.py: WritePort -- handles the writeports

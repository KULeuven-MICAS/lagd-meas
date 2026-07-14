# Python scripts and libs for Xillybus/Zedboard control

Author: Jiacong Sun <jiacong.sun@kuleuven.be>

This folder holds python scripts and libraries for LAGD project for controlling Xillybus on Zedboard environment.

Before running any script under sw/, please source the env.sh (to ensure the import works correctly in python):

```[bash]
cd sw/
source env.sh
```

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
- /dev/xillybus_read_8 / /dev/xillybus_write_8: the 8-bit byte stream, used for PLL serial configuration (see `lib/pll_driver.py`, `tests/pll_test.py`)

The chip control protocol is defined by `fpga/src/verilog/chip_command_api.sv`: a 32-bit
word is a command only when its top nibble (the handshake marker) equals 0xF; the next byte
is the opcode. The software mirror of this ISA lives in `lib/chip_command_api.py`.

The periphery port (prp/pwp) hosts TWO devices on its one stream via `fpga/src/verilog/perip_command_api.sv`,
multiplexed by the opcode: the on-board DAC and the HV9308 32-channel serial-to-parallel converter
(S2P) that biases the chip's analog current mirrors. Same framing as the chip controller (32-bit word,
marker 0xF, opcode in the next byte). DAC commands are single words (rstn/shdn/addr/data). The S2P adds
`S2P_WRITE` (a 2-word [cmd][32-bit value] frame, shift+latch), `S2P_READBACK` (recirculating scan of the
HV9308 shift register out of its cascade Data Out -> 1 word), and `S2P_OE` (output enable). The software
mirror of this ISA lives in `lib/perip_command_api.py`.

The PLL port (8-bit read_8/write_8) drives the Pomelo PLL serial configuration via
`fpga/src/verilog/pll_command_api.sv`. Because the stream is byte-wide, a command is a multi-byte
frame: a header byte `{marker=0xF, opcode}` followed by an opcode-dependent payload (the 47-bit
config split little-endian into 6 bytes for LOAD). The software mirror of this ISA -- including the
field-level `pack_pll_cfg()` from `pomelo_pll_wrap_cfg.yml` -- lives in `lib/pll_command_api.py`.

## directory and file description
The lib folder contains the reusable building blocks:
- port_driver.py: PortDriver -- shared base owning a read+write port (open/close as a context manager, word send, read polling, writeback loopback); subclassed by the two drivers below
- chip_driver.py: ChipDriver -- exposes the chip command set (init_spi, config_clk_rst, write_mem, read_mem, writeback)
- chip_command_api.py: chip controller ISA (command-word builders + opcodes); the software mirror of `chip_command_api.sv` and must stay in sync with it
- perip_driver.py: PeripDriver -- exposes the periphery command set for both devices on the stream: the DAC (dac_write, dac_reset, writeback, AD8802 channel/voltage helpers backed by a host-side cache) and the HV9308 S2P (s2p_write, s2p_readback, s2p_verify, s2p_output_enable, and s2p_reconfigure which blanks->writes->re-enables)
- perip_command_api.py: periphery controller ISA (command-word builders + opcodes); the software mirror of `perip_command_api.sv` and must stay in sync with it
- pll_driver.py: PllDriver -- exposes the PLL serial-config command set over the 8-bit stream (load/load_cfg, verify_load, reset, clk_sel, writeback, plus a `bring_up` helper that configures+switches the SoC onto the PLL); keeps a host-side cache of the last config word
- pll_command_api.py: PLL controller ISA (byte-frame builders + opcodes + the `pack_pll_cfg`/`rst_pll_cfg` field layout); the software mirror of `pll_command_api.sv` / `pomelo_pll_wrap_cfg.yml` and must stay in sync with them
- read_port.py: ReadPort -- handles the readports
- write_port.py: WritePort -- handles the writeports

The tools folder contains the program loader (load an ELF onto the chip and run it):
- tools/elf_loader.py: transport-agnostic ELF reader (pure stdlib `struct`, no pyelftools). Parses PT_LOAD segments + entry point; reusable by SPI/JTAG/UART loaders. Run standalone to inspect an ELF: `python3 tools/elf_loader.py tests/helloworld.spm.elf`
- tools/spi_program_loader.py: SPI-specific loader. Writes each segment over SPI via a ChipDriver, hands the entry point to the bootrom via the SCRATCH registers, and launches. Run: `python3 tools/spi_program_loader.py tests/helloworld.spm.elf [--verify] [--wait]` (boot_mode must be 0; the loader drives chip_clk_en/rstn unless `--no-clk-rst`).
- tests/: prebuilt ELFs (e.g. helloworld.spm.elf) copied from the lagd-im SW build, plus their .dump disassembly for reference.

See `doc/spi_program_loading.md` for the full SPI load-and-launch background.

## two loaders: Xillybus drivers vs UART
Firmware/control reaches the chip over two independent transports, both run from
this Zedboard host and both consuming the same chip ELFs in `inputs/`:
- **Via the FPGA (Xillybus):** the `lib/` drivers and `tools/spi_program_loader.py`
  push data through the FPGA fabric over `/dev/xillybus_*`. Requires the bitstream
  to be loaded (this is the "control the FPGA drivers" path).
- **Direct UART (FT4232):** `uart/send_uart.py` loads and runs an ELF over the chip's
  Cheshire bootrom UART debug protocol on `/dev/ttyUSBn`. It talks to the chip
  directly and **bypasses the FPGA entirely** (no bitstream needed for the link
  itself; the chip just has to be clocked and out of reset). Offline self-test:
  `python3 uart/selftest.py`. See `uart/README.md` for the protocol and flags.

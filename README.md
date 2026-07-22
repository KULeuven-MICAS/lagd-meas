# ☯ LAGD-MEAS

Author: Jiacong Sun \<jiacong.sun@kuleuven.be\>

Measurement and software environment for the **LAGD** chip: an FPGA bitstream plus
host-side Python that let a Linux host configure the chip and its on-board DAC and
read data back.

## How it fits together

```
host (Python, Zynq Linux)  ──Xillybus FIFOs──▶  FPGA controllers  ──SPI / serial──▶  LAGD chip + DAC + PLL
        sw/                                          fpga/
```

Running on a Zedboard, the host pushes command words/bytes into Xillybus FIFOs;
FPGA controllers decode them and drive the chip over Quad-SPI (register/memory
access), the on-board DAC over SPI, and the on-chip PLL over a serial-shift config
interface. Three independent FIFO streams keep chip, peripheral, and PLL control
separate.

## Layout

- [`fpga/`](fpga/) — Vivado project for the Zedboard/Xillinux bitstream (the SPI
  controllers and Xillybus glue). Build with `make`, unit-test with `make sim`.
  See [fpga/README.md](fpga/README.md).
- [`sw/`](sw/) — Python control library and per-controller test scripts, run on
  the Zynq Linux host. See [sw/README.md](sw/README.md).

## Getting started

1. Build and load the bitstream — see [fpga/README.md](fpga/README.md).
2. On the Zedboard's Linux, run the host scripts — see [sw/README.md](sw/README.md).

## Dependencies

_Coming soon: a `requirements.txt` for the Python host-side code, and a Vivado version for the FPGA bitstream._

## Lab instrument control

The host-side Python can also control lab instruments (power supplies, multimeters, etc.) over LAN.
To set up LAN connections, you need to authenticate with the IC-LAB secure server.
You can authenticate by:
  * prompting for your username and password from command line
  * passing your username and password as arguments to the script (not recommended)
  * generating a keyfile with your credentials and using it to authenticate automatically. (recommended)

### Generating a keyfile

To generate a keyfile, run the following command:

```bash
python3 sw/lib/os_utils/keygen.py
```

The script will ask for destination key file path, username and password.
It will then ask for a master password to encrypt your credentials.

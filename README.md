# ☯ LAGD-MEAS

Author: Jiacong Sun <jiacong.sun@kuleuven.be>

Measurement and software environment for the **LAGD** chip: an FPGA bitstream plus
host-side Python that let a Linux host configure the chip and its on-board DAC and
read data back.

## How it fits together

```
host (Python, Zynq Linux)  ──Xillybus FIFOs──▶  FPGA controllers  ──SPI──▶  LAGD chip + DAC
        sw/                                          fpga/
```

Running on a Zedboard, the host pushes 32-bit command words into Xillybus FIFOs;
FPGA controllers decode them and drive the chip over Quad-SPI (register/memory
access) and the on-board DAC over SPI. Two independent FIFO pairs keep chip and
peripheral control separate.

## Layout

- [`fpga/`](fpga/) — Vivado project for the Zedboard/Xillinux bitstream (the SPI
  controllers and Xillybus glue). Build with `make`, unit-test with `make sim`.
  See [fpga/README.md](fpga/README.md).
- [`sw/`](sw/) — Python control library and per-controller test scripts, run on
  the Zynq Linux host. See [sw/README.md](sw/README.md).

## Getting started

1. Build and load the bitstream — see [fpga/README.md](fpga/README.md).
2. On the Zedboard's Linux, run the host scripts — see [sw/README.md](sw/README.md).

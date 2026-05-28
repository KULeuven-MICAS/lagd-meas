This repository contains the vivado project for LAGD chip.

To generate the vivado project, please run "make" under fpga/.

The generated xillydemo.bit should be placed under /mnt/sd/xillydemo.bit. The xilinux should be reboot to load the new bitstream.

The xillinux template is from: xillybus.com/downloads/xillinux-eval-zedboard-2.0c.zip

Note: in the FPGA project, all reset are active-high, which aligns with vivado FIFO IP. However, the chip and DAC use active-low reset.
# Measurement Ladder (LAGD chip, 2026)

<!-- Icon warehouse: 🔳✅ -->

Author: Jiacong Sun \<jiacong.sun@kuleuven.be\>

---

This file documents the measurement ladder (sequence) for LAGD (V1) chip.

**Note:** Before running any tests (especailly python) below, please do:

```[bash]
cd lagd-meas/
source env.sh
```

The measurement consists of the functional test and the performance measurement.

## Functional Test

### **Lab-Instrument Test**

- ✅ Power source (the voltage can be configured remotely)

### **On-PCB Test**

- ✅ DAC (AD8802) Interface (DAC output voltage can be configured)

```[bash]
python sw/tests/perip_test.py
```

- 🔳 S2P (HV9308) Interface (Resistor network can be configured)

```[bash]
python sw/tests/perip_test.py
```

### **On-Chip Test**

#### PLL Test

- 🔳 PLL Interface and PLL (PLL can start correctly)

```[bash]
python sw/tests/pll_test.py
```

#### SoC Test via Each Interface

##### UART (FT4232H UART channel, /dev/ttyUSB2)

- ✅ (optional) FT4232H' UART channel and host serial path work — no chip involved

```[bash]
python sw/testcases/uart/00_loopback/loopback.py --device /dev/ttyUSB2
```

- ✅ Find the chip's UART and confirm the bootrom answers the 0x06 handshake

```[bash]
./testcases/uart/01_portsweep/portsweep.py --scan
```

- ✅ Chip is clocked and the bootrom works (via the real loader)

```[bash]
./testcases/uart/02_handshake/run.sh
```

- ✅ HelloWord ELF test

```[bash]
./testcases/uart/03_load_run/run.sh --device /dev/ttyUSB2 --no-exec --verify ─▶ Memory check only
./testcases/uart/03_load_run/run.sh --device /dev/ttyUSB2 --verify ─▶ Run and check
```

- ✅ Memory volume stress test (mem-base: hex, mem-size: size in bit)

```[bash]
./testcases/uart/04_memtest/run.sh --mem-base 0x10000000 --mem-size 0x3fc8
./testcases/uart/04_memtest/run.sh --mem-base 0x80000000 --mem-size 0x10000
./testcases/uart/04_memtest/run.sh --mem-base 0x90000000 --mem-size 0x10000
./testcases/uart/04_memtest/run.sh --mem-base 0x90010000 --mem-size 0x10000
```

- ✅ IsingCore Reg test

```[bash]
python sw/uart/send_uart.py sw/inputs/lagd_reg.spm.elf --device /dev/ttyUSB2 --verify
```

- ✅ IsingCore ELF test

```[bash]
python sw/uart/send_uart.py sw/inputs/lagd_dcompute.spm.elf --device /dev/ttyUSB2 --verify
```

##### SPI (FPGA FMC)

- ✅ Quad-SPI interface works and memory can be accessed (no ELF)

```[bash]
python sw/tests/chip_test.py
```

- ✅ HelloWorld ELF test

```[bash]
python sw/tests/chip_load_spi.py
```

- 🔳 IsingCore ELF test

```[bash]
python sw/tests/chip_load_spi.py sw/inputs/lagd_dcompute.spm.elf
```

#### JTAG (FT4232H JTAG channel, /dev/ttyUSB0)

- 🔳 FT4232H' JTAG channel works and Chip JTAG (slave) returns the correct IDCODE (0x1c5e5db3)

```[bash]
openocd -f testcases/jtag/01_idcode/openocd.scan.tcl
```

- 🔳 Chip is clocked and the bootrom works

```[bash]
openocd -f /testcases/jtag/02_halt/openocd.halt.tcl
```

- 🔳 HelloWord ELF test

```[bash]
./testcases/jtag/03_load_run/run.sh
```

- 🔳 Memory volume stress test (same purpose as UART test) (mem-base: hex, mem-size: size in bit)

```[bash]
./testcases/jtag/04_memtest/run.sh -c "set MEM_WORDS 16384; set ADAPTER_KHZ 4000"
```

- 🔳 JTAG speed upperlimit test (figure out the highest reliable JTAG clock speed. The ones above are all on 100 kHz)

```[bash]
./testcases/jtag/05_speed/speed_sweep.sh
```

- 🔳 IsingCore ELF test

```[bash]
./sw/jtag/run_elf.sh sw/inputs/lagd_dcompute.spm.elf -c "set ADAPTER_KHZ 4000"
```

#### Galena Calibration

- 🔳 How to calibrate galena's external bias?


## Performance Measurement

### Single case: 256x128 QAM4 MIMO @ 0.8V, 500 MHz

#### Energy

#### TTS

```[bash]
python sw/uart/send_uart.py sw/inputs/lagd_scompute.spm.elf --device /dev/ttyUSB2 --verify ─▶ Via UART (115200)
./sw/jtag/run_elf.sh sw/inputs/lagd_scompute.spm.elf -c "set ADAPTER_KHZ 4000" ─▶ Via JTAG
```

### BER-SNR @ 24x24 BPSK MIMO

### BER-SNR @ 256x128 QAM4 MIMO

### MPC

### MaxCut

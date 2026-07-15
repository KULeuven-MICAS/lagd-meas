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

The measurement consists of the following parts:

## Functional Tests

### **Lab-Instrument Test**

- 🔳 Power source (the voltage can be configured remotely)

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

- 🔳 FT4232H' UART channel and Chip UART (slave) interface work

```[bash]
python sw/testcases/uart/01_loopback/loopback.py --device /dev/ttyUSB2
```

- 🔳 Chip is clocked and the bootrom works

```[bash]
./sw/testcases/uart/02_handshake/run.sh
```

- 🔳 HelloWord ELF test

```[bash]
./sw/testcases/uart/03_load_run/run.sh --device /dev/ttyUSB2 --no-exec --verify ─▶ Memory check only
./sw/testcases/uart/03_load_run/run.sh --device /dev/ttyUSB2 --verify ─▶ Run and check
```

- 🔳 Memory volume stress test (mem-base: hex, mem-size: size in bit)

```[bash]
./sw/testcases/uart/04_memtest/run.sh --device /dev/ttyUSB2 --mem-base 0x80000000 --mem-size 0x2000
```

- 🔳 IsingCore ELF test

```[bash]
python sw/uart/send_uart.py sw/inputs/lagd_dcompute.spm.elf --device /dev/ttyUSB2 --verify
```

##### SPI (FPGA FMC)

- 🔳 Quad-SPI interface works and memory can be accessed (no ELF)

```[bash]
python sw/tests/chip_test.py
```

- 🔳 HelloWorld ELF test

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

### TTS @ 0.8V, 500MHz

### BER-SNR @ 24x24 BPSK MIMO

### BER-SNR @ 256x128 QAM4 MIMO

### MPC

### MaxCut

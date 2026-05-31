# Vivado project for Xillybus/Zedboard control

Author: Jiacong Sun <jiacong.sun@kuleuven.be>

This repository contains the Vivado project for the LAGD chip.

To generate the Vivado project, run `make` under `fpga/`.

The generated `xillydemo.bit` should be placed under `/mnt/pl_sd/xillydemo.bit`
(mount first with `mount_pl_sd.sh`). Reboot Xillinux to load the new bitstream.

The Xillinux template is from: xillybus.com/downloads/xillinux-eval-zedboard-2.0c.zip

> Note: in the FPGA project all resets are active-high (aligning with the Vivado
> FIFO IP). The chip and DAC use active-low reset.

---

## SPI interfaces

The FPGA drives **two independent SPI controllers**, each on its own Xillybus
FIFO pair and clock domain. Both work the same way at the host level — push
32-bit command words into a write FIFO, optionally get a loopback word on the
read FIFO — but they target different devices and use different SPI modes.

| Interface | Controller | Device | FIFOs | SPI mode |
|-----------|------------|--------|-------|----------|
| Quad-SPI to chip | [chip_controller.sv](src/verilog/chip_controller.sv) + [quad_spi_master.sv](src/verilog/quad_spi_master.sv) | chip's on-chip `axi_spi_slave` (register/memory) | `/dev/xillybus_{write,read}_32` | mode 0, quad, bursts |
| DAC SPI | [perip_controller.sv](src/verilog/perip_controller.sv) + [dac_spi_driver.sv](src/verilog/dac_spi_driver.sv) | on-board DAC (DAC8802) | `/dev/xillybus_{write,read}_32_2` | mode 3, 1-bit, single word |

---

## 1. Quad-SPI to the chip

The FPGA talks to the chip's on-chip SPI slave (an ETH/PULP `axi_spi_slave`)
over a Quad-SPI bus. The path from the host (Linux on the Zynq PS) to the chip is:

```
host SW  ──Xillybus FIFOs──▶  chip_controller  ──▶  quad_spi_master  ──Quad-SPI──▶  chip (axi_spi_slave ─▶ AXI memory)
(chip_test.py)   ▲ readback         │                                                                 │
                 └─────────────── read FIFO ◀───────────────────────────────────────────────────────┘
```

- **Write FIFO** (`/dev/xillybus_write_32`): the host pushes 32-bit *command* and
  *data* words.
- **Read FIFO** (`/dev/xillybus_read_32`): the FPGA pushes readback words back to
  the host.

### Command protocol

The controller reads a stream of 32-bit words and groups them into *frames* (a
command word, then the address/data words it needs). A word is decoded as a
**command** only when the controller is expecting one (i.e. it is idle between
frames) **and** the word's top nibble is the marker `0xF`. Full encoding:
[chip_command_api.sv](src/verilog/chip_command_api.sv).

```
[31:28] marker = 0xF   [27:20] opcode   [19:16] reserved   [15:0] burst_length
```

The address and data words inside a frame are consumed *by position* — the
controller already knows they follow the command — so they may carry **any**
value (including a `0xF` top nibble). Non-command words are **never forwarded to
the chip**: the marker is only a re-sync safeguard. If the FIFO stream ever gets
misaligned, a stray word arriving where a command is expected is **discarded**
instead of being misread as a command. Because chip addresses never start with
`0xF`, a real address can never be mistaken for a command.

| opcode | operation        | FIFO frame (host → write FIFO)          | SPI cmd |
|--------|------------------|-----------------------------------------|---------|
| `0x00` | CONFIG_CLK_RST   | `[cmd]` (bit1=clk_en, bit0=rstn)        | – (local) |
| `0x01` | CONFIG_SPI_SLAVE | `[cmd]`                                 | `0x01` (enable Quad) |
| `0x02` | DATA_WRITE       | `[cmd(N)] [addr] [d0]…[d(N-1)]`          | `0x02` (write mem) |
| `0x0B` | DATA_READ        | `[cmd(N)] [addr]`  → N words read back   | `0x0B` (read mem) |
| `0xFF` | WRITEBACK_FIFO   | `[cmd]` → echoed back (loopback test)    | – (local) |

`N` = `burst_length` = number of 32-bit words. `N = 1` is a single word; `N > 1`
is a burst to consecutive word addresses (`addr`, `addr+4`, …). Up to 65535
words per frame.

### How to use it (from the host)

Helpers live in [sw/chip_test.py](../sw/chip_test.py) / [sw/lib/chipc_ISA.py](../sw/lib/chipc_ISA.py):

```python
init_spi()                       # 1) enable Quad-SPI on the slave (do this once, first)
write_mem(0x0, [0x11,0x22,0x33]) # 2) burst write 3 words to 0x0, 0x4, 0x8
read_mem(0x0, 3)                 # 3) burst read 3 words -> [0x11, 0x22, 0x33]
config_clk_rst(clk_en=1, rstn=1) # drive the chip clock-enable / reset pins
```

**`init_spi()` must run first.** The slave powers up in standard SPI; Quad mode is
only active after `CONFIG_SPI_SLAVE` writes its `reg0`.

### How the SPI works (behavior)

- **SPI mode 0** (CPOL=0, CPHA=0): clock idles low, the slave samples MOSI on the
  rising edge and changes MISO on the falling edge.
- **Quad enable**: `CONFIG_SPI_SLAVE` sends standard-SPI command `0x01` followed
  by a data byte `0x01` (sets `reg0[0]`). Until then the slave is standard SPI.
- **Reads need 33 dummy cycles** between the address and the first data word
  (slave dummy register = 32 plus one extra from the slave's RX-counter
  off-by-one). The master inserts exactly 33; this is fixed, not tunable.
- **Bursts are continuous**: one command + one start address, then the data
  streams within a single chip-select frame while the address auto-increments by
  one word. Reads/writes end when chip-select is released.
- **Flow control**: data words are streamed with backpressure. The master pauses
  the SPI clock (chip-select stays low) when the input FIFO underruns (write) or
  the output FIFO is full (read), so no data is lost — the slave is edge-driven
  and tolerates a paused clock.

---

## 2. DAC SPI (peripheral)

A second, independent controller configures the on-board DAC. It uses its own
FIFO pair (`/dev/xillybus_{write,read}_32_2`) and clock, driven by
[perip_controller.sv](src/verilog/perip_controller.sv) +
[dac_spi_driver.sv](src/verilog/dac_spi_driver.sv).

Unlike the chip Quad-SPI, **each DAC access is a single self-contained 32-bit
word** — there are no follow-up address/data words and no bursts. The fields are
defined in [perip_command_api.sv](src/verilog/perip_command_api.sv):

| bits  | field     | meaning                                                       |
|-------|-----------|---------------------------------------------------------------|
| 31    | valid     | `0` = ignore the word                                         |
| 30    | writeback | `1` = echo the word to the read FIFO (loopback test), no SPI  |
| 13    | rstn      | `0` = hold the DAC in reset (`dac_rstn` low), no SPI          |
| 12    | shdn      | DAC shutdown control (active low), driven on `dac_shdn`       |
| 11:8  | addr      | 4-bit DAC register address                                    |
| 7:0   | data      | 8-bit register value                                          |

When `valid=1`, `writeback=0`, `rstn=1`, the controller runs one **12-bit
MSB-first** SPI transfer of `{addr, data}`.

Behavior:
- **SPI mode 3** (CPOL=1, CPHA=1): clock idles high, the driver changes data on
  the falling edge and the DAC samples on the rising edge.
- Chip-select stays low for the transfer and is held low for `CSB_HOLD_CYCLES`
  extra cycles afterwards to meet DAC timing.
- One transfer per word (no bursts); `dac_shdn` / `dac_rstn` are also driven
  directly from the command word.

> Note: the host-side DAC helpers under `sw/lib/` are legacy and predate the
> current `perip_command_api.sv` packing — when reusing the DAC path, build words
> to match the table above rather than the old helper encoding.

---

## Simulation

A self-checking unit testbench (with a behavioral model of the ETH slave) for the
chip Quad-SPI lives under
[src/unit_tests/chip_controller/](src/unit_tests/chip_controller/):

```
make sim            # run the suite (console PASS/FAIL)
make sim DUMP=1     # ... and write a VCD into vivado-runs/
```

---

## Where this can (and cannot) be reused

**Reusable** as a host↔device access path:
- the chip Quad-SPI (`chip_controller` + `quad_spi_master` + command API) for
  **any chip embedding the ETH/PULP `axi_spi_slave`** (HEMAiA/Occamy-style);
- the `dac_spi_driver` as a small **mode-3, MSB-first** SPI engine for similar
  parallel-loaded DACs.

The RTL is self-contained and ports to other Xilinx FPGAs; only the host
transport (here Xillybus 32-bit FIFOs) needs swapping if you don't use
Xillinx/Zedboard.

**Not reusable as-is** for:
- a *different* on-chip SPI slave or a generic SPI flash — the Quad-SPI master
  hard-codes this slave's behavior (command bytes `0x01`/`0x02`/`0x0B`, `reg0`
  Quad-enable, the 33-cycle read dummy, MS-nibble-first quad ordering). A
  different slave needs the master adapted.
- a DAC with a different word width or SPI mode — adjust `dac_spi_driver`'s
  `SHIFT_BITS` / mode accordingly.
- non-Xillybus / non-Zedboard platforms without replacing the FIFO front-end
  (and note Xillybus requires its own IP/license).

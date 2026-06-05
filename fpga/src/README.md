# FPGA source (`fpga/src/`)

RTL, constraints, IP and unit tests for the LAGD Xillybus bitstream on the
Zedboard. The design builds on the **`corebundle-bv_testcore_2022`** Xillybus
flavor (downloaded by Bob Vanhoof, 2022), which provides the base Xillybus setup
plus the host↔FPGA FIFO streams this project uses.

General **Xillybus documentation**: http://www.xillybus.com/doc.

## Xillybus streams used

| Stream | Width | Driven by |
|--------|-------|-----------|
| `/dev/xillybus_{write,read}_32`   | 32-bit | chip controller — chip Quad-SPI |
| `/dev/xillybus_{write,read}_32_2` | 32-bit | periphery controller — on-board DAC SPI + HV9308 S2P |
| `/dev/xillybus_{write,read}_8`    |  8-bit | PLL controller — Pomelo PLL serial config |

The two 32-bit pairs let an independent host engine poll Ivdd/Ibias measurements
while sending/receiving commands to the chip in parallel; the 8-bit byte stream
carries the PLL configuration. See [../README.md](../README.md) for the
controllers, their command protocols, the build (`make`), and simulation
(`make sim`).

## Layout

- `verilog/` — RTL: top module [verilog/xillydemo.v](verilog/xillydemo.v) plus the
  three controllers (`chip_controller`, `perip_controller`, `pll_controller`) with
  their `*_command_api.sv` ISAs, the device engines (`quad_spi_master`,
  `dac_spi_driver`, `s2p_driver`), the FIFO→AXI-stream adapter, and helper macros.
- `constraints/` — [constraints/xillydemo.xdc](constraints/xillydemo.xdc): pin
  mapping and IO timing.
- `vivado_ip/` — packaged Vivado IP: the dual-port FIFOs (`fifo_dualport_32x512`,
  `fifo_dualport_8x2048`) and the clock wizard.
- `unit_tests/` — self-checking `xsim` testbenches, one per controller; run with
  `make sim TB=<name>` from `fpga/` (see [unit_tests/README.md](unit_tests/README.md)).

## Debug core (ILA)

Nets tagged `(* mark_debug = "true" *)` are offered to the Vivado debug core
during synthesis (**SYNTHESIS → Set Up Debug**); the inserted probes are written
back into `constraints/xillydemo.xdc`. The chip Quad-SPI pins (`chip_sck`,
`chip_csb`, `chip_sd[3:0]`), the PLL serial lines, and the controller FIFO data
nets carry the attribute, so Vivado offers to create an ILA automatically during
implementation. Background:
[../doc/vivado/hw_debugger/doc_vivado_hwdebugger.md](../doc/vivado/hw_debugger/doc_vivado_hwdebugger.md).

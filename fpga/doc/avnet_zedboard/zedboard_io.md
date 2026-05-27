# Brief summary of Zedboard IO functionality

## References
* [zynq7000_selectIO.pdf](https://www.xilinx.com/support/documentation/user_guides/ug471_7Series_SelectIO.pdf)

## Important specs
* Zedboard has HP (high performance; thus high speed) and HR (high range banks). In Zedboard these are resp. mapped to the FMC and PMOD headers.
* DCI = digital controlled impedance

## Available IO cells
Can be viewed at [zynq7000_selectIO.pdf,pg.34]
* OBUF: output buffer
* OBUFT: 3-state output buffer
* IOBUF: bidirectional buffer with active-high 3-state pin T

#### Special primitives
* OSERDES2

## Cell attributes

Which attributes can be set in the .xdc constraint file?

* LOC: location mapping
* IOSTANDARD: `INST <IO_BUFFER_INST_NAME> IOSTANDARD = "<LVCMOS18|LVCMOS33|..>"`
* IBUF_LOW_PWR: `INST <IO_BUFFER_INST_NAME> IBUF_LOW_PWR=[TRUE|FALSE]"` (default TRUE); optimizes power vs performance
* SLEW: `INST <IO_BUFFER_INST_NAME> SLEW = "<SLOW|FAST>"` (default SLOW)
* DRIVE: `INST <IO_BUFFER_INST_NAME> SLEW = "<SLOW|FAST>"`
  - note: HP bank LVCMOS18 has max 16mA current drive; the HR bank can go up to 24mA

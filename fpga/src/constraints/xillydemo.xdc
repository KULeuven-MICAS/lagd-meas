create_clock -name gclk -period 10 [get_ports "clk_100"]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets "clk_100"]

# Vivado constraints unrelated clocks. So set false paths.
set_false_path -from [get_clocks clk_fpga_1] -to [get_clocks vga_clk_ins/*]
set_false_path -from [get_clocks vga_clk_ins/*] -to [get_clocks clk_fpga_1]

################################################################################
## XILLYBUS FIXED ZYNC IO MAPPING
################################################################################
# The VGA outputs are turned into an analog voltage by virtue of a resistor
# network, so the flip flops driving these must sit in the IOBs to minimize
# timing skew. The RTL code should handle this, but the constraint below
# is there to fail if something goes wrong about this.
set_output_delay 5.5 [get_ports {vga*}]

set_property -dict "PACKAGE_PIN Y9 IOSTANDARD LVCMOS33" [get_ports "clk_100"]
set_property -dict "PACKAGE_PIN T22 IOSTANDARD LVCMOS33" [get_ports "GPIO_LED[0]"]
set_property -dict "PACKAGE_PIN T21 IOSTANDARD LVCMOS33" [get_ports "GPIO_LED[1]"]
set_property -dict "PACKAGE_PIN U22 IOSTANDARD LVCMOS33" [get_ports "GPIO_LED[2]"]
set_property -dict "PACKAGE_PIN U21 IOSTANDARD LVCMOS33" [get_ports "GPIO_LED[3]"]
set_property -dict "PACKAGE_PIN Y21 IOSTANDARD LVCMOS33" [get_ports "vga4_blue[0]"]
set_property -dict "PACKAGE_PIN Y20 IOSTANDARD LVCMOS33" [get_ports "vga4_blue[1]"]
set_property -dict "PACKAGE_PIN AB20 IOSTANDARD LVCMOS33" [get_ports "vga4_blue[2]"]
set_property -dict "PACKAGE_PIN AB19 IOSTANDARD LVCMOS33" [get_ports "vga4_blue[3]"]
set_property -dict "PACKAGE_PIN AB22 IOSTANDARD LVCMOS33" [get_ports "vga4_green[0]"]
set_property -dict "PACKAGE_PIN AA22 IOSTANDARD LVCMOS33" [get_ports "vga4_green[1]"]
set_property -dict "PACKAGE_PIN AB21 IOSTANDARD LVCMOS33" [get_ports "vga4_green[2]"]
set_property -dict "PACKAGE_PIN AA21 IOSTANDARD LVCMOS33" [get_ports "vga4_green[3]"]
set_property -dict "PACKAGE_PIN V20 IOSTANDARD LVCMOS33" [get_ports "vga4_red[0]"]
set_property -dict "PACKAGE_PIN U20 IOSTANDARD LVCMOS33" [get_ports "vga4_red[1]"]
set_property -dict "PACKAGE_PIN V19 IOSTANDARD LVCMOS33" [get_ports "vga4_red[2]"]
set_property -dict "PACKAGE_PIN V18 IOSTANDARD LVCMOS33" [get_ports "vga4_red[3]"]
set_property -dict "PACKAGE_PIN Y19 IOSTANDARD LVCMOS33" [get_ports "vga_vsync"]
set_property -dict "PACKAGE_PIN AA19 IOSTANDARD LVCMOS33" [get_ports "vga_hsync"]

# IMPORTANT: Since four LEDs are taken by the Xillybus IP core, the pin
# placement doesn't match the one given by Digilent.

# GPIO pin to reset the USB OTG PHY

set_property -dict "PACKAGE_PIN G17 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[0]"]

# On-board OLED

set_property -dict "PACKAGE_PIN U11 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[1]"]
set_property -dict "PACKAGE_PIN U12 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[2]"]
set_property -dict "PACKAGE_PIN U9 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[3]"]
set_property -dict "PACKAGE_PIN U10 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[4]"]
set_property -dict "PACKAGE_PIN AB12 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[5]"]
set_property -dict "PACKAGE_PIN AA12 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[6]"]

# On-board LEDs. Note that only for LEDs are allocated, as opposed to
# Digilent's eight, and all placements that follow are shifted by four.
# There was no other choice, as the tools don't allow unplaced PS GPIO pins.
#   [TBOS EDIT]: swap PS_GPIO[7..10] with unused HDMI "video data input" pins
#                 this way we can acces LEDs LD[7:4] with user_led[3:0]
set_property -dict "PACKAGE_PIN Y13 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[7]"]
set_property -dict "PACKAGE_PIN AA13 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[8]"]
set_property -dict "PACKAGE_PIN AA14 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[9]"]
set_property -dict "PACKAGE_PIN Y14 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[10]"]
set_property -dict "PACKAGE_PIN V22 IOSTANDARD LVCMOS33" [get_ports "user_led[0]"]
set_property -dict "PACKAGE_PIN W22 IOSTANDARD LVCMOS33" [get_ports "user_led[1]"]
set_property -dict "PACKAGE_PIN U19 IOSTANDARD LVCMOS33" [get_ports "user_led[2]"]
set_property -dict "PACKAGE_PIN U14 IOSTANDARD LVCMOS33" [get_ports "user_led[3]"]

# On-board Slide Switches

set_property -dict "PACKAGE_PIN F22 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[11]"]
set_property -dict "PACKAGE_PIN G22 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[12]"]
set_property -dict "PACKAGE_PIN H22 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[13]"]
set_property -dict "PACKAGE_PIN F21 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[14]"]
set_property -dict "PACKAGE_PIN H19 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[15]"]
set_property -dict "PACKAGE_PIN H18 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[16]"]
set_property -dict "PACKAGE_PIN H17 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[17]"]
set_property -dict "PACKAGE_PIN M15 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[18]"]

# On-board Left, Right, Up, Down, and Select Pushbuttons

set_property -dict "PACKAGE_PIN N15 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[19]"]
set_property -dict "PACKAGE_PIN R18 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[20]"]
set_property -dict "PACKAGE_PIN T18 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[21]"]
set_property -dict "PACKAGE_PIN R16 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[22]"]
set_property -dict "PACKAGE_PIN P16 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[23]"]

# Pmod JA
# JA1-JA4, JA7-JA10 are unused (chip SPI moved to the FMC connector).
# PS_GPIO[24:29] are left without physical-pin assignments; those PS EMIO
# indices will float (harmless – the PS will not configure them as outputs).

set_property -dict "PACKAGE_PIN AB9  IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[30]"]
set_property -dict "PACKAGE_PIN AA8  IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[31]"]

# Switches (PS_GPIO[11:18]) and buttons (PS_GPIO[19:21]) are physical inputs.
# Declare false paths to suppress irrelevant timing warnings.
set_false_path -from [get_ports "PS_GPIO[11]"]
set_false_path -from [get_ports "PS_GPIO[12]"]
set_false_path -from [get_ports "PS_GPIO[13]"]
set_false_path -from [get_ports "PS_GPIO[14]"]
set_false_path -from [get_ports "PS_GPIO[15]"]
set_false_path -from [get_ports "PS_GPIO[16]"]
set_false_path -from [get_ports "PS_GPIO[17]"]
set_false_path -from [get_ports "PS_GPIO[18]"]
set_false_path -from [get_ports "PS_GPIO[19]"]
set_false_path -from [get_ports "PS_GPIO[20]"]
set_false_path -from [get_ports "PS_GPIO[21]"]

# Pmod JB

set_property -dict "PACKAGE_PIN W12 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[32]"]
set_property -dict "PACKAGE_PIN W11 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[33]"]
set_property -dict "PACKAGE_PIN V10 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[34]"]
set_property -dict "PACKAGE_PIN W8 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[35]"]
set_property -dict "PACKAGE_PIN V12 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[36]"]
set_property -dict "PACKAGE_PIN W10 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[37]"]
set_property -dict "PACKAGE_PIN V9 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[38]"]
set_property -dict "PACKAGE_PIN V8 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[39]"]

# Pmod JC

set_property -dict "PACKAGE_PIN AB7 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[40]"]
set_property -dict "PACKAGE_PIN AB6 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[41]"]
set_property -dict "PACKAGE_PIN Y4 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[42]"]
set_property -dict "PACKAGE_PIN AA4 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[43]"]
set_property -dict "PACKAGE_PIN R6 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[44]"]
set_property -dict "PACKAGE_PIN T6 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[45]"]
set_property -dict "PACKAGE_PIN T4 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[46]"]
set_property -dict "PACKAGE_PIN U4 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[47]"]

# Pmod JD

set_property -dict "PACKAGE_PIN V7 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[48]"]
set_property -dict "PACKAGE_PIN W7 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[49]"]
set_property -dict "PACKAGE_PIN V5 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[50]"]
set_property -dict "PACKAGE_PIN V4 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[51]"]
set_property -dict "PACKAGE_PIN W6 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[52]"]
set_property -dict "PACKAGE_PIN W5 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[53]"]
set_property -dict "PACKAGE_PIN U6 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[54]"]
set_property -dict "PACKAGE_PIN U5 IOSTANDARD LVCMOS33" [get_ports "PS_GPIO[55]"]

# Pin for detecting USB OTG over-current condition

set_property -dict "PACKAGE_PIN L16 IOSTANDARD LVCMOS33" [get_ports "otg_oc"]

# Pins connected to sound chip
set_property -dict "PACKAGE_PIN AB1 IOSTANDARD LVCMOS33" [get_ports "smbus_addr[0]"]
set_property -dict "PACKAGE_PIN Y5 IOSTANDARD LVCMOS33" [get_ports "smbus_addr[1]"]
set_property -dict "PACKAGE_PIN AB4 IOSTANDARD LVCMOS33" [get_ports "smb_sclk"]
set_property -dict "PACKAGE_PIN AB5 IOSTANDARD LVCMOS33" [get_ports "smb_sdata"]

set_property -dict "PACKAGE_PIN Y8 IOSTANDARD LVCMOS33" [get_ports "audio_dac"]
set_property -dict "PACKAGE_PIN AA7 IOSTANDARD LVCMOS33" [get_ports "audio_adc"]
set_property -dict "PACKAGE_PIN AA6 IOSTANDARD LVCMOS33" [get_ports "audio_bclk"]
set_property -dict "PACKAGE_PIN Y6 IOSTANDARD LVCMOS33" [get_ports "audio_lrclk"]
set_property -dict "PACKAGE_PIN AB2 IOSTANDARD LVCMOS33" [get_ports "audio_mclk"]

################################################################################
## Pins connected to the FMC connector
################################################################################
## -- DAC
set_property PACKAGE_PIN B22 [get_ports dac1_sclk]
set_property PACKAGE_PIN A21 [get_ports dac1_sdin]
set_property PACKAGE_PIN C15 [get_ports dac1_sdo]
set_property PACKAGE_PIN A22 [get_ports dac1_syncbar]
set_property PACKAGE_PIN B15 [get_ports dac2_sclk]
set_property PACKAGE_PIN B17 [get_ports dac2_sdin]
set_property PACKAGE_PIN B16 [get_ports dac2_sdo]
set_property PACKAGE_PIN B21 [get_ports dac2_syncbar]

## -- ADC
set_property PACKAGE_PIN E21 [get_ports adc1_sclk]
set_property PACKAGE_PIN D22 [get_ports adc1_sdin]
set_property PACKAGE_PIN E18 [get_ports adc1_sdo]
set_property PACKAGE_PIN D21 [get_ports adc1_csbar]
set_property PACKAGE_PIN A18 [get_ports adc1_convstbar]
set_property PACKAGE_PIN C22 [get_ports adc1_status]
## ADC2 dropped: its pins P17/P18 conflict with chip-SPI on FMC H7/H8.
## ADC2 signals are tied off inside xillydemo.v (no top-level ports, no constraints).
set_property PACKAGE_PIN A19 [get_ports adc3_sdin]
set_property PACKAGE_PIN C17 [get_ports adc3_sdo]
set_property PACKAGE_PIN A16 [get_ports adc3_csbar]
set_property PACKAGE_PIN C18 [get_ports adc3_convstbar]
set_property PACKAGE_PIN A17 [get_ports adc3_status]

## -- CHIP QUAD-SPI (freq_sel_controller + spi_image_tester → custom chip SPI slave)
##    Routed over the FMC-LPC connector to the UPS daughter-card SPI block.
##    IOSTANDARD LVCMOS18 inherited from the bank-34/35 blanket rule below.
##    FMC pin → ZedBoard FPGA pin mapping verified against
##    doc/avnet_zedboard/zedboard_master_UCF_RevC_v3.ucf.
##      FMC pin H7  / LA02_P (P17) = chip_sck    → UPS_SPI_SCK
##      FMC pin H8  / LA02_N (P18) = chip_csb    → UPS_SPI_CSB
##      FMC pin H10 / LA04_P (M21) = chip_sd[0]  ↔ UPS_SPI_IO_0  (MOSI / Quad bit 0)
##      FMC pin H11 / LA04_N (M22) = chip_sd[1]  ↔ UPS_SPI_IO_1  (MISO / Quad bit 1)
##      FMC pin H13 / LA07_P (T16) = chip_sd[2]  ↔ UPS_SPI_IO_2
##      FMC pin H14 / LA07_N (T17) = chip_sd[3]  ↔ UPS_SPI_IO_3
set_property PACKAGE_PIN P17 [get_ports chip_sck]
set_property PACKAGE_PIN P18 [get_ports chip_csb]
set_property PACKAGE_PIN M21 [get_ports {chip_sd[0]}]
set_property PACKAGE_PIN M22 [get_ports {chip_sd[1]}]
set_property PACKAGE_PIN T16 [get_ports {chip_sd[2]}]
set_property PACKAGE_PIN T17 [get_ports {chip_sd[3]}]

# SPI outputs / bidirectional data: slow 1 MHz signals; exclude from timing.
set_false_path -to   [get_ports chip_sck]
set_false_path -to   [get_ports chip_csb]
set_false_path -to   [get_ports {chip_sd[*]}]
set_false_path -from [get_ports {chip_sd[*]}]

################################################################################
## FMC PIN PROPERTIES
################################################################################
# Set the drive strength and voltage level of the FMC IO pins

# All IO connected through FMC set to 1.8V CMOS
set_property IOSTANDARD LVCMOS18 [get_ports -of_objects [get_iobanks 34]]
set_property IOSTANDARD LVCMOS18 [get_ports -of_objects [get_iobanks 35]]

# -- DAC
set_property DRIVE 24 [get_ports dac1_sclk]
set_property DRIVE 24 [get_ports dac1_sdin]
set_property DRIVE 24 [get_ports dac1_syncbar]
set_property DRIVE 24 [get_ports dac2_sclk]
set_property DRIVE 24 [get_ports dac2_sdin]
set_property DRIVE 24 [get_ports dac2_syncbar]
# -- ADC
set_property DRIVE 24 [get_ports adc1_sclk]
set_property DRIVE 24 [get_ports adc1_sdin]
set_property DRIVE 24 [get_ports adc1_csbar]
set_property DRIVE 24 [get_ports adc1_convstbar]
set_property DRIVE 24 [get_ports adc3_sdin]
set_property DRIVE 24 [get_ports adc3_csbar]
set_property DRIVE 24 [get_ports adc3_convstbar]

################################################################################
## SPECIFY IO DELAY CONSTRAINTS
################################################################################
#originating from kgoetsch
## -- DAC1 SPI CONTROL --
# setup and hold timing for AD5724 in time unit [ns]
# margins for pcb delay differences
#get clock as comes out:
create_generated_clock -name clk_dac1_sclk -source [get_pins perip_controller_inst/dac1_controller/spi_interface/bufgce_i0/O] -divide_by 1 [get_ports dac1_sclk]
#2 per datasheet, 0.5 margin [data hold]
set_output_delay -clock [get_clocks clk_dac1_sclk] -clock_fall -min -add_delay -2.500 [get_ports dac1_sdin]
#7 per datasheet, 3 margin [data setup]
set_output_delay -clock [get_clocks clk_dac1_sclk] -clock_fall -max -add_delay 10.000 [get_ports dac1_sdin]
#13 per datasheet, 0.5 margin [syncb hold]
set_output_delay -clock [get_clocks clk_dac1_sclk] -clock_fall -min -add_delay -13.500 [get_ports dac1_syncbar]
#13 per datasheet, 2 margin [syncb setup]
set_output_delay -clock [get_clocks clk_dac1_sclk] -clock_fall -max -add_delay 15.000 [get_ports dac1_syncbar]

## -- DAC2 SPI CONTROL --
create_generated_clock -name clk_dac2_sclk -source [get_pins perip_controller_inst/dac2_controller/spi_interface/bufgce_i0/O] -divide_by 1 [get_ports dac2_sclk]
#margins for pcb delay differences
#2 per datasheet, 0.5 margin
set_output_delay -clock [get_clocks clk_dac2_sclk] -clock_fall -min -add_delay -2.500 [get_ports dac2_sdin]
#7 per datasheet, 3 margin
set_output_delay -clock [get_clocks clk_dac2_sclk] -clock_fall -max -add_delay 10.000 [get_ports dac2_sdin]
#13 per datasheet, 0.5 margin
set_output_delay -clock [get_clocks clk_dac2_sclk] -clock_fall -min -add_delay -13.500 [get_ports dac2_syncbar]
#13 per datasheet, 2 margin
set_output_delay -clock [get_clocks clk_dac2_sclk] -clock_fall -max -add_delay 15.000 [get_ports dac2_syncbar]

#originating from kgoetsch
## -- ADC1 SPI CONTROL --
# setup and hold timing for ADS833x in time unit [ns]
# margins for pcb delay differences
create_generated_clock -name clk_adc1_clk -source [get_pins perip_controller_inst/bufgce_adc_sclk/O] -divide_by 1 [get_ports adc1_sclk]
#tsu4 (+0.5) th3 (+2) [sdin setup and hold]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -min -add_delay -8.500 [get_ports adc1_sdin]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -max -add_delay 10.000 [get_ports adc1_sdin]
#tsu5. (+1) [csbar setup]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -min -add_delay -11.000 [get_ports adc1_csbar]
#tsu3 (+1) [csbar hold most strict criterium]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -max -add_delay 9.000 [get_ports adc1_csbar]
#text in 9.4.2 (+2)
set_output_delay -clock [get_clocks clk_adc1_clk] -max -add_delay 22.000 [get_ports adc1_convstbar]
set_output_delay -clock [get_clocks clk_adc1_clk] -min -add_delay 0.000 [get_ports adc1_convstbar]
#td1 and td2 [sdo input delay]
set_input_delay -clock [get_clocks clk_adc1_clk] -clock_fall -min -add_delay 3.000 [get_ports adc1_sdo]
set_input_delay -clock [get_clocks clk_adc1_clk] -clock_fall -max -add_delay 22.000 [get_ports adc1_sdo]
##eoc (status) synchronized on fpga with synchronizer
##set_input_delay -clock [get_clocks clk_pl_1] -clock_fall -min -add_delay  3.000 [get_ports adc1_status]
##set_input_delay -clock [get_clocks clk_pl_1] -clock_fall -max -add_delay 22.000 [get_ports adc1_status]

## -- ADC2 SPI CONTROL: dropped (pins reclaimed for chip-SPI on FMC H7/H8) --

## -- ADC3 SPI CONTROL --
# shared sclk
#create_generated_clock -name clk_adc1_clk -source [get_pins perip_controller_inst/bufgce_adc_sclk/O] -divide_by 1 [get_ports adc1_sclk]
#tsu4 (+0.5) th3 (+2) [sdin setup and hold]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -min -add_delay -8.500 [get_ports adc3_sdin]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -max -add_delay 10.000 [get_ports adc3_sdin]
#tsu5. (+1) [csbar setup]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -min -add_delay -11.000 [get_ports adc3_csbar]
#tsu3 (+1) [csbar hold most strict criterium]
set_output_delay -clock [get_clocks clk_adc1_clk] -clock_fall -max -add_delay 9.000 [get_ports adc3_csbar]
#text in 9.4.2 (+2)
set_output_delay -clock [get_clocks clk_adc1_clk] -max -add_delay 22.000 [get_ports adc3_convstbar]
set_output_delay -clock [get_clocks clk_adc1_clk] -min -add_delay 0.000 [get_ports adc3_convstbar]
#td1 and td2 [sdo input delay]
set_input_delay -clock [get_clocks clk_adc1_clk] -clock_fall -min -add_delay 3.000 [get_ports adc3_sdo]
set_input_delay -clock [get_clocks clk_adc1_clk] -clock_fall -max -add_delay 22.000 [get_ports adc3_sdo]
##eoc (status) synchronized on fpga with synchronizer
##set_input_delay -clock [get_clocks clk_pl_1] -clock_fall -min -add_delay  3.000 [get_ports adc1_status]
##set_input_delay -clock [get_clocks clk_pl_1] -clock_fall -max -add_delay 22.000 [get_ports adc1_status]

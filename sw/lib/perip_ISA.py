# ISA of the periphery controller

# Available OPCODE (3b):

dac_config      = 0
adc_command     = 1     # write command = short SPI command = use to select the channel
adc_config      = 2     # write configuration = long SPI command = use to configure ADC
adc_sample      = 3
led_ctrl        = 14
test_writeback  = 15

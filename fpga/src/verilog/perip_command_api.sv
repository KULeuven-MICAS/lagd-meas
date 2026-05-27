/*
PERIP_COMMAND_API
  Separate file combining API commands send over the Xillybus PERIPHERY FIFO

CHANGELOG
v1.0, 17-12-2021  Start with simple example
v1.1, 20-12-2021  Insert PCB supply DAC and ADC commands
*/

// OPCODE
//  I foresee 4b opcode for different commands
enum bit[3:0] {
    PCB_DAC_COMMAND             = 4'b0000,  // send command to DAC on PCB
    PCB_ADC_COMMAND             = 4'b0001,  // send command to ADC on PCB (current implementation: which channel to start acquisition)
    PCB_ADC_CONFIG              = 4'b0010,  // send configuration to ADC on PCB
    PCB_ADC_SAMPLE              = 4'b0011,  // sample current selected ADC channel
    LED_CTRL                    = 4'b1110,  // Control the LEDs
    TEST_WRITEBACK_PERIPFIFO    = 4'b1111   // Test writeback of FIFO data
} e_perip_opcode;

// OPCODE DEPENDENT COMMANDS
//  perip_command packet structure, one per opcode:
//    naming: i_<opcode_name>_t: (i = instruction; t = typedef)
//    always needs to be 32b wide!
typedef struct packed {
    bit[3:0] opcode;
    bit bus;              // DAC bus: 0:DAC_LV or 1:DAC_MV
    bit[2:0] channel;     // DAC channel; 3b to support 2x daisy chain; only 2 LSB propagate to SPI cmd
    bit[4:0] empty;
    bit[2:0] register;    // REG[2..0] SPI command
    bit[15:0] data;       // 16b data SPI command
} dac_command_t;

typedef struct packed {
    bit[3:0] opcode;
    bit[1:0] bus;         // ADC bus: 1: ADC_LV, 2: ADC_MV, 3: ADC_BIAS
    bit[2:0] channel;     // ADC channel
    bit[10:0] empty;
    bit[11:0] conf;       // 12b CFR register (see datasheet ADS833x, table 5.)
} adc_config_t;

typedef struct packed {
    bit[3:0] opcode;
    bit[1:0] bus;         // ADC bus: 1: ADC_LV, 2: ADC_MV, 3: ADC_BIAS
    bit[2:0] channel;
    bit[22:0] length;     // nr samples; max 2^23-1 = a lot
} adc_sample_t;

typedef struct packed{
    bit[3:0] opcode;
    bit[23:0] empty;
    bit[3:0] user_led;    // Requested LED value
} led_ctrl_t;


// PERIP_COMMAND
//  Create the perip_command typedef
//  union makes that an t_perip_command can be interpret as any of the given 32b typedefs
//  look into the perip_controller for examples, it significantly increases code readability
typedef union packed{
    dac_command_t     dac;
    adc_config_t      adc_conf;
    adc_sample_t      adc_sample;
    led_ctrl_t        led_ctrl;
    logic[31:0]       bitwise;
} perip_command_t;

/*
CHIP_COMMAND_API
  Separate file combining API commands send over the Xillybus CHIP FIFO

CHANGELOG
v1.0, 17-12-2021  Start with simple example
*/

// OPCODE
//  I foresee 4b opcode for different commands
enum bit[3:0] {
    AFE_CONFIG                = 4'b0000,  // Set misc config for AFE CHIP (not CONFIG SHIFTREG!)
    TEST_WRITEBACK_CHIPFIFO   = 4'b1111   // Test writeback of FIFO data
} e_chip_opcode;

// OPCODE DEPENDENT COMMANDS
//  chip_command packet structure, one per opcode:
//    naming: i_<opcode_name>_t: (i = instruction; t = typedef)
//    always needs to be 32b wide!
typedef struct packed{
    bit[3:0]    opcode;       // 4b opcode
    bit[25:0]   empty;
    bit         afe_clk_en;   // enable the afe_clk
    bit         afe_rstn;     // direct control afe_rstn
} afe_config_t;


// CHIP_COMMAND
//  Create the chip_command typedef
//  union makes that an t_chip_command can be interpret as any of the given 32b typedefs
//  look into the chip_controller for examples, it significantly increases code readability
typedef union packed{
    afe_config_t  afe_config;
    logic[31:0]   bitwise;
} chip_command_t;

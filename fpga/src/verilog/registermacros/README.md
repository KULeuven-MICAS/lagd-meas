<!-- Author: Thomas Bos <2022> -->

A register module `reg_arstn` with parameters for width and reset value (as well as a switch to use increasing indices instead), and posedge sensitive clk, asynchronous active low arst_n_in, wen, and din inputs and qout output.

A duplicate file `register_and_macros_xilinx.sv` with register module `reg_rst` is added to be used in Xilinx FPGA projects. FPGA's typically prefer synchronous over asynchronous reset flipflops. Identical macros `REG_ALWAYS_WRITE`, `REG`, ... are available. Disclaimer: only source one of both register_and_macros.sv files

Together with some verilog macro's to quickly instantiate these.
```verilog
//make available by
`include "register_and_macros.sv"
//this can be done in every file where you need it, or just in the first compiled file only

`REG_ALWAYS_WRITE(32, test);
//creates code:
logic [32-1:0] test_next, test;
reg_arstn #(.WIDTH(32)) next_r(.clk(clk), .arst_n_in(arst_n_in), .din(test_next), .qout(test), .wen(1));
//at which point 'test' can be used as reg output and 'test_next' as reg input

`REG(32, test);
//creates code:
logic [32-1:0] test_next, test;
logic test_we;
reg_arstn #(.WIDTH(32)) next_r(.clk(clk), .arst_n_in(arst_n_in), .din(test_next), .qout(test), .wen(test_we));
//at which point 'test' can be used as reg output and 'test_next' as reg input, and 'test_we' as the write enable of the register

//variants UPREG_ALWAYS_WRITE and UPREG are similar but with increasing indices (for instance [0:32-1])

//not instantiating the register module, but usefull nevertheless:
`DELAY(test, 10);
//creates code:
logic [0:10][$bits(test)-1:0] test_delay_line;
assign test_delay_line[0] = test;
generate
  genvar test_delay_genvar;
  for (test_delay_genvar = 1; test_delay_genvar <= 10; test_delay_genvar = test_delay_genvar + 1)
  begin
      always @ (posedge clk or negedge arst_n_in) begin
        if(arst_n_in==0) begin
          test_delay_line[test_delay_genvar] <=  '0;
        end else begin
          test_delay_line[test_delay_genvar] <=  test_delay_line[test_delay_genvar - 1];
        end
      end
  end
endgenerate
//at which point test_delay_line[0] equals test, test_delay_line[1] a 1 cycle delayed version of test, test_delay_line[2] a 2 cycle delayed version of test, ... up to the given 10
//Note: reset values of delayed versions are all 0
//Note: the test_delay_line[...] signals have decreasing indices, possible unlike test itself.
//Note: if the delay line is longer than actually used, synthesis tools should automatically remove unused registers for you. Nevertheless it's of course better to keep things tidy and not make them  unnecessary long in the first palce.
```

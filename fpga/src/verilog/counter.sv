//`ifndef REG
//`include "register_xilinx_macros.sv"
//`endif

module bv_counter
  #(
    parameter integer WIDTH = 32
  )
  (
    input logic clk,
    (* direct_reset = "yes" *) input logic rst,
    input logic counter_inc,
    input logic counter_load,
    input logic [WIDTH-1:0] counter_load_value,
    output logic [WIDTH-1:0] counter_val
  );
  
    `REG(WIDTH, counter_reg, clk);
    assign counter_reg_next = counter_load ? counter_load_value : counter_reg+1;
    assign counter_reg_we = counter_load || counter_inc;

    assign counter_val = counter_reg;

endmodule

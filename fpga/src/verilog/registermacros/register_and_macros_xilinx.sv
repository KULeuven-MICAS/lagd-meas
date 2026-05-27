`ifndef REG
module reg_rst #(
  parameter integer WIDTH     = 20,
  parameter integer RESET_VAL = 'b0,
  parameter bit increasing_indices = 0
     )(
        input  logic              clk,
        (* direct_reset = "yes" *)input  logic              rst,
        input  logic [increasing_indices?0:WIDTH-1: increasing_indices?WIDTH-1:0] din,
        output logic [increasing_indices?0:WIDTH-1: increasing_indices?WIDTH-1:0] qout,
        input  logic 	     				wen
  );

  logic [WIDTH-1:0] r;

  always_ff @(posedge clk) begin
     if(rst==1)begin
        r <= RESET_VAL;
     end else begin
        if(wen)
          r <= din;
     end
  end
  assign qout = r;
endmodule



`define REG_ALWAYS_WRITE(raw_width, raw_name, clkname) \
logic [raw_width-1:0] ``raw_name``_next, raw_name;\
reg_rst #(.WIDTH(raw_width)) ``raw_name``_r(.clk(clkname), .rst(rst), .din(raw_name_next), .qout(raw_name), .wen(1))

`define REG(r_width, r_name, clkname) \
logic [r_width-1:0] ``r_name``_next, r_name;\
logic ``r_name``_we;\
reg_rst #(.WIDTH(r_width)) ``r_name``_r(.clk(clkname), .rst(rst), .din(``r_name``_next), .qout(r_name), .wen(``r_name``_we))

`define UPREG(r_width, r_name, clkname) \
logic [0:r_width-1] ``r_name``_next, r_name;\
logic ``r_name``_we;\
reg_rst #(.WIDTH(r_width), .increasing_indices(1)) ``r_name``_r(.clk(clkname), .rst(rst), .din(``r_name``_next), .qout(r_name), .wen(``r_name``_we))

`define UPREG_ALWAYS_WRITE(raw_width, raw_name, clkname) \
logic [0:raw_width-1] ``raw_name``_next, raw_name;\
reg_rst #(.WIDTH(raw_width), .increasing_indices(1)) ``raw_name``_r(.clk(clkname), .rst(rst), .din(raw_name_next), .qout(raw_name), .wen(1))

`define DELAY(signal, n, clkname)\
logic [0:n][$bits(signal)-1:0] ``signal``_delay_line;\
assign ``signal``_delay_line[0] = signal;\
generate\
  genvar ``signal``_delay_genvar;\
  for (``signal``_delay_genvar = 1; ``signal``_delay_genvar <= n; ``signal``_delay_genvar = ``signal``_delay_genvar + 1)\
  begin\
      always @ (posedge clkname) begin\
        if(rst==1) begin\
          ``signal``_delay_line[``signal``_delay_genvar] <=  '0;\
        end else begin\
          ``signal``_delay_line[``signal``_delay_genvar] <=  ``signal``_delay_line[``signal``_delay_genvar - 1];\
        end\
      end\
  end\
endgenerate


`endif

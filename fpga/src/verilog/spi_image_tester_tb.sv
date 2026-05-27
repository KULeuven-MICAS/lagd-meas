// Self-checking testbench for spi_image_tester.sv (Verilator / SV).
// Models a Quad SPI slave that mirrors chip behaviour enough for write + verify:
//   • Captures quad program writes (cmd 0x02) into shadow RAM (MSByte first).
//   • Echoes shadow RAM on fast-read (0x0B) with dummy cycles + matching nibble order.

`include "image_info.vh"

module spi_image_tester_tb;

  localparam int CLK_HZ = 100_000_000;
  localparam time TCLK = 10ns; // 100 MHz

  localparam int NUM_BYTES = `IMAGE_NUM_BYTES;
  localparam int DATA_NIBBLES = 2 * NUM_BYTES;
  localparam int DEB_TICKS = CLK_HZ / 1000 * 20;

  logic clk;
  logic rst;
  logic btn_write;
  logic btn_verify;

  logic spi_sck;
  logic spi_csb;
  logic [3:0] sd_out;
  logic sd_oe;
  logic [3:0] sd_in;

  logic busy;
  logic pass_;
  logic fail_;

  logic [7:0] golden_rom [0:NUM_BYTES-1];
  initial begin
    $readmemh(`IMAGE_FILE, golden_rom);
  end

  spi_image_tester dut (
    .clk(clk),
    .rst(rst),
    .btn_write(btn_write),
    .btn_verify(btn_verify),
    .spi_sck(spi_sck),
    .spi_csb(spi_csb),
    .sd_out(sd_out),
    .sd_oe(sd_oe),
    .sd_in(sd_in),
    .busy(busy),
    .pass(pass_),
    .fail(fail_)
  );

  // ---------------------------------------------------------------------------
  // SPI slave — track edges on TB clock
  // ---------------------------------------------------------------------------
  logic spi_sck_d;
  logic spi_csb_d;

  wire sck_rise = spi_sck && !spi_sck_d;
  wire sck_fall = !spi_sck && spi_sck_d;
  wire csb_rise = spi_csb && !spi_csb_d;
  wire csb_fall = !spi_csb && spi_csb_d;

  logic [7:0] shadow_mem [0:NUM_BYTES-1];

  localparam int CAP_W = 128;
  logic [3:0] cap_nib [0:CAP_W-1];
  logic [$clog2(CAP_W)-1:0] nib_wr_idx;

  logic [$clog2(512)-1:0] sck_rise_while_csb_lo;
  logic [$clog2(512)-1:0] last_rise_cnt;

  initial begin
    for (int i = 0; i < NUM_BYTES; i++) shadow_mem[i] = 8'h00;
  end

  always_ff @(posedge clk) begin
    spi_sck_d <= spi_sck;
    spi_csb_d <= spi_csb;
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      nib_wr_idx <= '0;
      sck_rise_while_csb_lo <= '0;
      last_rise_cnt <= '0;
      sd_in <= 4'h0;
    end else begin
      if (csb_rise) begin
        unique case (nib_wr_idx)
          (10 + DATA_NIBBLES): begin
            if ({cap_nib[0], cap_nib[1]} === 8'h02) begin
              for (int b = 0; b < NUM_BYTES; b++) begin
                shadow_mem[b] <= {cap_nib[10 + 2 * b], cap_nib[10 + 2 * b + 1]};
              end
            end
          end
          default: ;
        endcase
      end

      if (csb_fall) begin
        nib_wr_idx <= '0;
        sck_rise_while_csb_lo <= '0;
        last_rise_cnt <= '0;
        sd_in <= 4'h0;
      end else begin
        if (!spi_csb && sck_rise) begin
          last_rise_cnt <= sck_rise_while_csb_lo + 1'b1;
          sck_rise_while_csb_lo <= sck_rise_while_csb_lo + 1'b1;

          if (sd_oe && nib_wr_idx != CAP_W'(CAP_W)) begin
            cap_nib[nib_wr_idx] <= sd_out;
            nib_wr_idx <= nib_wr_idx + 1'b1;
          end
        end

        // Drive read data before each rising edge where the master samples:
        // falls after rises 43..42+DATA_NIBBLES correspond to nibbles 0..DATA_NIBBLES-1.
        if (!spi_csb && sck_fall && !sd_oe) begin
          if ((last_rise_cnt >= 43) && (last_rise_cnt < 43 + DATA_NIBBLES)) begin
            automatic int nib_ix = int'(last_rise_cnt) - 43;
            automatic int b = nib_ix / 2;
            automatic logic hi_nib = (nib_ix[0] == 1'b0);
            sd_in <= hi_nib ? shadow_mem[b][7:4] : shadow_mem[b][3:0];
          end else begin
            sd_in <= 4'h0;
          end
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // Stimulus
  // ---------------------------------------------------------------------------
  task static pulse_btn_write();
    begin
      repeat (DEB_TICKS) @(posedge clk);
      btn_write = 1'b0;
      repeat (DEB_TICKS) @(posedge clk);
      btn_write = 1'b1;
      repeat (DEB_TICKS) @(posedge clk);
      btn_write = 1'b0;
      repeat (DEB_TICKS) @(posedge clk);
    end
  endtask

  task static pulse_btn_verify();
    begin
      repeat (DEB_TICKS) @(posedge clk);
      btn_verify = 1'b0;
      repeat (DEB_TICKS) @(posedge clk);
      btn_verify = 1'b1;
      repeat (DEB_TICKS) @(posedge clk);
      btn_verify = 1'b0;
      repeat (DEB_TICKS) @(posedge clk);
    end
  endtask

  task static wait_not_busy();
    begin
      while (busy) @(posedge clk);
      repeat (10) @(posedge clk);
    end
  endtask

  int tb_errors;

  initial begin
    tb_errors = 0;
    clk = 1'b0;
    rst = 1'b1;
    btn_write = 1'b0;
    btn_verify = 1'b0;

    forever #(TCLK / 2) clk = ~clk;
  end

  initial begin
    @(posedge clk);
    @(posedge clk);
    rst = 1'b0;

    $display("TB: IMAGE_NUM_BYTES=%0d IMAGE_FILE=%s", NUM_BYTES, `IMAGE_FILE);

    pulse_btn_write();
    wait_not_busy();

    for (int i = 0; i < NUM_BYTES; i++) begin
      if (shadow_mem[i] !== golden_rom[NUM_BYTES - 1 - i]) begin
        $error("TB: shadow_mem[%0d]=%02x expected %02x (MSByte-first wire order)",
               i, shadow_mem[i], golden_rom[NUM_BYTES - 1 - i]);
        tb_errors++;
      end
    end

    pulse_btn_verify();
    wait_not_busy();

    if (!pass_ || fail_) begin
      $error("TB: verify failed (pass=%b fail=%b)", pass_, fail_);
      tb_errors++;
    end else begin
      $display("TB: verify PASS");
    end

    pulse_btn_write();
    wait_not_busy();

    if (tb_errors == 0)
      $display("TB: *** ALL CHECKS PASSED ***");
    else
      $error("TB: *** FINISHED WITH %0d ERROR(S) ***", tb_errors);

    $finish;
  end

endmodule

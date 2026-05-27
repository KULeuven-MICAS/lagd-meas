/*
SPI_IMAGE_TESTER

Drives the custom chip's Quad-SPI slave with two independently triggered
operations: write program (btn_write) and program verify (btn_verify).
Image data is loaded at elaboration time from a $readmemh-format hex file
generated from a program .bin by scripts/bin_to_hex.sh; the byte count is
fixed at synthesis time.

btn_write sequence
  1. Clears latched pass/fail (neutral until next verify completes)
  2. spi_init             – standard 1-bit SPI, 16 clocks; switches chip to Quad mode
  3. 1 ms inter-frame gap
  4. spi_write_image      – Quad SPI write to 32'h8000_0000 (pulse_reset = 0)
  5. busy → 0  (pass/fail stay cleared until verify)

btn_verify sequence
  1. spi_init             – standard 1-bit SPI, 16 clocks; switches chip to Quad mode
  2. 1 ms inter-frame gap
  3. spi_verify_loaded_image – Quad SPI read + streaming compare vs. image ROM
  4. Latch pass/fail on outputs (held until the next btn_write)

Image ROM
  Driven entirely by the generated include file `image_info.vh`:
    `IMAGE_NUM_BYTES – padded byte count (multiple of 4)
    `IMAGE_FILE      – absolute path to the $readmemh-format hex file
  The hex file is one byte per line; image_rom[0] = first byte of the .bin,
  matching the byte order used by spi_write_image / spi_verify_loaded_image
  (rom[N-1] is shipped first on the wire = MSByte of word 0).

  For a 4-byte program 0xDEADBEEF, the file contains EF / BE / AD / DE and
  the wire carries 0xDE 0xAD 0xBE 0xEF.

SPI protocol for write / read frames  (CPOL=0, CPHA=0)
  • cmd  : 8 bits  over 4 data lines = 2 Quad SCK cycles
  • addr : 32 bits over 4 data lines = 8 Quad SCK cycles
  • data : NUM_BYTES×8 bits = DATA_NIBBLES Quad SCK cycles
  • Byte order: MSByte first (big-endian), MSNibble first within each byte

Dummy cycles (read frame only)
  After the last address nibble is sampled, the bus is released (sd_oe=0)
  and 33 full SCK cycles are generated.  The chip shifts out data starting
  on the negedge after the 33rd dummy posedge; the FPGA samples on the 34th
  and subsequent posedges (DATA_NIBBLES nibbles = NUM_BYTES×8 bits).

ROM access
  image_rom is read via a 1-clk-registered synchronous path (idx → BRAM → reg)
  so Vivado infers BRAM for realistic program sizes. Two FSM-managed phase
  bits (wr_phase / rx_phase) sequence high/low nibbles within each byte.

Pin roles (connected via IOBUF in xillydemo.v)
  spi_sck         : SCK output        (always FPGA-driven)
  spi_csb         : chip-select bar   (always FPGA-driven)
  sd_out[3:0]     : quad MOSI data    (FPGA drives during cmd/addr/write-data)
  sd_oe           : 1 = FPGA drives sd_out; 0 = chip drives (read data phase)
  sd_in[3:0]      : quad MISO data    (FPGA samples during read data phase)

  Note: image_info.vh (auto-generated) defines `IMAGE_NUM_BYTES and `IMAGE_FILE.
  It is registered as a global include in scripts/build_batch.tcl, so no
  explicit `\`include` is needed here (and adding one would redefine the
  macros).
*/

module spi_image_tester (
  input  logic        clk,         // 100 MHz system clock
  input  logic        rst,         // synchronous active-high reset

  input  logic        btn_write,   // trigger: init + write program
  input  logic        btn_verify,  // trigger: init + read + verify

  // SPI master (connect via xillydemo.v IOBUF mux)
  output logic        spi_sck,
  output logic        spi_csb,
  output logic [3:0]  sd_out,  // to IOBUF I input
  output logic        sd_oe,   // IOBUF output-enable (1 = drive)
  input  logic [3:0]  sd_in,   // from IOBUF O output

  // Status
  output logic        busy,
  output logic        pass,   // last verify outcome; cleared on btn_write edge
  output logic        fail    // last verify outcome; cleared on btn_write edge
);

  // -------------------------------------------------------------------------
  // Image ROM sizing (from auto-generated image_info.vh)
  // -------------------------------------------------------------------------
  localparam int    NUM_BYTES       = `IMAGE_NUM_BYTES;
  localparam string IMAGE_FILE_PATH = `IMAGE_FILE;

  localparam int DATA_NIBBLES = 2 * NUM_BYTES;
  // seq_cnt must hold the largest of: 15 (init), 9 (cmd+addr), DATA_NIBBLES-1.
  localparam int SEQ_W  = (4 > $clog2(DATA_NIBBLES)) ? 4 : $clog2(DATA_NIBBLES);
  // cur_byte_idx counts byte position from 0..NUM_BYTES-1.
  localparam int BIDX_W = (1 > $clog2(NUM_BYTES))    ? 1 : $clog2(NUM_BYTES);

  // -------------------------------------------------------------------------
  // SPI timing
  // -------------------------------------------------------------------------
  localparam int CLK_HZ     = 100_000_000;
  localparam int SCK_HZ     = 1_000_000;
  localparam int SCK_HALF   = CLK_HZ / SCK_HZ / 2;       // 50 ticks
  localparam int SCK_PERIOD = 2 * SCK_HALF;               // 100 ticks
  localparam int DEB_TICKS  = CLK_HZ / 1000 * 20;        // 20 ms debounce
  localparam int GAP_TICKS  = CLK_HZ / 1000;             // 1 ms inter-frame gap
  localparam int DUMMY_CYCS = 33;                         // read dummy SCK cycles

  // -------------------------------------------------------------------------
  // Fixed SPI frame headers (cmd + addr, 40 bits = 10 Quad nibbles)
  // -------------------------------------------------------------------------
  localparam logic [39:0] WR_CMD_ADDR = {8'h02, 32'h8000_0000};
  localparam logic [39:0] RD_CMD_ADDR = {8'h0B, 32'h8000_0000};
  localparam logic [15:0] INIT_SEQ    = 16'h0101;

  // -------------------------------------------------------------------------
  // Image ROM – initialised from file at synthesis time
  // -------------------------------------------------------------------------
  logic [7:0] image_rom [0:NUM_BYTES-1];
  initial $readmemh(IMAGE_FILE_PATH, image_rom);

  // Registered 1-byte view of image_rom[cur_byte_idx]. Updated by the FSM
  // (cur_byte_idx is set far enough in advance of every use that the 1-clk
  // BRAM latency is hidden — the slowest tick is SCK_PERIOD = 100 clks).
  logic [BIDX_W-1:0] cur_byte_idx;
  logic [7:0]        cur_byte;
  always_ff @(posedge clk) cur_byte <= image_rom[cur_byte_idx];

  // -------------------------------------------------------------------------
  // Buttons: per-button 2-stage synchroniser + debounce + rising-edge strobe
  // -------------------------------------------------------------------------
  logic btn_w_s0, btn_w_s1, btn_w_db, btn_w_db_d, btn_w_rise;
  logic btn_v_s0, btn_v_s1, btn_v_db, btn_v_db_d, btn_v_rise;
  logic [$clog2(DEB_TICKS)-1:0] deb_cnt_w, deb_cnt_v;

  always_ff @(posedge clk) {btn_w_s1, btn_w_s0} <= {btn_w_s0, btn_write};
  always_ff @(posedge clk) {btn_v_s1, btn_v_s0} <= {btn_v_s0, btn_verify};

  always_ff @(posedge clk) begin
    if (rst) begin
      deb_cnt_w <= '0;
      btn_w_db  <= 1'b0;
    end else if (btn_w_s1 == btn_w_db) begin
      deb_cnt_w <= '0;
    end else if (deb_cnt_w == DEB_TICKS - 1) begin
      btn_w_db  <= btn_w_s1;
      deb_cnt_w <= '0;
    end else begin
      deb_cnt_w <= deb_cnt_w + 1;
    end
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      deb_cnt_v <= '0;
      btn_v_db  <= 1'b0;
    end else if (btn_v_s1 == btn_v_db) begin
      deb_cnt_v <= '0;
    end else if (deb_cnt_v == DEB_TICKS - 1) begin
      btn_v_db  <= btn_v_s1;
      deb_cnt_v <= '0;
    end else begin
      deb_cnt_v <= deb_cnt_v + 1;
    end
  end

  always_ff @(posedge clk) {btn_w_db_d, btn_v_db_d} <= {btn_w_db, btn_v_db};
  assign btn_w_rise = btn_w_db & ~btn_w_db_d;
  assign btn_v_rise = btn_v_db & ~btn_v_db_d;

  // -------------------------------------------------------------------------
  // SCK divider (runs only while sck_active)
  // -------------------------------------------------------------------------
  typedef enum logic [3:0] {
    IDLE,
    INIT_TX,   // 1-bit SPI init  (16 clocks)
    INIT_GAP,
    WR_CA,     // Quad write: cmd+addr  (10 nibbles)
    WR_DATA,   // Quad write: image ROM (DATA_NIBBLES nibbles)
    RD_CA,     // Quad read:  cmd+addr  (10 nibbles)
    RD_DUMMY,  // 33 dummy SCK cycles
    RD_DATA,   // Quad receive          (DATA_NIBBLES nibbles)
    RESULT,
    DONE_ST
  } state_t;
  state_t state;

  // 0 = write program (init + write), 1 = verify program (init + read+compare).
  // Captured on the triggering button press and held for the operation.
  logic is_verify;

  wire sck_active = (state == INIT_TX  || state == WR_CA    || state == WR_DATA ||
                     state == RD_CA    || state == RD_DUMMY  || state == RD_DATA);

  logic [$clog2(SCK_PERIOD)-1:0] sck_cnt;

  always_ff @(posedge clk) begin
    if (!sck_active)                    sck_cnt <= '0;
    else if (sck_cnt == SCK_PERIOD - 1) sck_cnt <= '0;
    else                                sck_cnt <= sck_cnt + 1;
  end

  wire sck_rise_tick = sck_active && (sck_cnt == SCK_HALF   - 1);
  wire sck_fall_tick = sck_active && (sck_cnt == SCK_PERIOD - 1);

  // -------------------------------------------------------------------------
  // Datapath registers
  // -------------------------------------------------------------------------
  logic [39:0] ca_sr;      // cmd+addr shift register (10 nibbles, reused for
                            // both write and read frames)
  logic [15:0] init_sr;    // spi_init SR             (16 bits, MSB first)

  logic [SEQ_W-1:0]            seq_cnt;     // nibble / bit down-counter
  logic [5:0]                  dummy_cnt;   // dummy SCK cycle down-counter
  logic [$clog2(GAP_TICKS)-1:0] gap_cnt;
  logic                        all_rx;      // set after last RX nibble sampled

  // Write-side nibble phase: 0 = next outgoing nibble is the high nibble of
  // cur_byte; 1 = next outgoing nibble is the low nibble.
  logic       wr_phase;

  // Read-side nibble assembly:
  //   rx_phase = 0 → the next sd_in[3:0] sample is the high nibble of a new
  //                  byte (latched into rx_hi).
  //   rx_phase = 1 → the next sample completes the byte; compared on the spot
  //                  against cur_byte; mismatch latched sticky.
  logic [3:0] rx_hi;
  logic       rx_phase;
  logic       mismatch;

  // -------------------------------------------------------------------------
  // Main FSM
  // -------------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (rst) begin
      state        <= IDLE;
      spi_sck      <= 1'b0;
      spi_csb      <= 1'b1;
      sd_out       <= 4'h0;
      sd_oe        <= 1'b0;
      busy         <= 1'b0;
      pass         <= 1'b0;
      fail         <= 1'b0;
      seq_cnt      <= '0;
      dummy_cnt    <= '0;
      gap_cnt      <= '0;
      ca_sr        <= '0;
      init_sr      <= '0;
      all_rx       <= 1'b0;
      cur_byte_idx <= '0;
      wr_phase     <= 1'b0;
      rx_hi        <= 4'h0;
      rx_phase     <= 1'b0;
      mismatch     <= 1'b0;
      is_verify    <= 1'b0;

    end else begin
      case (state)

        // ==================================================================
        IDLE: begin
          spi_sck <= 1'b0;
          spi_csb <= 1'b1;
          sd_oe   <= 1'b0;
          sd_out  <= 4'h0;
          busy    <= 1'b0;
          all_rx  <= 1'b0;
          if (btn_w_rise || btn_v_rise) begin
            // Write has priority if both buttons strobe in the same cycle.
            is_verify <= btn_w_rise ? 1'b0 : 1'b1;
            if (btn_w_rise) begin
              pass <= 1'b0;
              fail <= 1'b0;
            end
            init_sr   <= INIT_SEQ;
            seq_cnt   <= SEQ_W'(15);                // 16 bits, index 15..0
            spi_csb   <= 1'b0;
            sd_oe     <= 1'b1;
            sd_out    <= {3'b0, INIT_SEQ[15]};      // pre-drive MSB of cmd 0x01
            busy      <= 1'b1;
            mismatch  <= 1'b0;
            state     <= INIT_TX;
          end
        end

        // ==================================================================
        // spi_init: 1-bit SPI, send INIT_SEQ (16'h0101) MSB-first on SD[0]
        //   16 SCK cycles + 1 extra negedge → CSB=1
        // ==================================================================
        INIT_TX: begin
          if (sck_rise_tick) spi_sck <= 1'b1;
          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            if (seq_cnt == '0) begin
              spi_csb      <= 1'b1;
              sd_oe        <= 1'b0;
              gap_cnt      <= '0;
              // Pre-load cur_byte with rom[NUM_BYTES-1] (MSByte sent first).
              cur_byte_idx <= BIDX_W'(NUM_BYTES - 1);
              state        <= INIT_GAP;
            end else begin
              seq_cnt <= seq_cnt - 1;
              init_sr <= {init_sr[14:0], 1'b0};
              sd_out  <= {3'b0, init_sr[14]};
            end
          end
        end

        // ==================================================================
        // After 1 ms gap, branch on is_verify:
        //   is_verify=0 → start write frame (cmd 0x02 + addr + image data)
        //   is_verify=1 → start read  frame (cmd 0x0B + addr + dummy + data)
        // ==================================================================
        INIT_GAP: begin
          if (gap_cnt == GAP_TICKS - 1) begin
            seq_cnt <= SEQ_W'(9);                   // 10 nibbles, index 9..0
            spi_csb <= 1'b0;
            sd_oe   <= 1'b1;
            if (is_verify) begin
              ca_sr        <= RD_CMD_ADDR;
              sd_out       <= RD_CMD_ADDR[39:36];
              rx_phase     <= 1'b0;
              mismatch     <= 1'b0;
              state        <= RD_CA;
            end else begin
              ca_sr   <= WR_CMD_ADDR;
              sd_out  <= WR_CMD_ADDR[39:36];        // pre-drive nibble 0 (cmd[7:4]=0)
              state   <= WR_CA;
            end
          end else begin
            gap_cnt <= gap_cnt + 1;
          end
        end

        // ==================================================================
        // Write cmd+addr: 10 Quad nibbles.
        // On the extra negedge (seq_cnt==0), the data phase starts immediately
        // (no CSB gap between addr and data per spi_write_image task).
        // The first data nibble (MSNibble of rom[NUM_BYTES-1]) is driven
        // here from cur_byte; WR_DATA takes over from the next SCK cycle and
        // alternates low/high nibbles via wr_phase.
        // ==================================================================
        WR_CA: begin
          if (sck_rise_tick) spi_sck <= 1'b1;
          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            if (seq_cnt == '0) begin
              // Drive first data nibble: high nibble of MSByte (cur_byte was
              // pre-loaded with image_rom[NUM_BYTES-1] during INIT_GAP).
              sd_out   <= cur_byte[7:4];
              wr_phase <= 1'b1;                     // next: low nibble
              seq_cnt  <= SEQ_W'(DATA_NIBBLES - 1);
              state    <= WR_DATA;
            end else begin
              seq_cnt <= seq_cnt - 1;
              ca_sr   <= {ca_sr[35:0], 4'b0};       // shift left one nibble
              sd_out  <= ca_sr[35:32];              // drive next nibble (pre-shift)
            end
          end
        end

        // ==================================================================
        // Write data: DATA_NIBBLES Quad SCK cycles from image ROM.
        //   wr_phase=1 → drive low nibble of cur_byte, then advance to next
        //                byte (decrement cur_byte_idx, cur_byte refreshes
        //                ~1 clk later — plenty of time before next sck_fall).
        //   wr_phase=0 → drive high nibble of new cur_byte.
        //   seq_cnt==0 → extra negedge: deassert CSB, end write frame.
        // ==================================================================
        WR_DATA: begin
          if (sck_rise_tick) spi_sck <= 1'b1;
          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            if (seq_cnt == '0) begin
              spi_csb <= 1'b1;
              sd_oe   <= 1'b0;
              busy    <= 1'b0;
              state   <= DONE_ST;
            end else begin
              seq_cnt <= seq_cnt - 1;
              if (wr_phase) begin
                sd_out   <= cur_byte[3:0];
                wr_phase <= 1'b0;
                if (cur_byte_idx != '0)
                  cur_byte_idx <= cur_byte_idx - 1;
              end else begin
                sd_out   <= cur_byte[7:4];
                wr_phase <= 1'b1;
              end
            end
          end
        end

        // ==================================================================
        // Read cmd+addr: 10 Quad nibbles, then release bus → dummy phase
        // ==================================================================
        RD_CA: begin
          if (sck_rise_tick) spi_sck <= 1'b1;
          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            if (seq_cnt == '0) begin
              sd_oe     <= 1'b0;
              sd_out    <= 4'h0;
              dummy_cnt <= DUMMY_CYCS - 1;
              state     <= RD_DUMMY;
            end else begin
              seq_cnt <= seq_cnt - 1;
              ca_sr   <= {ca_sr[35:0], 4'b0};
              sd_out  <= ca_sr[35:32];
            end
          end
        end

        // ==================================================================
        // 33 full SCK cycles with sd_oe=0 (chip prepares output data)
        // ==================================================================
        RD_DUMMY: begin
          sd_oe <= 1'b0;
          if (sck_rise_tick) spi_sck <= 1'b1;
          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            if (dummy_cnt == '0) begin
              seq_cnt  <= SEQ_W'(DATA_NIBBLES - 1);
              rx_phase <= 1'b0;
              all_rx   <= 1'b0;
              state    <= RD_DATA;
            end else begin
              dummy_cnt <= dummy_cnt - 1;
            end
          end
        end

        // ==================================================================
        // Quad receive: DATA_NIBBLES nibbles, sampled on each SCK rising edge.
        //   rx_phase=0 → latch sd_in into rx_hi (high nibble of new byte)
        //   rx_phase=1 → assemble {rx_hi, sd_in}, compare against cur_byte
        //                (which holds image_rom[cur_byte_idx]), set sticky
        //                mismatch on miscompare, then advance cur_byte_idx.
        // After the last rising edge (all_rx set), the next falling edge
        // deasserts CSB and transitions to RESULT.
        // ==================================================================
        RD_DATA: begin
          sd_oe <= 1'b0;
          if (sck_rise_tick) begin
            spi_sck <= 1'b1;
            if (rx_phase == 1'b0) begin
              rx_hi    <= sd_in;
              rx_phase <= 1'b1;
            end else begin
              if ({rx_hi, sd_in} != cur_byte)
                mismatch <= 1'b1;
              rx_phase <= 1'b0;
              if (cur_byte_idx != '0)
                cur_byte_idx <= cur_byte_idx - 1;
            end
            if (seq_cnt == '0)
              all_rx <= 1'b1;
            else
              seq_cnt <= seq_cnt - 1;
          end
          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            if (all_rx) begin
              spi_csb <= 1'b1;
              state   <= RESULT;
            end
          end
        end

        // ==================================================================
        // Latch the streaming mismatch flag into pass/fail.
        // ==================================================================
        RESULT: begin
          pass  <= ~mismatch;
          fail  <=  mismatch;
          busy  <= 1'b0;
          state <= DONE_ST;
        end

        // ==================================================================
        // Hold pass/fail until btn_write (cleared there); restart on button.
        // ==================================================================
        DONE_ST: begin
          spi_sck <= 1'b0;
          spi_csb <= 1'b1;
          sd_oe   <= 1'b0;
          if (btn_w_rise || btn_v_rise) begin
            is_verify <= btn_w_rise ? 1'b0 : 1'b1;
            if (btn_w_rise) begin
              pass <= 1'b0;
              fail <= 1'b0;
            end
            init_sr  <= INIT_SEQ;
            seq_cnt  <= SEQ_W'(15);
            spi_csb  <= 1'b0;
            sd_oe    <= 1'b1;
            sd_out   <= {3'b0, INIT_SEQ[15]};
            busy     <= 1'b1;
            all_rx   <= 1'b0;
            mismatch <= 1'b0;
            state    <= INIT_TX;
          end
        end

        default: state <= IDLE;
      endcase
    end
  end

endmodule

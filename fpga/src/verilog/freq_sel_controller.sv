/*
FREQ_SEL_CONTROLLER

  SPI master that executes the spi_freq_sel protocol: writes a 6-bit
  frequency selection value to register 4 of the custom chip by sending
  command byte 8'h40 followed by the data byte {2'b00, sw[5:0]}.

  User interface
    sw[5:0]  : slide switches SW5..SW0 – encode the 6-bit freq value
    btn      : push-button (active-high, raw) – one press triggers one frame

  SPI protocol  (Mode 0, CPOL=0 CPHA=0)
    Frame : 16 bits = CMD (8'h40) | {2'b00, sw[5:0]}
    MOSI changes on SCK falling edge; slave samples on SCK rising edge.
    CSB is asserted (low) before the first rising edge and deasserted
    (high) after the last sampling edge, matching the spi_freq_sel task.

  Pin mapping (Pmod JA connector, LVCMOS33)
    spi_sck  → JA1 (Y11)
    spi_csb  → JA2 (AA11)
    spi_mosi → JA3 (Y10)
*/

module freq_sel_controller (
  input  logic        clk,       // 100 MHz system clock
  input  logic        rst,       // synchronous active-high reset

  // Board user I/O
  input  logic [5:0]  sw,        // frequency value from slide switches SW5..SW0
  input  logic        btn,       // send-trigger button (active-high, raw signal)

  // SPI master outputs – connect to chip SPI slave
  output logic        spi_sck,   // SPI clock (CPOL=0, idle low)
  output logic        spi_csb,   // chip select bar (active low)
  output logic        spi_mosi,  // master out slave in

  // Status
  output logic        busy       // high while a transaction is in progress
);

  // -------------------------------------------------------------------------
  // Compile-time parameters
  // -------------------------------------------------------------------------
  localparam int CLK_HZ    = 100_000_000;
  localparam int SCK_HZ    = 1_000_000;                     // 1 MHz SCK
  localparam int SCK_HALF  = CLK_HZ / SCK_HZ / 2;          // 50 ticks
  localparam int DEB_TICKS = CLK_HZ / 1000 * 20;           // 20 ms debounce

  localparam logic [7:0] CMD = 8'h40;   // write register 4 opcode

  // -------------------------------------------------------------------------
  // Button: 2-stage synchroniser + debouncer + rising-edge strobe
  // -------------------------------------------------------------------------
  logic btn_s0, btn_s1;
  logic [$clog2(DEB_TICKS)-1:0] deb_cnt;
  logic btn_db, btn_db_d, btn_rise;

  always_ff @(posedge clk) {btn_s1, btn_s0} <= {btn_s0, btn};

  always_ff @(posedge clk) begin
    if (rst) begin
      deb_cnt <= '0;
      btn_db  <= 1'b0;
    end else if (btn_s1 == btn_db) begin
      // Input matches stable level – reset counter
      deb_cnt <= '0;
    end else if (deb_cnt == DEB_TICKS - 1) begin
      // Stable for the full debounce window – accept the new level
      btn_db  <= btn_s1;
      deb_cnt <= '0;
    end else begin
      deb_cnt <= deb_cnt + 1;
    end
  end

  always_ff @(posedge clk) btn_db_d <= btn_db;
  assign btn_rise = btn_db & ~btn_db_d;   // single-cycle strobe on press

  // -------------------------------------------------------------------------
  // SPI transmitter FSM
  // -------------------------------------------------------------------------
  typedef enum logic [1:0] {IDLE, SEND, DONE} state_t;
  state_t state;

  logic [15:0] tx_sr;           // transmit shift register, MSB first
  logic [3:0]  bit_cnt;         // current bit index (15 → 0)
  logic [6:0]  sck_cnt;         // SCK half-period tick counter (0 .. 2*SCK_HALF-1)

  // Combinatorially compute next-frame data so it can be used in the
  // same clock edge that we start the transaction (avoids NBD timing issue).
  logic [15:0] tx_next;
  assign tx_next = {CMD, 2'b00, sw};

  // SCK edge strobes (only meaningful in SEND state)
  wire sck_rise_tick = (state == SEND) && (sck_cnt == SCK_HALF     - 1);
  wire sck_fall_tick = (state == SEND) && (sck_cnt == 2 * SCK_HALF - 1);

  always_ff @(posedge clk) begin
    if (rst) begin
      state    <= IDLE;
      spi_sck  <= 1'b0;
      spi_csb  <= 1'b1;
      spi_mosi <= 1'b0;
      busy     <= 1'b0;
      tx_sr    <= '0;
      bit_cnt  <= '0;
      sck_cnt  <= '0;

    end else begin
      case (state)

        // ------------------------------------------------------------------
        IDLE: begin
          spi_sck  <= 1'b0;
          spi_csb  <= 1'b1;
          spi_mosi <= 1'b0;
          busy     <= 1'b0;
          sck_cnt  <= '0;
          if (btn_rise) begin
            tx_sr    <= tx_next;
            bit_cnt  <= 4'd15;
            spi_csb  <= 1'b0;         // assert chip-select
            spi_mosi <= tx_next[15];  // pre-drive MSB so it is stable at rise 1
            busy     <= 1'b1;
            state    <= SEND;
          end
        end

        // ------------------------------------------------------------------
        // SCK ticks at 1 MHz.  MOSI changes on every falling edge.
        // Rising edge N samples bit (15-N+1); after 16 full cycles → DONE.
        //
        //   Rise 1  samples bit15  (MOSI set in IDLE)
        //   Fall 1  sets   bit14, bit_cnt → 14
        //   Rise 2  samples bit14
        //   ...
        //   Fall 15 sets   bit0,  bit_cnt → 0
        //   Rise 16 samples bit0
        //   Fall 16 bit_cnt==0 → DONE
        // ------------------------------------------------------------------
        SEND: begin
          sck_cnt <= sck_cnt + 1;   // default; overridden on fall_tick

          if (sck_rise_tick)
            spi_sck <= 1'b1;        // rising edge: slave samples MOSI

          if (sck_fall_tick) begin
            spi_sck <= 1'b0;
            sck_cnt <= '0;
            if (bit_cnt == '0) begin
              state <= DONE;        // all 16 bits sampled; end transaction
            end else begin
              bit_cnt  <= bit_cnt - 1;
              tx_sr    <= {tx_sr[14:0], 1'b0};  // shift left
              spi_mosi <= tx_sr[14];             // drive next bit (pre-shift value)
            end
          end
        end

        // ------------------------------------------------------------------
        DONE: begin
          spi_sck  <= 1'b0;
          spi_csb  <= 1'b1;         // deassert chip-select
          spi_mosi <= 1'b0;
          busy     <= 1'b0;
          state    <= IDLE;
        end

        default: state <= IDLE;

      endcase
    end
  end

endmodule

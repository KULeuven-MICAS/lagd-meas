# Loading & launching programs on the LAGD chip over SPI

Status: **research notes** (no code written yet). Captures everything needed to
later write a host-side "SPI program loader" that runs in `lagd-meas/sw/` on top
of the existing `ChipDriver`/SPI-slave path.

The chip is a **Cheshire-based RISC-V SoC** (`lagd_soc` wrapping `cheshire_soc`).
RTL lives in the sibling repo `lagd-im/` (paths below are relative to
`aria_project/tapeout/`). The Cheshire dependency is the bender checkout
`lagd-im/.bender/git/checkouts/cheshire-4912d4aca2fac633/`.

> ⚠️ Provenance note: an earlier pass mis-read a non-existent `axi_spi_slave`
> checkout and reported wrong opcodes (0x03/0x83…). The **authoritative** IP is
> `hemaia_axi_spi_slave` (confirmed via `lagd-im/Bender.lock`:
> `KULeuven-MICAS/hemaia_axi_spi_slave`), checkout
> `lagd-im/.bender/git/checkouts/hemaia_axi_spi_slave-280826a1f9b73f6b/`.
> All opcodes/register facts below are read from that source.

---

## 1. Big picture — "a program" is just bytes at addresses

A CPU runs machine-code bytes sitting at specific memory addresses, then has its
PC pointed at the first one. So "loading a program" = **write the right bytes to
the right addresses, then tell the core to start.** Flow:

```
helloworld.spm.c  --riscv-gcc-->  .o  --ld(spm.ld)-->  .elf  --objcopy-->  .bin
                                                          |
                          (.elf carries per-segment load addresses)
                                                          v
        load = for each ELF PT_LOAD segment: write its bytes to its addr
        launch = write entry to SCRATCH regs + set the "go" bit
```

The compiler/linker (RISC-V GCC) is the "converter"; we don't write it. The
host-side loader only needs to (a) parse the ELF into `(addr, bytes)` segments,
(b) push each segment over SPI, (c) do the launch handshake.

**Use the `.elf`, not the flat `.bin`.** The real workloads scatter sections
across L2 (`0x8000_0000`) + Ising L1 (`0x9000_0000`); a flat `.bin` loses the
per-segment addresses and `objcopy` zero-pads the gaps (that's why
`lagd_scompute.spm.bin` is ~268 MB). Parse ELF program headers and load each
segment to its own address.

Memory map (from `lagd-im/sw/link/common.ldh`): `ENTRY(_start)`, code in
`l2_spm` @ `0x8000_0000` (64 KB), stack `0x1000_0000`, Ising J/F L1 at
`0x9000_0000`+. helloworld's `_start` / `.text` LMA = `0x8000_0000`.

---

## 2. Boot behavior (boot_mode is always 0 = passive)

Bootrom = **stock Cheshire bootrom** compiled into `lagd-im/hw/bootrom/lagd_bootrom.sv`
(generated hex ROM). No local `lagd_bootrom_extra.c` exists. Sources:
`cheshire-…/hw/bootrom/cheshire_bootrom.{c,S}`.

`main()` (`cheshire_bootrom.c:70-89`) reads the boot-mode register and switches:

| boot_mode | fn | who loads program | needs external "go"? |
|---|---|---|---|
| **0 passive** (ours) | `boot_passive()` | external (JTAG/UART/SPI scratch-poke) | **yes** |
| 1 SPI SD card | `boot_spi_sdcard()` | bootrom, autonomous | no |
| 2 SPI NOR flash | `boot_spi_s25fs512s()` | bootrom, autonomous | no |
| 3 I²C EEPROM | `boot_i2c_24fc1025()` | bootrom, autonomous | no |

On silicon `boot_mode` is **two real pins** (`pad_boot_mode_0_i/1_i` →
`lagd_soc.boot_mode_i` → cheshire), so strap = 0.

**boot_passive() (`cheshire_bootrom.c:23-34`) — the launch handshake:**
```c
uart_debug_init(&__base_uart, core_freq);                 // only UART gets init'd
volatile uint32_t *scratch = reg32(&__base_regs, CHESHIRE_SCRATCH_0_REG_OFFSET);
while (!(scratch[2] & 2))                                  // poll SCRATCH_2 bit 1
    if (uart_debug_check(&__base_uart)) return uart_debug_serve(&__base_uart);
scratch[2] = 0;
return boot_next_stage((void *)(((uint64_t)scratch[1] << 32) | scratch[0]));  // jump
```

### Q: does it print anything?
**No.** Zero `printf`/banner in the bootrom (no string literals at all). UART is
set up as a silent listener; it only emits protocol bytes (starting with ACK
`0x06`) if a host first sends the UART-debug handshake. On a serial console at
power-up: nothing. (A loaded *program* may print via UART itself — separate.)

### Q: is the core idle or active after bootrom?
In passive mode the boot hart is **actively busy-waiting** in the loop above
(secondary harts sleep in WFI). It waits for EITHER:
1. a UART-debug session (host sends `0x06` → in-loop server does read/write/exec), OR
2. someone to write **entry → SCRATCH_0/1** and then **set SCRATCH_2 bit 1**;
   the bootrom clears SCRATCH_2 and jumps to that entry.

On program exit, startup `.S` `_exit` writes `(retval<<1)|1` to **SCRATCH_2**,
`ebreak`, then `wfi` forever. (Sim's `jtag_wait_for_eoc` reads this:
`exit_code >>= 1`.)

---

## 3. Which interfaces need software init?

"Init" = the CPU must write a config register before the interface works.

| Interface | Needs bootrom init? | Why |
|---|---|---|
| **UART** | Yes (`uart_debug_init`) | baud divisor computed from `core_freq` at runtime |
| **JTAG** | **No** | autonomous TAP + RISC-V debug module on its own `jtag_tck_i` clock; live once TCK toggles & `trst_n` released |
| **SPI slave** | **No** | passive SPI→AXI bridge; works once out of reset & SCLK/CS toggle; reset-default config is usable as-is |

So for the SPI flow: the SPI slave is alive from reset and needs no CPU setup.
But the **launch** step still needs the bootrom *running* (core clock + reset
released, boot_mode=0) because the "go" is the bootrom's SCRATCH poll loop.

---

## 4. Address map reachable from the SPI master

The SPI slave is wired as an **external AXI master** into cheshire
(`lagd_soc.sv:112-126`, `axi_ext_mst_req[0]`). Cheshire uses **one** `axi_xbar`
with `.Connectivity('1)` (full) and a single shared address map
(`cheshire_soc.sv:246-275`). External master is just another master port
(`cheshire_soc.sv:278-280`) → routes purely by address, same as the CVA6 cores.

**Confirmed reachable from SPI** (verified through xbar + lagd external slaves):

| Target | Address | Route |
|---|---|---|
| **SCRATCH_0/1/2** (launch) | `0x0300_0000 / _0004 / _0008` | xbar → reg_demux (`AmRegs`) |
| **L2 SPM** (`.text`) | `0x8000_0000` (64 KB) | xbar → ext slave `L2_MEM` |
| Stack | `0x1000_0000` (16 KB) | xbar → ext slave `STACK_MEM` |
| Ising L1 (J / flip) | `0x9000_0000`+ | xbar → ext slave `ISING_CORES` |

`AmRegs = 0x0300_0000` (cheshire_pkg.sv); SCRATCH_n at `+0x0/0x4/0x8`.
LAGD external regions: `lagd-im/hw/rtl/include/lagd_define.svh`
(`L2_MEM_BASE_ADDR='h8000_0000`, 64 KB) registered into `CheshireCfg` at
`lagd-im/hw/rtl/lagd_pkg.sv:199-204`. LLC is bypassed (`LlcNotBypass=0`), so
`0x8000_0000` is genuinely the LAGD external L2 slave (not an internal LLC-SPM)
— and it's on the same xbar, so routable from the SPI master.

---

## 5. SPI-slave wire protocol (the loader emits this)

Source: `hemaia_axi_spi_slave-280826…/` files `spi_slave_cmd_parser.sv`,
`spi_slave_controller.sv`, `spi_slave_regs.sv`, `spi_slave_rx.sv`,
`spi_slave_axi_plug.sv`. Wrapper `lagd-im/hw/rtl/lagd_axi_spi_slave.sv`
instantiates it with `AXI_ADDR_WIDTH=32`, `AXI_DATA_WIDTH=32`, `chip_id('0)`,
`test_mode(1'b0)`.

### Command opcodes (`spi_slave_cmd_parser.sv`)
| cmd | meaning | phases |
|---|---|---|
| `0x01` | write reg0 (reg_sel=0) | cmd + 1 data byte |
| `0x02` | **write mem (AXI write)** | cmd + addr + data… (cont) |
| `0x05` | read reg0 | cmd + send 1 byte |
| `0x07` | read reg1 | cmd + send 1 byte |
| `0x0B` | **read mem (AXI read)** | cmd + addr + dummy + data… (cont) |
| `0x11` | write reg1 (reg_sel=1) | cmd + 1 data byte |
| `0x20` | write reg2 (reg_sel=2) | cmd + 1 data byte |
| `0x21` | read reg2 | cmd + send 1 byte |
| `0x30` | write reg3 (reg_sel=3) | cmd + 1 data byte |
| `0x31` | read reg3 | cmd + send 1 byte |

### Internal registers (`spi_slave_regs.sv`), reset defaults at lines 51-57
- **reg0**: bit0 = `en_qpi` (quad enable). reset **0** → single-lane by default.
- **reg1**: `dummy_cycles` (for reads). reset **32** (`'d32`).
- **reg2/reg3**: `wrap_length = {reg3, reg2}` (16-bit). reset **0**.

→ **Reset defaults are usable as-is for single-lane writes/reads. No config
command needed first.**

### Bit/byte order — MSB first
`spi_slave_rx.sv:69`: `data_int_next = {data_int[30:0], sdi0}` — shift left, new
bit into LSB ⇒ **first SCLK bit = MSB**. Command auto-sizes to 8 bits
(`spi_slave_rx.sv:42-43`). Phase widths from `spi_slave_controller.sv`:
- command = 8 bits
- address = **32 bits** (`rx_counter=0x1F` single-lane; `cmd→ADDR` at lines 144-145)
- each data word = **32 bits** (`0x1F`)
- register write data = **8 bits** (`0x7`)
- read dummy = `s_dummy_cycles` = reg1 (default 32 SCLKs)

### AXI mapping (`spi_slave_axi_plug.sv`)
- `aw_size/ar_size = 3'b010` (4 bytes), `aw_len=0` → **one 32-bit AXI beat per SPI data word**.
- write: `w_strb=0xF`, `w_data = curr_data_rx` (the 32-bit word).
- **auto-increment**: `next_addr = curr_addr + 4` per word (line 155), until
  `tx_counter == wrap_length-1` then wraps to start. With `wrap_length=0`
  default, `wrap_length-1 = 0xFFFF` ⇒ effectively linear for up to 65536 words.
  So: hold CS low, send cmd+addr once, then stream many words → they land at
  addr, addr+4, addr+8, … **This is the fast bulk-load path.**

### chip_id is a non-issue here
`axi_spi_slave.sv:204` `generate if (AXI_ADDR_WIDTH > 32)` — only then is the
address top byte forced from `chip_id`. With `AXI_ADDR_WIDTH=32` this block is
**not** instantiated; the full 32-bit address comes from SPI. `chip_id` (tied 0)
is unused. No chip-id prefix byte in the frame.

### Frame templates (single-lane, MSB-first)
```
WRITE 32-bit word D to address A (single word):
    CS low; send 0x02, A[31:24],A[23:16],A[15:8],A[7:0], D[31:24],D[23:16],D[15:8],D[7:0]; CS high

WRITE burst (stream N words from A):
    CS low; 0x02, A(4 bytes MSB-first), D0(4B), D1(4B), … D(N-1)(4B); CS high
    -> writes A, A+4, …, A+4*(N-1)

READ 32-bit word from A:
    CS low; 0x0B, A(4 bytes MSB-first), <32 dummy SCLKs>, then clock 32 bits out (MSB first); CS high
    (dummy count = reg1, default 32; read burst also auto-increments while CS held low)

WRITE internal register rN (e.g. dummy cycles): cmd 0x11, then 1 data byte
```

### SPI electrical — CONFIRMED (both sides of the RTL)
- **SPI mode 0 (CPOL=0, CPHA=0).** Slave samples on posedge sclk
  (`spi_slave_rx.sv:80`) and changes TX on negedge (inverted clock in
  `spi_slave_tx.sv:98-110,152`). Host states the same requirement in
  `lagd-meas/fpga/src/verilog/quad_spi_master.sv:31-33`.
- **CS active low**, one frame per CS-low window (`cs==1` resets FSM to CMD).
- SCK rate: host default `SCK_HZ=25 MHz` (`quad_spi_master.sv:37`).

### IMPORTANT: the lagd-meas host already implements the SPI AXI write/read
`lagd-meas/fpga/src/verilog/{chip_controller,quad_spi_master}.sv` are
co-designed against THIS slave. So the low-level SPI is done; the loader is
host-side Python only. The host path (after init) is **quad mode**, not the
single-lane frames above (those are the raw-slave reference):
- `chip.init_spi()` → cmd `0x01`, writes slave reg0=1 to enable QPI
  (single-lane, one frame) — `chip_controller.sv:238-239`.
- `chip.write_mem(A, words)` → cmd `0x02`, addr, quad data stream
  (`chip_controller.sv:275`, `spi_quad_mode_o=1` at `:267`).
- `chip.read_mem(A, n)` → cmd `0x0B`, addr, 33 dummy SCKs, quad read stream
  (`chip_controller.sv:279`; `DUMMY_CYCS=33` already matches slave reg1
  default 32 + 1 off-by-one, `quad_spi_master.sv:67-70`).
- Burst: host holds CS low and **pauses SCK** for stream backpressure
  (`quad_spi_master.sv:23-29`), so multi-word auto-increment works as-is.
- So loading is just: `init_spi()` once, then `write_mem(addr, words)` per ELF
  segment + the scratch-register launch writes. No new RTL.

### Endianness — CONFIRMED pass-through, no byte swap
Traced the 32-bit value host→slave→AXI: host drives `wdata_i[31:28]` first
(`quad_spi_master.sv:273-274`), slave reassembles identical bits
(`spi_slave_rx.sv:67`), `axi_master_w_data = curr_data_rx` with `w_strb=0xF`
(`spi_slave_axi_plug.sv:304`). So **`write_mem(A, V)` places the exact 32-bit V
on the AXI bus at word address A** (reads symmetric, `quad_spi_master.sv:186-188`).
- Within the word, AXI/RISC-V are **little-endian**: V[7:0]→byte A, …,
  V[31:24]→A+3.
- ELF for LE RISC-V stores words LE on disk; memory must match byte-for-byte.
  Since file=LE, ISA=LE, AXI=LE and the SPI path is value-preserving, **no
  swapping is needed** — read each 4-byte chunk little-endian and write it:
  ```python
  for off in range(0, len(segment), 4):
      word = struct.unpack_from('<I', segment, off)[0]   # little-endian
      chip.write_mem(seg_addr + off, word)
  ```
  (`WritePort.sendInt`'s `struct.pack("I", …)` is already native-LE on the
  Zedboard, and the 32-bit value is preserved through xillybus→FIFO→SPI→AXI.)
- 64-bit entry for launch: `entry & 0xFFFFFFFF`→SCRATCH_0,
  `entry>>32`→SCRATCH_1 (plain word writes).

---

> **Implemented** in `sw/tools/elf_loader.py` (transport-agnostic ELF parser)
> + `sw/tools/spi_program_loader.py` (`SpiProgramLoader`, SPI write + scratch
> launch on top of `ChipDriver`). Both target Python 3.6 (locked Zedboard).
> Verified end-to-end against a stub: helloworld loads to 0x8000_0000 (first
> word = 0x30057073), reads back identical, entry → SCRATCH_0/1, go-bit →
> SCRATCH_2. **Caveat:** `lib/*.py` currently use 3.10-only `X | Y` type
> annotations and crash on import under Python 3.6 — see §8.

## 6. The load-and-launch sequence (what the loader does)

Preconditions: boot_mode pins = 0; core clock + reset released (bootrom running
and spinning in `boot_passive`); SPI slave out of reset.

1. **Parse ELF** (`pyelftools`) → list of `(load_addr, bytes)` PT_LOAD segments
   + `e_entry`.
2. **Load** each segment: pad to 4-byte multiple; SPI `0x02` + addr + stream the
   words (one CS-low frame per segment, using auto-increment). Targets:
   L2 `0x8000_0000`, Ising L1 `0x9000_0000`, etc.
3. **Set entry**: SPI write `entry[31:0]` → `0x0300_0000` (SCRATCH_0),
   `entry[63:32]` → `0x0300_0004` (SCRATCH_1).
4. **Launch**: SPI write `2` → `0x0300_0008` (SCRATCH_2 bit 1). Bootrom sees it,
   clears SCRATCH_2, jumps to entry.
5. **(optional) Wait for done**: poll SCRATCH_2 via SPI read (`0x0B` @
   `0x0300_0008`); program-exit writes `(retval<<1)|1`, so bit0=done,
   `value>>1`=exit code.

All four target regions are SPI-reachable (§4). Each `ChipDriver.write_mem(addr,
words)`-style call maps to one `0x02` SPI frame.

---

## 7. How the *simulation* does the same (reference)

`ci/sys-run.sh --binary=…elf` → `make -C hw/tb run-soc` → `vsim tb_lagd_chip`.
TB passes binary/boot/preload as **Verilog `+define+`** (not plusargs):
`BOOT_MODE`, `PRELOAD_MODE`, `PRELOAD_ELF`. Dispatch in
`lagd-im/hw/tb/src/tb_lagd_chip.sv:50-67`:
- preload 0 = **JTAG**: `jtag_init(); jtag_elf_run(elf); jtag_wait_for_eoc()`
- preload 1 = **UART**: `uart_debug_elf_run_and_wait()`
- preload 2 = **SPI**: *placeholder, commented out — not implemented in sim*

ELF parsing is DPI-C (`cheshire/target/sim/src/elfloader.cpp`:
`read_elf`/`get_section`/`read_section`/`get_entry`). The JTAG path
(`vip_cheshire_soc.sv jtag_elf_preload/jtag_elf_run`) writes segments over the
debug-module system bus, then sets the core PC via an abstract command and
resumes — it **bypasses** the SCRATCH handshake. The UART/serial-link paths use
the SCRATCH handshake (write entry → SCRATCH, set go bit) that our SPI flow will
mirror. **SPI preload is the new thing for measurement; it has no sim equivalent
yet.**

---

## 8. Open items — RESOLVED from RTL (only bench sanity-checks remain)

- [x] **SPI mode** = mode 0 (CPOL=0, CPHA=0), confirmed both sides (see §5).
- [x] **Host drives CS/SCLK/4 lines and holds CS low across a burst** (pauses
      SCK for backpressure) — `quad_spi_master.sv:23-29`. Auto-increment burst OK.
- [x] **reg1 dummy=32** matches host (`DUMMY_CYCS=33` accounts for the off-by-one)
      — no reg reconfig needed.
- [x] **Endianness** = value pass-through, little-endian bytes; ELF needs no swap
      (see §5). The low-level SPI write/read is already implemented in the
      `lagd-meas` FPGA + existing `ChipDriver`.
- [ ] (bench) Endianness/round-trip smoke test: `write_mem`+`read_mem` a SCRATCH
      reg once on hardware before trusting bulk loads. (`spi_program_loader.py
      --verify` does this per-segment.)
- [ ] (bench) Max SCLK in the real setup (host default 25 MHz). Must be swept;
      there is no SPI timing spec in lagd-im.
- [ ] Quad mode is already used by the host after `init_spi()`; nothing to add.
- [ ] **Python 3.6 compat of `lib/`**: `read_port.py`/`write_port.py`/
      `chip_driver.py` use PEP 604 `X | Y` and `type[...]` annotations
      (3.9/3.10+). These raise `TypeError` at import on the Zedboard's Python
      3.6.15. `tools/elf_loader.py` and `tools/spi_program_loader.py` are 3.6-safe,
      but they import `ChipDriver`, so the lib must be made 3.6-compatible (use
      `typing.Optional[int]` / `typing.List[int]`, or add
      `from __future__ import annotations` at the top of each lib file) before the
      loader runs on the board.

## Key file references
- Bootrom: `lagd-im/.bender/git/checkouts/cheshire-4912d4aca2fac633/hw/bootrom/cheshire_bootrom.{c,S}`
- SoC wiring / addr map: `lagd-im/hw/rtl/lagd_soc.sv`, `lagd-im/hw/rtl/lagd_pkg.sv`,
  `lagd-im/hw/rtl/include/lagd_define.svh`, cheshire `hw/cheshire_soc.sv` + `hw/cheshire_pkg.sv`
- SPI IP: `lagd-im/.bender/git/checkouts/hemaia_axi_spi_slave-280826a1f9b73f6b/`
  (`spi_slave_cmd_parser.sv`, `spi_slave_controller.sv`, `spi_slave_regs.sv`,
  `spi_slave_rx.sv`, `spi_slave_axi_plug.sv`, `axi_spi_slave.sv`) + wrapper
  `lagd-im/hw/rtl/lagd_axi_spi_slave.sv`
- Sim entry: `lagd-im/ci/sys-run.sh`, `lagd-im/hw/tb/src/tb_lagd_chip.sv`
- SW build: `lagd-im/sw/Makefile`, `lagd-im/sw/link/{spm.ld,common.ldh}`, tests in `lagd-im/sw/tests/`

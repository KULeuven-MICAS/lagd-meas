# Zedboard Xillybus bitstream

This project holds all files and scripts to synthesize and implement a **Xillybus bitstream on your Zedboard**.

This project continues on a **specific Xillybus flavor** downloaded by Bob Vanhoof (bv) in 2022 (which is named `corebundle-bv_testcore_2022`).
This Xillybus flavor holds following specifications:
1. The basis Xillybus setup.
2. Two 32b read-write FIFO streams (buffer depth 256x128): `xillybus_read_32`, `xillybus_write_32`, `xillybus_read_32_2` and `xillybus_write_32_2`

The two RW FIFO streams were pursued to obtain an independent python engine that polls all Ivdd/Ibias measurements and in parallel be able to send/receive (high-BW) commands to/from your chip.

General **Xillybus documentation** can be found on the [Xillybus documentation webpage ](http://www.xillybus.com/doc).

## Robin's changes for Mamba (Hemaia-based) tape-out

This fork extends the base Xillybus design with the FPGA-side logic to interface with the SPI ports of the chip. The changes include two SPI controllers within the sv file, and rewiring the switches, LEDs, buttons and FMC pints. See [doc/board_io_reference.md](doc/board_io_reference.md) for the full pin/LED/button mapping and [doc/spi_reference.md](doc/spi_reference.md) for the SPI framing.

**Design intent**

1. **Program the chip's SPI clock frequency** — [`freq_sel_controller`](src/verilog/freq_sel_controller.sv) issues a standard-SPI write to an on-chip SPI register. This register is directly read by the chip's PLL to control the frequency. The 6-bit frequency code is set on SW0–SW5 and shipped by pressing BTNL. 

2. **BIST that programs memory contents and verifies them** — [`spi_image_tester`](src/verilog/spi_image_tester.sv) is a built-in self-test that (a) initializes the chip into Quad-SPI mode, (b) writes a program image into the chip's memory at `0x8000_0000`, and (c) reads it back and compares against the same image, latching PASS (LD6) / FAIL (LD7). BTNR runs the write, BTNU runs the verify. This lets us confirm the chip's memory interface end-to-end with just the Zedboard, before any software is in the loop. The slide-switch–driven BIST mode (SW7) gives a second, even simpler sanity path (LEDs mirror switches) so we can confirm the bitstream is alive without a monitor.

3. **Program image is hardwired into the bitstream (current version)** — the image written/verified by `spi_image_tester` lives in [src/image/program.bin](src/image/program.bin) and is baked into the FPGA at synthesis time. [scripts/bin_to_hex.sh](scripts/bin_to_hex.sh) converts it to a `$readmemh`-able hex file plus a small `image_info.vh` header, which is then included into the bitstream as a ROM. There is **no runtime path** today to swap the program — changing the image requires regenerating the bitstream. The longer-term plan is to source the image over one of the Xillybus FIFO streams so a host can push arbitrary programs without rebuilding, but that path is not yet wired up.

The Xillybus FIFO streams inherited from the `bv_testcore_2022` corebundle are kept intact (see the description above) — none of the changes above use them yet; both controllers are driven from the Zedboard's PS GPIO (switches/buttons), not from a host stream.

## Cloning this repo

This repo uses git *submodules* to link to other micas repos for
common code. After cloning, you need to explicitly tell git to 
also clone these repos. 
First, go to the root of your local clone, the run the following:
```bash
	git submodule init
	git submodule update
```
Git should report it successfully cloned the submodules.

If you forget this, the project initialization scripts will crash and
your Vivado project will be incomplete.

## Get started

1. Collect the necessary **hardware**
  * 1 Zedboard
  * 1 (64GB) Sandisk SD card
  * 1 VGA-compatible monitor
  * 1 VGA cable
  * 1 USB-OTG cable
  * 1 keyboard
  * 2x micro-USB to USB-A (one for UART shell, one for VIVADO debug core)
  * 1 ethernet cable
2. Register your zedboard:
  * Go to the registration document: https://docs.google.com/spreadsheets/d/1JmtrHutt4cbaz8P0bQVbD5lI_xyRpptRKLjGID7dGgw/edit#gid=0 
  * Check that the mac address does not conflict and is not the default(see further)
3. Set up your **boot SD card**
  * most easiest: do a full image copy of the SD card of a colleague
  * more difficult: follow the Xillybus manual steps to setup the boot. Howto: [xillybus_getting_started_zynq.pdf](http://www.xillybus.com/downloads/doc/xillybus_getting_started_zynq.pdf).
4. Configure the **network** of the Zedboard
  * have a look into following MICAS gitlab project: [zedboard networking](https://gitlab.esat.kuleuven.be/micas/measurement-setups/zedboard-networking)
5. Configure Vivado for bitstream generation **[this repository]**

#### Build the bitstream

Run the fully headless build from the repo root:

```bash
./scripts/build.sh
```

This single command:
1. Extracts the Xillinux zip into `no_backup/` (skipped if already extracted).
2. Copies the `corebundle-bv_testcore_2022` files into place.
3. Converts `src/image/program.bin` → `program.hex` + `image_info.vh` for the SPI image tester (see [Program image](#program-image-spi-image-tester)).
4. Creates the Vivado project, adds all RTL/IP sources and the constraints file.
5. Runs synthesis → implementation → bitstream generation (8 jobs, no GUI).
6. Places the bitstream at `no_backup/links_to_important_files/xillydemo.bit`.

Force a clean rebuild from scratch with `./build.sh --clean`.

**Logs** (inspect if something fails):

| File                              | Contents                                 |
|-----------------------------------|------------------------------------------|
| `no_backup/logs/vivado_build.log` | Top-level Vivado batch log               |
| `no_backup/logs/synth.log`        | Synthesis run log (`synth_1/runme.log`)  |
| `no_backup/logs/impl.log`         | Implementation run log (`impl_1/runme.log`) |

Common warnings to ignore:
- `[Synth 8-7080]` on PS DDR/MIO unconnected pins (Xillybus design, not our concern).
- `[Synth 8-3331]` on PS_GPIO pins detached from PL logic (intentional — those indices were freed for `chip_sck/csb/mosi`).

#### Program the board

**Option A — Vivado Hardware Manager (GUI)**: connect USB-JTAG (micro-USB J17), power on, then in Vivado **Flow Navigator → Program and Debug → Open Hardware Manager → Auto Connect → Program Device**, select `xillydemo.bit`.

**Option B — Vivado Hardware Manager (Tcl)**:

```tcl
open_hw_manager
connect_hw_server
open_hw_target
current_hw_device [get_hw_devices xc7z020_1]
set_property PROGRAM.FILE {xillydemo.bit} [current_hw_device]
program_hw_devices [current_hw_device]
```

**Option C — SD-card deployment (`xdevcfg` or BOOT.bin)**: copy `xillydemo.bit` to the SD card's FAT partition (u-boot loads it on power-up), or for a live update on a running Xillinux board: `scp xillydemo.bit root@<zedboard_ip>:/tmp/ && ssh root@<zedboard_ip> 'cat /tmp/xillydemo.bit > /dev/xdevcfg'`. The helper [scripts/deploy_bitstream.sh](scripts/deploy_bitstream.sh) bundles the bitstream (and optionally `BOOT.bin`) into `no_backup/deploy/` for download.

## RTL development
When you finished your initial Vivado/Xillybus setup, you can choose two ways to continue your FPGA code development:
1. Edit your source files, and restart the Xillybus setup process by rerunning `runtool.sh`. (**! be careful to not overwrite files/settings/.. you defined in the Vivado environment only**) **OR**
2. Open the already existing Vivado project using the `start_vivado_gui.sh` script

#### Important files
Where are the important settings located?
* `src/early_mine.xdc`: Zedboard IO configuration (mapping and IO timing)
  - Zynq->Avnet Zedboard pin mapping: [Zedboard_HW_Users_Guide.pdf](https://www.avnet.com/wps/wcm/connect/onesite/922900e3-3d57-4cc7-883f-a8b9fbea0cd0/ZedBoard_HW_UG_v2_2.pdf?MOD=AJPERES&CACHEID=ROOTWORKSPACE.Z18_NA5A1I41L0ICD0ABNDMDDG0000-922900e3-3d57-4cc7-883f-a8b9fbea0cd0-nNnWuIb)
  - or, including the FMC IO: [doc/avnet_zedboard/zedboard_master_UCF_RevC_v3.ucf](doc/avnet_zedboard/zedboard_master_UCF_RevC_v3.ucf)
* `src/xillydemo.xdc`: Zedboard Vivado debug core config [auto create from Vivado > SYNTHESIS > Set Up Debug]
* `src/verilog/`: primary verilog source file folder

#### Program image (SPI image tester)

The `spi_image_tester` module bakes a program image into the bitstream and can
program or verify over Quad-SPI: **BTNR** runs write-only (also clears PASS/FAIL
LEDs), **BTNU** runs verify-only and updates PASS/FAIL. The build consumes a raw
program **.bin** file:

* Place your program at [src/image/program.bin](src/image/program.bin) (or set
  `PROGRAM_BIN=<path>` before running `./build.sh`).
* [build.sh](build.sh) runs [scripts/bin_to_hex.sh](scripts/bin_to_hex.sh)
  automatically before Vivado. The script produces two generated artefacts
  next to the .bin (both `.gitignore`d):
  - `program.hex` – one byte per line, consumed by `$readmemh` at elaboration.
  - `image_info.vh` – defines `` `IMAGE_NUM_BYTES `` and `` `IMAGE_FILE ``
    that `spi_image_tester.sv` picks up via global include.
* The .bin is zero-padded up to a multiple of 4 bytes (the SPI engine transfers
  32-bit words).
* Byte order on the wire is MSByte first; `image_rom[0]` is the first byte of
  the .bin file and is shipped last.

## Board I/O Reference

LED / slide-switch / push-button / Pmod JA / FMC pin assignments and their RTL roles (including BIST and the `freq_sel_controller` / `spi_image_tester` trigger overview) live in [doc/board_io_reference.md](doc/board_io_reference.md).

---

## Debug core
To debug the waveforms and xillydemo.v code read this [repo](https://gitlab.esat.kuleuven.be/micas/measurement-setups/zedboard/zedboard_bitstream/-/blob/main/doc/vivado/hw_debugger/doc_vivado_hwdebugger.md)
Remember that:
1. All nets holding attribute `(* mark_debug = "true" *)` will be added to the debug core input.
2. Automatically insert the debug core with the Vivado GUI: SYNTHESIS > Set Up Debug
3. Check that the `src/constraints/xillydemo.xdc` gets correctly written.

`chip_sck`, `chip_csb`, and `chip_sd[3:0]` all carry `(* mark_debug = "true" *)`, so Vivado will offer to create an ILA automatically during implementation.

**Capturing a `freq_sel` frame**: trigger on `chip_csb` falling edge. Expect 16 SCK cycles; confirm MOSI carries `0x40` then `{2'b00, sw}`.

**Capturing image SPI (`spi_image_tester`)** — use **BTNR** for write, **BTNU** for verify (each press is one independent session: **spi_init** then one Quad frame):

1. Trigger on `chip_csb` falling edge.
2. After **spi_init**, one of:
   - **BTNR**: Quad write — `cmd=0x02`, `addr=0x80000000`, data nibbles MSByte-first (e.g. `D E A D B E E F` for the default 4-byte test image).
   - **BTNU**: Quad read verify — `cmd=0x0B`, same address, 33 dummy SCK cycles, then readback nibbles on `chip_sd[3:0]`.
3. LD6/LD7 (PASS/FAIL) update after **BTNU** finishes; pressing **BTNR** clears them until the next verify.

## FAQ
### Manually set up Vivado
1. Running Tcl Scripts
  * In vivado: Tools > Run Tcl Script. Select `xillinux../verilog/xillydemo-vivado.tcl`. This will set up the Xillybus environment, links to your source files, ..

### MAC address
By default, all zedboards have the same mac address (00:0a:35:00:01:22), since avnet found 2 development boards on the same network are unlikely. Alas. Change the mac address, following the manual.

The new (2022) mac address convention is the following: DE:AD:B\<serial number hex code\>
1. Boot the zedboard with either serial console open or vga monitor + keyboard attached using the OTG dongle
2. Interrupt boot process with any keyboard
3. ...

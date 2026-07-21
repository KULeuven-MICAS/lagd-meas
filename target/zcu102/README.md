# Scripts for FPGA Verification on ZCU102

Bring-up scripts for running the LAGD chip on the **ZCU102** board. The ZCU102 (a
Zynq UltraScale+ PYNQ host) programs the LAGD bitstream into its PL and resets the
chip; a separate measurement host then loads and runs an ELF on the chip over UART.

## Contents

| File | What it does |
|------|--------------|
| [`top.py`](top.py) | Top-level entry point: reload the ZCU102, then load & run an ELF on the chip over UART. |
| [`zcu102_reload.py`](zcu102_reload.py) | Reload the ZCU102 over SSH — (optionally) upload a bitstream, then (re)run the PYNQ notebook to program the PL and reset the chip. |
| [`jupyter_notebooks/lagd_v1_2026/`](jupyter_notebooks/lagd_v1_2026/) | PYNQ notebook (`lagd_v1_notebook.py` / `.ipynb`) that downloads `lagd.zcu102.bit` onto the ZCU102. Runs on the ZCU102 board. |

## Usage

Run from this directory. Both are `argparse` CLIs — see `--help` for the full option
list.

Reload the board only:

```bash
./zcu102_reload.py                     # just reload & run the notebook
./zcu102_reload.py --bit path/to.bit   # upload a bitstream first, then reload & run
./zcu102_reload.py --host xilinx@1.2.3.4   # target a different board
```

Full bring-up (reload the board, then load & run an ELF over UART):

```bash
./top.py                                          # default ELF and host
./top.py --elf sw/inputs/lagd_scompute.spm.elf    # run a specific ELF (path on the measurement host)
./top.py --host root@1.2.3.4                       # override the measurement host
./top.py --bit path/to.bit                         # also upload a bitstream during the reload
```

Any unrecognised arguments to `top.py` are forwarded to `send_uart` on the
measurement host (e.g. `--rtscts` to keep hardware flow control).

## Notes

- **Two hosts.** `zcu102_reload.py` talks to the ZCU102 (`xilinx@…`); the ELF stage
  in `top.py` talks to a separate Zedboard measurement host (`root@…`) that is wired
  to the chip's UART. Both hosts are overridable — `top.py --host …` (measurement
  host) and `top.py --reload-host …` / `zcu102_reload.py --host …` (ZCU102); the
  defaults live at the top of each script.
- The ELF path in `top.sh` is resolved on the **remote** measurement host, relative
  to its `REMOTE_DIR`, not locally.

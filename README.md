# LAGD-MEAS

Measurement environment for the **LAGD** chip: a Zedboard FPGA bitstream plus
host-side Python that configures the chip, on-board DAC/PLL, and runs chip tests.

## How it fits together

```
host (Python, Zynq Linux)  ──Xillybus FIFOs──▶  FPGA controllers  ──SPI/serial──▶  LAGD chip + DAC + PLL
                           ──USB port      ──▶  FT4232            ──UART      ──▶  LAGD chip
                                                                 ──JTAG       ──▶  LAGD chip
```

The Zynq host pushes commands into Xillybus FIFOs; the FPGA translates them into
Quad-SPI accesses to the chip, SPI writes to the on-board DAC, and serial config to
the on-chip PLL. Direct UART/JTAG paths through the FT4232 bypass the FPGA for bootrom
and JTAG debug work.

## Repository layout

- [`fpga/`](fpga/) — Vivado project for the Zedboard/Xillinux bitstream. Build with
  `make`; simulate with `make sim`. See [`fpga/README.md`](fpga/README.md).
- [`sw/`](sw/) — Python libraries, test scripts, ELF loaders, and UART/JTAG helpers
  that run on the Zynq Linux host. See [`sw/README.md`](sw/README.md).
- [`testcases/`](testcases/) — runnable chip test sequences (UART, JTAG, soak scripts).
- [`tools/`](tools/) — lint and support tools.
- [`target/`](target/) — target/board-specific files (e.g., `zcu102/`).
- [`xillinux/`](xillinux/) — Xillinux root filesystem overlays and workspace files.
- `env.sh` — environment setup: `source env.sh` from the repo root before running any
  Python scripts.
- `pyproject.toml` — Python linting configuration (Ruff targets Python 3.7 for the lab
  measurement machines).
- `measurement_ladder.md` — full measurement plan and checklist for the LAGD chip.

## Quick start

1. Source the environment:
   ```bash
   cd lagd-meas/
   source env.sh
   ```
2. Build and load the FPGA bitstream — see [`fpga/README.md`](fpga/README.md).
3. Run host scripts and tests — see [`sw/README.md`](sw/README.md) and
   [`measurement_ladder.md`](measurement_ladder.md).

## Lab instrument control

Host-side scripts can also control lab instruments over the IC-LAB network. Authenticate
by generating an encrypted keyfile (recommended):

```bash
python3 sw/lib/os_utils/keygen.py
```

The script asks for the keyfile path, username, password, and a master password to
encrypt the credentials.

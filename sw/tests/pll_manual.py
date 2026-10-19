# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Program the PLL only; every other instrument (PLL supply, reference, analyzer, scope) is set by hand. No IC-LAB
# login, no SMU, no 33600A: only the FPGA link to the PLL controller is opened.
#
# main() loads CFG for a reference of F_REF (VCO = FB_DIV x F_REF) and then reads the lock bit each time Enter is
# pressed, until "q". The config stays on the chip after the script ends (only the FPGA ports are closed), as long as
# the PLL supply stays on. Before running: PLL supply on (0.75 V), reference on the PLL input (F_REF, 0 -> 1.8 V
# square). Edit CFG / F_REF and run again to try other settings.
#
# Tests:
#   program(cfg, f_ref)   # load cfg, wait for lock, read the lock bit on Enter until "q"
#

import logging
from datetime import datetime
from pathlib import Path

from sw.lib import pll_setup
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8
from sw.lib.pll_spectrum import FB_DIV

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

F_REF = 32e6  # reference on the PLL input [Hz], set by hand; the VCO runs at FB_DIV x F_REF = 4096 MHz
CFG = dict(
    CFG_REF8,  # loop closed, internal Vctrl
    vco_tune_coarse=0,  # VCO codes: the S5 table pick at 4.05 GHz, locked with this filter in the range sweep
    vco_current_min=8,  # pll_range_S5_20261013_161640 (Vctrl pred 0.55 V); pll_test.TRY_CFG uses min 10, max 8
    vco_current_max=0,
    set_current=7,  # loop filter (pll_settings.LOOP_FILTER): charge-pump current
    set_c1=0,
    set_c2=0,
    set_r1=7,
    pll_clk_o_en=1,  # pad = PLL output (0: through the external divider: / 2**set_div_freq / (2 * (clk_div_val + 1)))
    set_div_freq=6,  # PLL output = VCO / 2**6 = 64 MHz on the pad; keep the pad <= 125 MHz
)


def program(cfg, f_ref, lock_timeout=3.0):
    """Load `cfg` (with silicon readback) for a reference of `f_ref` [Hz], wait up to `lock_timeout` [s] for lock and
    log the result; then read the lock bit again on every Enter, until "q". The FPGA ports are closed at the end (also
    on an error); the config stays on the chip."""
    pll = None
    try:
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=lock_timeout)
        _, total_div = calculate_div_factor(cfg)
        logging.info("PLL %s: ref %.4f MHz -> VCO %.1f MHz (x%d), pad %.4f MHz (/%d); VCO coarse %d min %d max %d, "
                     "Icp %d C1 %d C2 %d R1 %d", "LOCKED" if locked else "NOT LOCKED", f_ref / 1e6,
                     FB_DIV * f_ref / 1e6, FB_DIV, FB_DIV * f_ref / total_div / 1e6, total_div,
                     cfg["vco_tune_coarse"], cfg["vco_current_min"], cfg["vco_current_max"], cfg["set_current"],
                     cfg["set_c1"], cfg["set_c2"], cfg["set_r1"])
        while input("Enter: read the lock bit, q + Enter: quit (the config stays on the chip) ").strip() != "q":
            logging.info("Lock bit: %s", pll.read_lock())
    finally:
        if pll is not None:
            pll.close()


def start_log_file():
    """Also write the log to results/logs/pll_manual_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_manual_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # PLL supply and the 32 MHz reference are set by hand before this
    program(CFG, F_REF)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

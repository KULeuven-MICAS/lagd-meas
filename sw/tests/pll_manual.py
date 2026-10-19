# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Program the PLL only; the PLL supply and the reference are set by hand. No SMU, no 33600A: the FPGA links to the chip
# (reset) and the PLL controller are opened, and (IC-LAB login) the analyzer, to show the phase noise on its screen.
#
# main() loads CFG for a reference of F_REF (VCO = FB_DIV x F_REF) and then reads the lock bit each time Enter is
# pressed, until "q". Until then the chip's digital core is held in reset (pll_setup.core_in_reset keeps the chip
# ports open): a running core pollutes the spectrum. After "q" the FPGA ports close: the core runs again, the PLL
# config stays on the chip as long as the PLL supply stays on. Before running: PLL supply on (0.75 V), reference on
# the PLL input (F_REF, 0 -> 1.8 V square). Edit CFG / F_REF and run again to try other settings.
#
# After lock the analyzer (meas_setup.yaml `spectrum_analyzer`, the FSW43) is put in its Phase Noise application (K40)
# on the pad carrier, continuous sweep, offsets PNO_OFFSET_START up to pad / OUT_OFFSET_RATIO, spot-noise markers at the
# OFFSET_SPAN_MAP offsets of our marker method, spur removal and the spur list (show_phase_noise): look at it on the
# screen (press LOCAL to take over).
#
# Tests:
#   program(cfg, f_ref)            # core in reset, load cfg, wait for lock, phase noise on the analyzer screen,
#                                  # read the lock bit on Enter until "q"
#   show_phase_noise(f_pad)        # analyzer in phase-noise mode on a carrier at f_pad, left running
#   toggle_core_reset(cfg, f_ref)  # same, but every Enter releases / holds the core reset, to compare the spectrum
#

import logging
from datetime import datetime
from pathlib import Path

from sw.lib import pll_setup
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.lab_instruments.drivers.rohde_schwarz_fsv_spectrum import PNO_MAX_SPOT_MARKERS
from sw.lib.pll_spectrum import (FB_DIV, OFFSET_SPAN_MAP, OUT_OFFSET_RATIO, SPUR_THRESHOLD_DB, offsets_for,
                                 open_spectrum)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

F_REF = 32e6  # reference on the PLL input [Hz], set by hand; the VCO runs at FB_DIV x F_REF = 4096 MHz
# Phase-noise mode on the analyzer (show_phase_noise): lowest offset [Hz] (as our marker method), RBW as % of the offset
PNO_OFFSET_START = 1e3
PNO_RBW_PERCENT = 10.0
# Expected carrier on the pad for the analyzer's verification and tracking: full swing is about -5..+1 dBm (divider
# sweep 2026-10-05); the frequency is exact when locked, the tolerance only covers the reference generator.
PNO_CARRIER_DBM = 0.0
PNO_LEVEL_TOL_DB = 10.0
PNO_FREQ_TOL_HZ = 10e3
# Spur removal on the analyzer's trace, with the threshold of our own spur detection (pll_spectrum.SPUR_THRESHOLD_DB);
# the spurs are listed in a spur-list window next to the phase-noise diagram either way.
PNO_SPUR_REMOVAL = True
PNO_SPUR_THRESHOLD_DB = SPUR_THRESHOLD_DB
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


def show_phase_noise(f_pad, offset_start=PNO_OFFSET_START, rbw_percent=PNO_RBW_PERCENT):
    """Put the analyzer in its Phase Noise application on a carrier at `f_pad` [Hz] and leave it sweeping
    continuously for viewing: carrier verified against f_pad and PNO_CARRIER_DBM within PNO_FREQ_TOL_HZ /
    PNO_LEVEL_TOL_DB and tracked (frequency and level); offsets `offset_start` up to f_pad / OUT_OFFSET_RATIO, RBW
    `rbw_percent` % of the offset, spot-noise markers at the OFFSET_SPAN_MAP offsets that fit (as our marker method),
    spur removal (PNO_SPUR_REMOVAL, PNO_SPUR_THRESHOLD_DB) and the spur list next to the diagram.
    The VISA session is closed at the end (also on an error); the settings stay on the analyzer (press LOCAL to take
    over)."""
    offsets = sorted(offsets_for(f_pad, OFFSET_SPAN_MAP))[:PNO_MAX_SPOT_MARKERS]  # the analyzer has 5 spot markers
    spectrum = open_spectrum()
    try:
        spectrum.start_phase_noise_mode(f_pad, offset_start, f_pad / OUT_OFFSET_RATIO,
                                        carrier_level_dbm=PNO_CARRIER_DBM, freq_tolerance_hz=PNO_FREQ_TOL_HZ,
                                        level_tolerance_db=PNO_LEVEL_TOL_DB, tracking=True,
                                        rbw_percent=rbw_percent, spur_removal=PNO_SPUR_REMOVAL,
                                        spur_threshold_db=PNO_SPUR_THRESHOLD_DB, continuous=True)
        spectrum.set_phase_noise_spot_offsets(offsets)
        spectrum.add_phase_noise_window("SPURs")  # the analyzer's spur list, right of the diagram
        spectrum.set_display_update(True)
    finally:
        spectrum.close()
    logging.info("Analyzer in phase-noise mode on the pad carrier %.4f MHz, spot noise at %s Hz (press LOCAL to take "
                 "over)", f_pad / 1e6, ", ".join("{:g}".format(o) for o in offsets))


def program(cfg, f_ref, lock_timeout=3.0, show_pno=True):
    """Load `cfg` (with silicon readback) for a reference of `f_ref` [Hz], wait up to `lock_timeout` [s] for lock and
    log the result; `show_pno`: then show the phase noise on the analyzer (show_phase_noise). Then read the lock bit
    again on every Enter, until "q". The chip's digital core is held in reset until then (pll_setup.core_in_reset).
    The FPGA ports are closed at the end (also on an error): the PLL config stays on the chip, the core runs again.
    The analyzer needs the lab network (iclab_session)."""
    pll = None
    try:
        with pll_setup.core_in_reset():
            pll = pll_setup.open_pll(cfg)
            locked = pll.wait_lock(timeout=lock_timeout)
            _, total_div = calculate_div_factor(cfg)
            logging.info("PLL %s: ref %.4f MHz -> VCO %.1f MHz (x%d), pad %.4f MHz (/%d); VCO coarse %d min %d max %d, "
                         "Icp %d C1 %d C2 %d R1 %d", "LOCKED" if locked else "NOT LOCKED", f_ref / 1e6,
                         FB_DIV * f_ref / 1e6, FB_DIV, FB_DIV * f_ref / total_div / 1e6, total_div,
                         cfg["vco_tune_coarse"], cfg["vco_current_min"], cfg["vco_current_max"], cfg["set_current"],
                         cfg["set_c1"], cfg["set_c2"], cfg["set_r1"])
            if show_pno:
                show_phase_noise(FB_DIV * f_ref / total_div)
            while input("Enter: read the lock bit, q + Enter: quit (core runs again, the config stays on the chip) "
                        ).strip() != "q":
                logging.info("Lock bit: %s", pll.read_lock())
    finally:
        if pll is not None:
            pll.close()


def toggle_core_reset(cfg, f_ref, lock_timeout=3.0):
    """program(), but every Enter switches the chip's digital core between held in reset and running, until "q", to
    compare the spectrum on the analyzer with and without the core active (state + PLL lock bit logged at each
    switch). Starts with the core held in reset; at the end the chip ports close and the core runs again."""
    pll = None
    try:
        with pll_setup.core_in_reset() as chip:
            pll = pll_setup.open_pll(cfg)
            logging.info("PLL %s: ref %.4f MHz", "LOCKED" if pll.wait_lock(timeout=lock_timeout) else "NOT LOCKED",
                         f_ref / 1e6)
            held = True
            while input("Enter: %s the core reset, q + Enter: quit (core runs again, PLL config stays on the chip) "
                        % ("release" if held else "hold")).strip() != "q":
                held = not held
                chip.hold_reset(held)
                logging.info("Chip core %s; PLL lock bit: %s",
                             "HELD IN RESET" if held else "RUNNING (reset released)", pll.read_lock())
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
    # IC-LAB firewall login: opens the lab network to the analyzer (phase noise on its screen)
    with iclab_session(Parser().get_credentials()):
        program(CFG, F_REF)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

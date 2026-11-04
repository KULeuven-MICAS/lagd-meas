# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Program the PLL only; the PLL supply and (except in tune_filter) the reference are set by hand. No SMU: the FPGA
# links to the chip (reset) and the PLL controller are opened, and (IC-LAB login) the analyzer, to show the phase noise
# on its screen.
#
# main() loads CFG for a reference of F_REF (VCO = FB_DIV x F_REF) and then reads the lock bit each time Enter is
# pressed, until "q". Until then the chip's digital core is held in reset (pll_setup.core_in_reset keeps the chip
# ports open): a running core pollutes the spectrum. After "q" the FPGA ports close: the core runs again, the PLL
# config stays on the chip as long as the PLL supply stays on. Before running: PLL supply on (0.75 V), reference on
# the PLL input (F_REF, 0 -> 1.8 V square). Edit CFG / F_REF and run again to try other settings.
#
# After lock the analyzer (meas_setup.yaml `spectrum_analyzer`, the FSW43) is put in its Phase Noise application (K40)
# on the pad carrier, continuous sweep, offsets PNO_OFFSET_START up to pad / OUT_OFFSET_RATIO, spot-noise markers at the
# OFFSET_SPAN_MAP offsets, spur removal and the spur list (show_phase_noise): look at it on the
# screen (press LOCAL to take over).
#
# Tests:
#   program(cfg, f_ref)            # core in reset, load cfg, wait for lock, phase noise on the analyzer screen,
#                                  # read the lock bit on Enter until "q"
#   show_phase_noise(f_pad)        # analyzer in phase-noise mode on a carrier at f_pad, left running
#   toggle_core_reset(cfg, f_ref)  # same, but every Enter releases / holds the core reset, to compare the spectrum
#   tune_filter(point, sample)     # interactive loop-filter tuning at a point: a pll_spur_zoom.SPUR_POINTS entry,
#                                  # manual_point(f_vco, coarse, min, max) or lut_point(f_vco) (table pick); the
#                                  # reference from the 33600A, phase noise live on the analyzer; type filter codes
#                                  # to try them, "m" measures the current filter as pll_test_vdd does (spectrum +
#                                  # Phase Noise mode jitter) into results/pll/pll_filter_tune_<sample>_<stamp>.csv
#

import logging
from datetime import datetime
from pathlib import Path

from sw.lib import pll_setup, vco_lut
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8, LOOP_FILTER
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.lab_instruments.drivers.rohde_schwarz_fsv_spectrum import PNO_MAX_SPOT_MARKERS
from sw.lib.pll_spectrum import (FB_DIV, OFFSET_SPAN_MAP, OUT_OFFSET_RATIO, RESULTS_DIR, SPUR_THRESHOLD_DB,
                                 offsets_for, open_spectrum)
from sw.tests.pll_spur_zoom import LOCK_TIMEOUT, SPUR_POINTS
from sw.tests.pll_test_vctrl import loop_cfg, measure_pll_vctrl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

F_REF = 32e6  # reference on the PLL input [Hz], set by hand; the VCO runs at FB_DIV x F_REF = 4096 MHz
# Phase-noise mode on the analyzer (show_phase_noise): lowest offset [Hz] (as OFFSET_SPAN_MAP), RBW as % of the offset
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
# tune_filter: the short names you type for the loop-filter codes (each 0-7), and the PLL supply channel it records
FILTER_KEYS = dict(icp="set_current", c1="set_c1", c2="set_c2", r1="set_r1")
SUPPLY_CHANNEL = 2  # E36312A (meas_setup.yaml power_supply_pll) CH2; only read, the voltage is not changed


def show_phase_noise(f_pad, offset_start=PNO_OFFSET_START, rbw_percent=PNO_RBW_PERCENT, spur_removal=PNO_SPUR_REMOVAL):
    """Put the analyzer in its Phase Noise application on a carrier at `f_pad` [Hz] and leave it sweeping
    continuously for viewing: carrier verified against f_pad and PNO_CARRIER_DBM within PNO_FREQ_TOL_HZ /
    PNO_LEVEL_TOL_DB and tracked (frequency and level); offsets `offset_start` up to f_pad / OUT_OFFSET_RATIO, RBW
    `rbw_percent` % of the offset, spot-noise markers at the OFFSET_SPAN_MAP offsets that fit,
    spur removal (`spur_removal`, threshold PNO_SPUR_THRESHOLD_DB) and the spur list next to the diagram.
    The VISA session is closed at the end (also on an error); the settings stay on the analyzer (press LOCAL to take
    over)."""
    offsets = sorted(offsets_for(f_pad, OFFSET_SPAN_MAP))[:PNO_MAX_SPOT_MARKERS]  # the analyzer has 5 spot markers
    spectrum = open_spectrum()
    try:
        spectrum.start_phase_noise_mode(f_pad, offset_start, f_pad / OUT_OFFSET_RATIO,
                                        carrier_level_dbm=PNO_CARRIER_DBM, freq_tolerance_hz=PNO_FREQ_TOL_HZ,
                                        level_tolerance_db=PNO_LEVEL_TOL_DB, tracking=True,
                                        rbw_percent=rbw_percent, spur_removal=spur_removal,
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


def parse_filter(answer, loop_filter):
    """`loop_filter` ({FILTER_FIELDS: code}) with the codes typed in `answer`, e.g. "icp 5 c1 3" (FILTER_KEYS, each
    0-7); keys not typed keep their code. Raises ValueError on anything else."""
    words = answer.lower().split()
    if not words or len(words) % 2:
        raise ValueError("type pairs of name and code, e.g. 'icp 5 c1 3'")
    new = dict(loop_filter)
    for key, code in zip(words[0::2], words[1::2]):
        if key not in FILTER_KEYS:
            raise ValueError("unknown filter name %r (one of %s)" % (key, ", ".join(FILTER_KEYS)))
        if not code.isdigit() or not 0 <= int(code) <= 7:
            raise ValueError("%s code must be 0-7, not %r" % (key, code))
        new[FILTER_KEYS[key]] = int(code)
    return new


def filter_text(loop_filter):
    """The loop filter as you type it, e.g. "icp 7 c1 0 c2 0 r1 7"."""
    return " ".join("%s %d" % (key, loop_filter[field]) for key, field in FILTER_KEYS.items())


def manual_point(f_vco, coarse, cur_min, cur_max, loop_filter=None):
    """A tune_filter point with VCO codes you give: coarse `coarse`, min `cur_min`, max `cur_max` at `f_vco` [Hz],
    starting filter `loop_filter` ({FILTER_FIELDS: code}; None: LOOP_FILTER)."""
    codes = dict(vco_tune_coarse=coarse, vco_current_min=cur_min, vco_current_max=cur_max)
    return dict(label="c%d min%d max%d %.0fMHz" % (coarse, cur_min, cur_max, f_vco / 1e6), f_vco=f_vco, codes=codes,
                loop_filter=dict(loop_filter or LOOP_FILTER))


def lut_point(f_vco, vctrl=0.55, kvco=None, sample=None, loop_filter=None):
    """A tune_filter point with the VCO codes the lookup table (vco_lut.VcoLUT of `sample`) picks at `f_vco` [Hz]:
    expected Vctrl closest to `vctrl` [V], among those |Kvco| closest to `kvco` [Hz/V] (None: any)
    (VcoLUT.update_config_vctrl, the pick is logged). The table is ~5 % off in frequency since 2026-10-20; the loop
    still locks, Vctrl lands 15-50 mV from the prediction. Starting filter `loop_filter` (None: LOOP_FILTER)."""
    codes = vco_lut.vco_codes(vco_lut.VcoLUT(sample=sample).update_config_vctrl({}, f_vco, vctrl, kvco=kvco))
    return manual_point(f_vco, codes["vco_tune_coarse"], codes["vco_current_min"], codes["vco_current_max"],
                        loop_filter)


def tune_filter(point=SPUR_POINTS[1], sample=None, csv_path=None):
    """Interactive loop-filter tuning at `point` (a pll_spur_zoom.SPUR_POINTS entry: VCO codes, f_vco, starting
    filter; Vctrl pad off). The reference (f_vco / FB_DIV) comes from the 33600A; the PLL locks with the point's
    filter and the analyzer shows the phase noise live (show_phase_noise, spur removal off: its jitter includes the
    spurs, as the saved numbers). Then, until "q":
      - filter codes, e.g. "icp 5 c1 3" (FILTER_KEYS, 0-7; the others stay): loaded at once, lock logged, the
        analyzer keeps sweeping;
      - "m": measure the current filter as pll_test_vdd.vdd_sweep does (measure_pll_vctrl: spectrum and the Phase
        Noise mode, ~2.5 min, with the PLL supply on CH SUPPLY_CHANNEL recorded), one row in `csv_path` (default a new
        results/pll/pll_filter_tune_<sample>_<stamp>.csv, traces in <stem>_traces.csv), then back to the live view.
    The core is held in reset the whole time (pll_setup.core_in_reset). Reference off and every connection closed at
    the end, also on an error; the supply voltage is not changed. Returns the CSV path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = csv_path or RESULTS_DIR / "pll_filter_tune_{}_{}.csv".format(sample or "nosample",
                                                                          datetime.now().strftime("%Y%m%d_%H%M%S"))
    loop_filter = dict(point["loop_filter"])
    lut = vco_lut.VcoLUT(sample=sample)
    f_vco = point["f_vco"]
    f_ref = f_vco / FB_DIV
    _, total_div = calculate_div_factor(dict(loop_cfg(f_vco, loop_filter=loop_filter), **point["codes"]))
    fg = pll = supply = None
    try:
        with pll_setup.core_in_reset():
            supply = pll_setup.PllSupplyChannel(channel=SUPPLY_CHANNEL)
            answer = ""
            while answer != "q":
                if pll is None:  # (re)start the live view: reference, lock, analyzer
                    fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
                    pll = pll_setup.open_pll(dict(loop_cfg(f_vco, loop_filter=loop_filter), **point["codes"]))
                    logging.info("%s, filter %s: PLL %s", point["label"], filter_text(loop_filter),
                                 "LOCKED" if pll.wait_lock(timeout=LOCK_TIMEOUT) else "NOT LOCKED")
                    show_phase_noise(f_vco / total_div, spur_removal=False)
                answer = input("Filter codes to try (e.g. 'icp 5 c1 3'; now %s), m = measure and save this filter, "
                               "q = quit: " % filter_text(loop_filter)).strip().lower()
                if answer == "m":
                    pll.close()  # measure_pll_vctrl starts the reference and loads the PLL itself
                    fg.close()
                    pll = fg = None
                    row = measure_pll_vctrl(f_vco, float("nan"), sample=sample, lut=lut, csv_path=csv_path,
                                            scope=None, vctrl_pad="off", supply=supply, codes=point["codes"],
                                            loop_filter=loop_filter, phase_noise_mode=True)
                    logging.info("Saved filter %s: %s, jitter (Phase Noise mode) %.1f ps = %.1f ps random + %.1f ps "
                                 "spurs", filter_text(loop_filter), row["status"],
                                 row.get("time_jitter_pnm_ps", float("nan")),
                                 row.get("time_jitter_pnm_random_ps", float("nan")),
                                 row.get("time_jitter_pnm_discrete_ps", float("nan")))
                elif answer and answer != "q":
                    try:
                        loop_filter = parse_filter(answer, loop_filter)
                    except ValueError as e:
                        logging.warning("%s", e)
                        continue
                    pll_setup.load_config(pll, dict(loop_cfg(f_vco, loop_filter=loop_filter), **point["codes"]))
                    logging.info("Filter %s: PLL %s", filter_text(loop_filter),
                                 "LOCKED" if pll.wait_lock(timeout=LOCK_TIMEOUT) else "NOT LOCKED")
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
        if supply is not None:
            supply.close()  # voltage unchanged; CH1 and the outputs untouched
    logging.info("Filter tuning written to %s", csv_path)
    return csv_path


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
    # IC-LAB firewall login: opens the lab network to the analyzer (phase noise on its screen)
    with iclab_session(Parser().get_credentials()):
        # PLL supply and the 32 MHz reference are set by hand before this
        # program(CFG, F_REF, show_pno=False)
        # Loop-filter tuning with the reference current from the battery, at the 1 GHz spur setting (c9 min14 max0,
        # starting filter Icp 7 C1 0 C2 0 R1 7: 14 ps in pll_test_vdd_S5_20261022_131911). PLL supply on CH2
        # (0.75 V), 33600A on the PLL reference input, Vctrl pin header disconnected
        # (1 GHz done 2026-10-22, pll_filter_tune_S5_20261022_142037)
        # tune_filter(SPUR_POINTS[1], sample="S5")
        # High f_vco (|Kvco| ~30-40 GHz/V): 4 GHz, codes from the lookup table (Vctrl ~0.55 V; c0 min 8 max 0 locked
        # at 4.05 GHz with LOOP_FILTER in pll_range_S5_20261013_161640), reference 31.25 MHz from the 33600A. Codes by
        # hand instead: manual_point(4e9, 0, 8, 0). Added to the 1 GHz tuning CSV, so the notebook shows both
        tune_filter(lut_point(8e9, sample="S5"), sample="S5",
                    csv_path=RESULTS_DIR / "pll_filter_tune_S5_20261022_142037.csv")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

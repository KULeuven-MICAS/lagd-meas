# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Output divider check on the locked PLL. One fixed operating point (f_vco, VCO codes from the lookup table for a
# requested |Kvco|, reference f_vco / FB_DIV: the feedback ratio is fixed, so the VCO stays at f_vco whatever the
# output divider); the output divider is stepped through:
#   - inside the PLL: pll_clk_o_en = 1, total = 2**set_div_freq;
#   - outside the PLL: pll_clk_o_en = 0, clk_div_en = 1, total = 2**set_div_freq * 2 * (clk_div_val + 1)
#     (pll_command_api.calculate_div_factor).
# Per divider the pad is measured with lib/pll_spectrum.measure_output. Checks:
#   - n_meas = f_vco / measured carrier vs the set total divider (a digital divider is exact: this only catches a
#     wrong N; the ppm-level rest is the reference generator's clock against the analyzer's);
#   - L_vco_*: phase noise referred to the VCO (+20 log10 N) should be the same for every divider (as long as the
#     divider and the pad add less noise than the divided VCO);
#   - time jitter over the common band (COMMON_BAND, fits every divider) should be the same too.
# The offsets of each divider stop at f_out / OUT_OFFSET_RATIO (a 7.8 MHz carrier cannot show 50 MHz offsets).
# Dividers that put more than PAD_F_MAX on the pad are skipped (the pad does not drive them: no usable carrier).
#
# Results:
#   results/pll/pll_spectrum_div_<sample>_<stamp>.csv          one row per divider
#   results/pll/pll_spectrum_div_<sample>_<stamp>_traces.csv   averaged spectrum + phase-noise traces per divider
#
# Tests:
#   divider_sweep(f_vco, kvco, sample)   # all DIVIDERS at one operating point
#   hold_divider(f_vco, divider, kvco)   # the same operating point with one divider, held until Enter (manual
#                                        # measurements, e.g. the pad on a scope)
#

import logging
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8_LOOP, FILTER_FIELDS
from sw.lib.pll_spectrum import (FB_DIV, OUTPUT_COLUMNS, PAD_F_MAX, RESULTS_DIR,
                                 TRACE_FIELDS, append_rows, kvco_target_for, measure_output, offsets_for,
                                 trace_csv_path, trace_rows)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Divider settings, all <= PAD_F_MAX (125 MHz) on the pad at 1 GHz: inside the PLL /8../128; outside /10 and /100;
# both together /2 x /4 = /8 (same total as inside /8: compares the paths) and /4 x /10 = /40.
# The external divider input (f_vco / 2**set_div_freq) stays <= 1.25 GHz (vco_measure.EXT_DIV_F_MAX).
DIVIDERS = ([dict(pll_clk_o_en=1, set_div_freq=n) for n in range(3, 8)]
            + [dict(pll_clk_o_en=0, clk_div_en=1, set_div_freq=0, clk_div_val=k) for k in (4, 49)]
            + [dict(pll_clk_o_en=0, clk_div_en=1, set_div_freq=s, clk_div_val=k) for s, k in ((1, 1), (2, 4))])
# Band integrated for every divider, so the jitter can be compared: fits the smallest pad frequency (1 GHz / 128).
COMMON_BAND = (1e3, 1e6)

RESULT_COLUMNS = (["time", "lut_csv", "divider", "pll_clk_o_en", "clk_div_en", "set_div_freq", "clk_div_val",
                   "total_div", "f_vco", "kvco_target"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS)
                  + ["vctrl_pred", "kvco_pred", "f_ref", "ref_vpp", "locked"] + OUTPUT_COLUMNS
                  + list(pll_setup.SUPPLY_COLUMNS))
TRACE_COLUMNS = ["divider", "total_div"] + TRACE_FIELDS


def divider_label(div):
    if div["pll_clk_o_en"]:
        return "int /{}".format(2 ** div["set_div_freq"])
    return "ext /{} x /{}".format(2 ** div["set_div_freq"], 2 * (div["clk_div_val"] + 1))


def divider_sweep(f_vco=1e9, kvco="middle", sample=None, lut=None, supply=None, dividers=None, n_averages=10,
                  span=5e6, spectrum_averages=20, lock_timeout=3.0, common_band=COMMON_BAND, ref_vpp=1.8,
                  run_label=""):
    """Lock the PLL at `f_vco` [Hz] (VCO codes from the lookup table for |Kvco| `kvco` [Hz/V] or "middle", reference
    f_vco / FB_DIV from the 33600A), then for every output divider in `dividers` (default DIVIDERS): load the config,
    wait for lock and measure the pad with measure_output (offsets up to f_out / OUT_OFFSET_RATIO, jitter also over
    `common_band`). The PLL supply `supply` (pll_setup.pll_supply) must already be on; its current is recorded per
    divider. A divider that fails is recorded and the sweep continues; a VISA error stops it. The reference and the
    FPGA link are closed at the end, also on an error. `lut`: the lookup table (vco_lut.VcoLUT); None = the newest
    table of `sample`. `ref_vpp`: reference amplitude [V] (0 -> ref_vpp square into 50 Ohm). `run_label`: appended
    to the CSV name (e.g. "repeat", "vpp1p2") to tell debug runs apart. Returns the CSV path.
    """
    dividers = dividers or DIVIDERS
    lut = lut or vco_lut.VcoLUT(sample=sample)
    target, _, _ = kvco_target_for(lut, f_vco, kvco)
    # the same VCO codes and loop filter (CFG_REF8_LOOP) for every divider below
    vco_cfg = lut.update_config(CFG_REF8_LOOP, f_vco, target)
    op = lut.predict(vco_cfg, f_vco)
    f_ref = f_vco / FB_DIV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_spectrum_div_{}_{}{}.csv".format(sample or "nosample",
                                                                   datetime.now().strftime("%Y%m%d_%H%M%S"),
                                                                   "_" + run_label if run_label else "")
    logging.info("Divider sweep at %.1f MHz (ref %.4f MHz x %d), |Kvco| %.0f MHz/V, %d dividers",
                 f_vco / 1e6, f_ref / 1e6, FB_DIV, op["kvco_pred"] / 1e6, len(dividers))

    fg = pll = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=ref_vpp, channel=1, load=50)
        pll = pll_setup.connect()  # one link; every divider loads its own config on it

        for i, div in enumerate(dividers, 1):
            cfg = dict(vco_cfg, **div)
            _, total_div = calculate_div_factor(cfg)
            label = divider_label(div)
            row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, divider=label,
                       pll_clk_o_en=cfg["pll_clk_o_en"], clk_div_en=cfg["clk_div_en"],
                       set_div_freq=cfg["set_div_freq"], clk_div_val=cfg["clk_div_val"], total_div=total_div,
                       f_vco=f_vco, kvco_target=target, f_ref=f_ref, ref_vpp=ref_vpp, status="error",
                       **vco_lut.vco_codes(cfg), **{k: cfg[k] for k in FILTER_FIELDS}, **op)
            traces = []
            logging.info("=== Divider %d/%d: %s (total /%d) -> %.4f MHz on the pad ===", i, len(dividers), label,
                         total_div, f_vco / total_div / 1e6)
            try:
                pll_setup.load_config(pll, cfg)
                locked = pll.wait_lock(timeout=lock_timeout)
                row["locked"] = int(locked)
                row.update(pll_setup.measure_pll_supply(supply, label=label))
                offsets = offsets_for(f_vco / total_div)
                if f_vco / total_div > PAD_F_MAX:
                    logging.warning("%s: %.1f MHz on the pad > %.0f MHz, which the pad does not drive: not measured",
                                    label, f_vco / total_div / 1e6, PAD_F_MAX / 1e6)
                    row["status"] = "pad_too_high"
                elif not locked:
                    logging.warning("%s: not locked, not measured", label)
                    row["status"] = "not_locked"
                elif len(offsets) < 2:
                    logging.warning("%s: pad frequency %.3f MHz too low for the offsets, not measured", label,
                                    f_vco / total_div / 1e6)
                    row["status"] = "too_low"
                else:
                    meas, traces = measure_output(f_vco, total_div, offsets, n_averages=n_averages, span=span,
                                                  spectrum_averages=spectrum_averages, common_band=common_band,
                                                  pll_div=2 ** cfg["set_div_freq"])
                    row.update(meas)
                    logging.info("%s: divider check f_vco / carrier on the pad = %.3f (set /%d): %s", label,
                                 row["n_meas"], total_div, "OK" if row["divider_ok"] else "WRONG DIVIDER")
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop, outputs off in the finally blocks
            except Exception:
                logging.exception("%s failed, continuing", label)
            finally:
                append_rows(csv_path, RESULT_COLUMNS, [row])
                append_rows(trace_csv_path(csv_path), TRACE_COLUMNS,
                            trace_rows(traces, divider=label, total_div=total_div))
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
    logging.info("Divider sweep written to %s", csv_path)
    return csv_path


def hold_divider(f_vco=1e9, divider=None, kvco="middle", sample=None, lut=None, supply=None, lock_timeout=3.0,
                 ref_vpp=1.8):
    """Lock the PLL at `f_vco` [Hz] with the operating point of divider_sweep (VCO codes from the lookup table for
    |Kvco| `kvco`, loop filter of CFG_REF8_LOOP, reference f_vco / FB_DIV from the 33600A) and output divider
    `divider` (a dict like the DIVIDERS entries, e.g. dict(pll_clk_o_en=1, set_div_freq=3) for /8 inside the PLL),
    then hold it until Enter, for measurements by hand. Pads above PAD_F_MAX are set too (only a warning).

    Logs the setting, the lock bit and the PLL supply (`supply`: pll_setup.pll_supply, None = not measured); after
    Enter the lock bit and the supply once more. The reference is turned off and the FPGA link closed, also on an
    error. `lut`: the lookup table (vco_lut.VcoLUT); None = the newest table of `sample`. `ref_vpp`: reference
    amplitude [V].
    """
    divider = divider or dict(pll_clk_o_en=1, set_div_freq=3)
    lut = lut or vco_lut.VcoLUT(sample=sample)
    target, _, _ = kvco_target_for(lut, f_vco, kvco)
    cfg = dict(lut.update_config(CFG_REF8_LOOP, f_vco, target), **divider)
    op = lut.predict(cfg, f_vco)
    _, total_div = calculate_div_factor(cfg)
    f_ref = f_vco / FB_DIV
    f_pad = f_vco / total_div
    label = divider_label(divider)
    if f_pad > PAD_F_MAX:
        logging.warning("%s: %.1f MHz on the pad > %.0f MHz, which the pad is not specified for", label, f_pad / 1e6,
                        PAD_F_MAX / 1e6)

    fg = pll = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=ref_vpp, channel=1, load=50)
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=lock_timeout)
        logging.info("PLL %s: ref %.4f MHz -> VCO %.1f MHz (x%d), divider %s (total /%d) -> pad %.4f MHz; "
                     "VCO coarse %d min %d max %d (|Kvco| %.0f MHz/V, Vctrl %.2f V predicted), "
                     "Icp %d C1 %d C2 %d R1 %d",
                     "LOCKED" if locked else "NOT LOCKED", f_ref / 1e6, f_vco / 1e6, FB_DIV, label, total_div,
                     f_pad / 1e6, cfg["vco_tune_coarse"], cfg["vco_current_min"], cfg["vco_current_max"],
                     op["kvco_pred"] / 1e6, op["vctrl_pred"], cfg["set_current"], cfg["set_c1"], cfg["set_c2"],
                     cfg["set_r1"])
        pll_setup.measure_pll_supply(supply, label=label)
        input("Divider %s held (pad %.4f MHz); press Enter to stop..." % (label, f_pad / 1e6))
        logging.info("Lock bit at the end: %s", pll.read_lock())
        pll_setup.measure_pll_supply(supply, label="at the end")
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off


def start_log_file():
    """Also write the log to results/logs/pll_spectrum_div_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_spectrum_div_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # PLL supply: fixed on the board, always on (no SMU since 2026-10-19): power columns stay NaN
        # 1 GHz, |Kvco| in the geometric middle of the S5 table's range; all DIVIDERS (~1.5 min each)
        divider_sweep(1e9, "middle", sample="S5")

        # Debug steps of the in-band noise of /8 vs /128 (sw/tools/notebooks/pll_div_debug.ipynb):
        int8, int128 = dict(pll_clk_o_en=1, set_div_freq=3), dict(pll_clk_o_en=1, set_div_freq=7)

        # Debug step 4b (no longer possible: it needs the PLL VDD from the 2450 SMU, removed on 2026-10-19): /8 and
        # /128 per PLL VDD 0.75, 0.70, 0.65, 0.75 V. If the pad couples in through the PLL supply, the /8 - /128 gap
        # changes with VDD.

        # Debug step 4a: reference edge slope. Coupling into the reference input shifts its switching moment by
        # V_coupled / slope; a smaller reference (same rise time, so a smaller slope) should hurt /8 much more
        # than /128 if that is the path. 1.8 V again at the end: drift check. A run that does not lock is
        # recorded as not_locked.
        # for vpp in (1.8, 1.2, 0.9, 1.8):
        #     divider_sweep(1e9, "middle", sample="S5", dividers=[int8, int128], ref_vpp=vpp,
        #                   run_label="vpp{:.1f}".format(vpp).replace(".", "p"))

        # Debug step 1: is the /8 vs /128 difference repeatable, independent of the sweep order (~1.5 min each)
        # divider_sweep(1e9, "middle", sample="S5", dividers=[int8, int128, int8, int128, int8], run_label="repeat")

        # 1 GHz, |Kvco| in the geometric middle of the S5 table's range, one divider held until Enter (scope by
        # hand): set_div_freq n -> pad 1 GHz / 2**n
        # hold_divider(1e9, dict(pll_clk_o_en=1, set_div_freq=0), "middle", sample="S5")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

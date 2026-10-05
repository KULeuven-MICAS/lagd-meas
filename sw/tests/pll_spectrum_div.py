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
#

import logging
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8
from sw.lib.pll_spectrum import (FB_DIV, OUTPUT_COLUMNS, PAD_F_MAX, RESULTS_DIR, TRACE_FIELDS, append_rows,
                                 kvco_target_for, measure_output, offsets_for, trace_csv_path, trace_rows)

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
                   "total_div", "f_vco", "kvco_target"] + list(vco_lut.LUT_FIELDS)
                  + ["vctrl_pred", "kvco_pred", "f_ref", "locked"] + OUTPUT_COLUMNS + list(pll_setup.SUPPLY_COLUMNS))
TRACE_COLUMNS = ["divider", "total_div"] + TRACE_FIELDS


def divider_label(div):
    if div["pll_clk_o_en"]:
        return "int /{}".format(2 ** div["set_div_freq"])
    return "ext /{} x /{}".format(2 ** div["set_div_freq"], 2 * (div["clk_div_val"] + 1))


def divider_sweep(f_vco=1e9, kvco="middle", sample=None, lut_csv=None, supply=None, dividers=None, n_averages=10,
                  span=5e6, spectrum_averages=20, lock_timeout=3.0, common_band=COMMON_BAND):
    """Lock the PLL at `f_vco` [Hz] (VCO codes from the lookup table for |Kvco| `kvco` [Hz/V] or "middle", reference
    f_vco / FB_DIV from the 33600A), then for every output divider in `dividers` (default DIVIDERS): load the config,
    wait for lock and measure the pad with measure_output (offsets up to f_out / OUT_OFFSET_RATIO, jitter also over
    `common_band`). The PLL supply `supply` (pll_setup.pll_supply) must already be on; its current is recorded per
    divider. A divider that fails is recorded and the sweep continues; a VISA error stops it. The reference and the
    FPGA link are closed at the end, also on an error. Returns the CSV path.
    """
    dividers = dividers or DIVIDERS
    lut_csv = lut_csv or vco_lut.newest_lut(sample)
    target, _, _ = kvco_target_for(vco_lut.read_lut(lut_csv), f_vco, kvco)
    f_ref = f_vco / FB_DIV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "pll_spectrum_div_{}_{}.csv".format(sample or "nosample",
                                                                 datetime.now().strftime("%Y%m%d_%H%M%S"))

    fg = pll = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        # Operating point with the first divider; the same codes for every divider below
        pick, pll = vco_lut.configure_vco(f_vco, target, cfg=dict(CFG_REF8, **dividers[0]), sample=sample,
                                          lut_csv=lut_csv)
        codes = {k: pick[k] for k in vco_lut.LUT_FIELDS}
        logging.info("Divider sweep at %.1f MHz (ref %.4f MHz x %d): c%d min %d max %d, |Kvco| %.0f MHz/V, %d dividers",
                     f_vco / 1e6, f_ref / 1e6, FB_DIV, *codes.values(), pick["kvco"] / 1e6, len(dividers))

        for i, div in enumerate(dividers, 1):
            cfg = dict(CFG_REF8, **codes, **div)
            _, total_div = calculate_div_factor(cfg)
            label = divider_label(div)
            row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=Path(lut_csv).name, divider=label,
                       pll_clk_o_en=cfg["pll_clk_o_en"], clk_div_en=cfg["clk_div_en"],
                       set_div_freq=cfg["set_div_freq"], clk_div_val=cfg["clk_div_val"], total_div=total_div,
                       f_vco=f_vco, kvco_target=target, vctrl_pred=pick["vctrl"], kvco_pred=pick["kvco"], f_ref=f_ref,
                       status="error", **codes)
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
        # PLL VDD 0.75 V from the 2450 (smu_vdd_pll) for the block, off afterwards (also on an error)
        with pll_setup.pll_supply() as supply:
            # 1 GHz, |Kvco| in the geometric middle of the S5 table's range; all DIVIDERS (~1.5 min each)
            divider_sweep(1e9, "middle", sample="S5", supply=supply)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

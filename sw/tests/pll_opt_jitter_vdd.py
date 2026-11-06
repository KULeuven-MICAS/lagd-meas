# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

#
# PLL Jitter & Power vs Supply Voltage (VDD) Sweep.
#
# Evaluates optimal PLL loop filter configurations across varying core supply voltages (VDD).
# For each target frequency configuration, sweeps VDD downward:
#   VDD = [0.75 V, 0.70 V, 0.65 V, 0.60 V]
#
# Key features:
#   - Fast & focused: omits wide RF spectrum sweeps (_spectra.csv); only measures jitter,
#     phase noise spectra, discrete/reference spurs, and supply power.
#   - Early exit on lock failure: if a configuration fails to lock at a given VDD (e.g. 0.65 V),
#     subsequent lower voltages (e.g. 0.60 V) are automatically skipped for that configuration.
#   - Safe supply restoration: always returns the PLL supply (E36312A CH2) to nominal (0.75 V)
#     after each configuration and in the `finally` block.
#   - Results stored in `results/pll/pll_opt_jitter_vdd_<sample>_<stamp>.csv`
#     and phase noise traces in `<stem>_traces.csv`.
#

import logging
import math
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR
from sw.tests.pll_test_vctrl import measure_pll_vctrl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Supply configuration on Keysight E36312A (CH2 powers the PLL core)
SUPPLY_CHANNEL = 2
NOMINAL_VDD = 0.75
SUPPLY_SETTLE_S = 1.0

# Zoomed reference spur settings:
# Narrow 10 kHz span (+-5 kHz) with 10 Hz RBW (5,001 points -> 5 points/RBW).
REF_SPUR_SPAN = 10e3
REF_SPUR_RBW = 10.0
REF_SPUR_AVERAGES = 5

# Supply voltage steps to evaluate (monotonically decreasing)
VDD_STEPS = (0.85, 0.8, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50)

# Target configurations for 3.2 GHz VDD sensitivity sweep:
# Configuration 1: High VDD range (0.85 V to 0.65 V) with VCO centered at nominal supply
# Configuration 2: Low VDD range (0.60 V down to 0.50 V) optimized for sub-nominal operation down to 0.50 V
TARGET_CONFIGS = [
    {
        "label": "3.2GHz_high_vdd",
        "f_vco": 3.2e9,
        #"codes": dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=12), # This one works
        #"codes": dict(vco_tune_coarse=0, vco_current_min=10, vco_current_max=12),
        "codes": dict(vco_tune_coarse=1, vco_current_min=8, vco_current_max=8),   # This one works
        #"codes": dict(vco_tune_coarse=2, vco_current_min=8, vco_current_max=4),
        "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
        "total_div": 64,
        "vdd_steps": (0.85, 0.8, 0.75, 0.70, 0.65, 0.6),
    },
    {
        "label": "3.2GHz_low_vdd",
        "f_vco": 3.2e9,
        "codes": dict(vco_tune_coarse=0, vco_current_min=11, vco_current_max=2),
        "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
        "total_div": 64,
        "vdd_steps": (0.55, 0.50),
    },
    #{
    #    "label": "4.8GHz_opt",
    #    "f_vco": 4.8e9,
    #    "codes": dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=8),
    #    "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
    #},
    #{
    #    "label": "6.0GHz_opt",
    #    "f_vco": 6.0e9,
    #    "codes": dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=8),
    #    "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
    #},
    #{
    #    "label": "7.0GHz_opt",
    #    "f_vco": 7.0e9,
    #    "codes": dict(vco_tune_coarse=0, vco_current_min=0, vco_current_max=4),
    #    "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
    #},
    #{
    #    "label": "8.0GHz_opt",
    #    "f_vco": 8.0e9,
    #    "codes": dict(vco_tune_coarse=0, vco_current_min=0, vco_current_max=0),
    #    "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
    #},
]


def pll_vdd_sweep(configs=TARGET_CONFIGS, vdds=VDD_STEPS, sample="S5",
                  supply_channel=SUPPLY_CHANNEL, settle_s=SUPPLY_SETTLE_S,
                  ref_spur_span=REF_SPUR_SPAN, ref_spur_rbw=REF_SPUR_RBW,
                  ref_spur_averages=REF_SPUR_AVERAGES,
                  phase_noise_mode=True, csv_path=None, tag=None):
    """Sweep PLL supply voltage (VDD) for specified target configurations.

    Args:
        configs: List of configuration dicts, each with:
                 - 'label': Human-readable string identifier (e.g. '4.8GHz_opt').
                 - 'f_vco': Target VCO frequency in Hz.
                 - 'codes': Dict with {LUT_FIELDS: code} (vco_tune_coarse, vco_current_min, vco_current_max).
                 - 'loop_filter': Dict with {FILTER_FIELDS: code} (set_current, set_r1, set_c1, set_c2).
        vdds: Tuple/list of VDD voltages to sweep (default: 0.75, 0.70, 0.65, 0.60 V).
        sample: Chip sample identifier (default: 'S5').
        supply_channel: Channel on the E36312A power supply (default CH2).
        settle_s: Settle time in seconds after stepping supply voltage.
        phase_noise_mode: If True, also runs FSW K40 Phase Noise Mode application.
        csv_path: Optional explicit CSV path.
        tag: Optional string tag to include in filename.

    Returns:
        tuple: (csv_path, summary_results)
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if csv_path is None:
        tag_str = f"_{tag}" if tag else ""
        csv_path = RESULTS_DIR / "pll_opt_jitter_vdd_{}_{}{}.csv".format(
            sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"), tag_str
        )
    else:
        csv_path = Path(csv_path)

    lut = vco_lut.VcoLUT(sample=sample)
    supply = pll_setup.PllSupplyChannel(channel=supply_channel)
    summary_results = []

    logging.info("=" * 75)
    logging.info("  STARTING PLL VDD SENSITIVITY SWEEP")
    logging.info("  Supply Steps: %s", ", ".join(f"{v:.2f} V" for v in vdds))
    logging.info("  Configurations: %d target frequencies", len(configs))
    logging.info("  Output CSV: %s", csv_path.name)
    logging.info("=" * 75)

    try:
        total_cfgs = len(configs)
        for cfg_idx, cfg_item in enumerate(configs, 1):
            label = cfg_item.get("label", f"cfg_{cfg_idx}")
            f_vco = cfg_item["f_vco"]
            f_ghz = f_vco / 1e9
            f_ref_mhz = (f_vco / FB_DIV) / 1e6
            codes = cfg_item.get("codes")
            loop_filter = cfg_item.get("loop_filter")
            cfg_vdds = cfg_item.get("vdd_steps", cfg_item.get("vdds", vdds))
            total_div = cfg_item.get("total_div", 64)
            lf = dict(loop_filter) if loop_filter else {}
            if "set_div_freq" not in lf:
                lf["set_div_freq"] = int(math.log2(total_div))

            logging.info("")
            logging.info("*" * 75)
            logging.info("  [%d/%d] EVALUATING: %s (f_vco = %.2f GHz, f_ref = %.4f MHz, total_div = %d)",
                         cfg_idx, total_cfgs, label, f_ghz, f_ref_mhz, total_div)
            logging.info("  VCO Codes: %s", codes)
            logging.info("  Loop Filter: %s", lf)
            logging.info("  Supply Steps: %s", ", ".join(f"{v:.2f} V" for v in cfg_vdds))
            logging.info("*" * 75)

            for vdd_idx, vdd in enumerate(cfg_vdds, 1):
                logging.info("--- [%d/%d] Setting VDD = %.3f V on CH%d (settling %.1f s) ---",
                             vdd_idx, len(cfg_vdds), vdd, supply_channel, settle_s)
                supply.set(vdd, settle=settle_s)

                try:
                    row = measure_pll_vctrl(
                        f_vco=f_vco,
                        vctrl=float("nan"),
                        sample=sample,
                        lut=lut,
                        csv_path=csv_path,
                        scope=None,
                        vctrl_pad="off",
                        supply=supply,
                        codes=codes,
                        loop_filter=lf,
                        phase_noise_mode=phase_noise_mode,
                        ref_spur_span=ref_spur_span,
                        ref_spur_rbw=ref_spur_rbw,
                        ref_spur_averages=ref_spur_averages,
                        skip_unlocked=True,
                    )

                    locked = bool(row.get("locked", 0))
                    pnm_jitter_ps = row.get("time_jitter_pnm_ps", float("nan"))
                    trace_jitter_ps = row.get("time_jitter_trace_ps", float("nan"))
                    # Prioritize Phase Noise Mode (PNM) jitter for all primary metrics
                    jitter_ps = pnm_jitter_ps if not math.isnan(pnm_jitter_ps) else trace_jitter_ps
                    noise_ps = row.get("time_jitter_pnm_random_ps", row.get("time_jitter_noise_ps", float("nan")))
                    spur_ps = row.get("time_jitter_pnm_discrete_ps", row.get("time_jitter_spur_ps", float("nan")))
                    pwr_mw = row.get("pll_p", float("nan")) * 1e3
                    v_meas = row.get("pll_vdd", float("nan"))
                    i_ma = row.get("pll_i", float("nan")) * 1e3
                    ref_spur_dbc = row.get("ref_spur_dbc")

                    ref_str = f"{ref_spur_dbc:.1f} dBc" if ref_spur_dbc is not None and not math.isnan(ref_spur_dbc) else "n/a"
                    logging.info("Result @ VDD=%.3f V: Locked=%s | PNM Jitter=%.2f ps (Trace: %.2f ps) | "
                                 "Noise=%.2f ps, Spurs=%.2f ps | Power=%.2f mW (%.2f mA) | Ref Spur=%s",
                                 vdd, locked, pnm_jitter_ps, trace_jitter_ps, noise_ps, spur_ps, pwr_mw, i_ma, ref_str)

                    summary_results.append({
                        "label": label,
                        "f_vco": f_vco,
                        "vdd_target": vdd,
                        "vdd_meas": v_meas,
                        "i_ma": i_ma,
                        "pwr_mw": pwr_mw,
                        "locked": locked,
                        "jitter_ps": jitter_ps,
                        "pnm_jitter_ps": pnm_jitter_ps,
                        "trace_jitter_ps": trace_jitter_ps,
                        "noise_ps": noise_ps,
                        "spur_ps": spur_ps,
                        "ref_spur_dbc": ref_spur_dbc,
                    })

                    # Early exit condition: if PLL fails to lock, skip remaining lower supply voltages
                    if not locked:
                        logging.warning(
                            ">>> PLL lost lock for %s at VDD = %.3f V! "
                            "Skipping remaining lower voltages (%.2f V and below) for this configuration. <<<",
                            label, vdd, vdd
                        )
                        break

                except pyvisa.VisaIOError:
                    raise  # Instrument communication lost: stop run safely
                except Exception:
                    logging.exception("Measurement failed for %s at VDD = %.3f V, continuing", label, vdd)

            # Restore supply to nominal 0.75 V before configuring the next frequency point
            logging.info("Restoring supply to nominal %.2f V before next configuration", NOMINAL_VDD)
            supply.set(NOMINAL_VDD, settle=settle_s)

    finally:
        if supply is not None:
            logging.info("Cleaning up and safely resetting PLL supply to nominal setpoint")
            supply.close()  # Restores nominal voltage (0.75 V) and releases connection

    logging.info("")
    logging.info("=" * 80)
    logging.info("  PLL VDD SENSITIVITY SWEEP COMPLETED")
    logging.info("  Results CSV: %s", csv_path)
    logging.info("=" * 80)
    for res in summary_results:
        lock_str = "LOCKED" if res["locked"] else "NOT LOCKED"
        pnm_val = res.get("pnm_jitter_ps", float("nan"))
        jit_val = pnm_val if not math.isnan(pnm_val) else res.get("jitter_ps", float("nan"))
        jit_str = f"{jit_val:.2f} ps" if not math.isnan(jit_val) else "n/a"
        logging.info("  %-12s | VDD = %.2f V (%.3f V) | %-10s | PNM Jitter = %-8s | Power = %.2f mW",
                     res["label"], res["vdd_target"], res["vdd_meas"], lock_str, jit_str, res["pwr_mw"])
    logging.info("=" * 80)

    return csv_path, summary_results


def start_log_file():
    """Write run logs to results/logs/pll_opt_jitter_vdd_<stamp>.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_opt_jitter_vdd_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    parser = Parser()

    # Log into IC-LAB lab network and ensure chip core stays in reset during RF measurements
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():
        csv_file, results = pll_vdd_sweep(
            configs=TARGET_CONFIGS,
            vdds=VDD_STEPS,
            sample="S5",
            supply_channel=SUPPLY_CHANNEL,
            settle_s=SUPPLY_SETTLE_S,
            phase_noise_mode=True,
        )
        logging.info("Finished! Results saved to %s", csv_file.name)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:
        logging.exception("Run stopped")
        raise

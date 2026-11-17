# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

#
# PLL Jitter & Power vs Supply Voltage (VDD) Sweep.
#
# Evaluates optimal PLL loop filter configurations across varying core supply voltages (VDD):
#   - 3.2 GHz High-VDD (total_div = 64, f_out = 50.0 MHz, max PNM band = 30 MHz):
#       [0.85 V, 0.80 V, 0.75 V, 0.70 V, 0.65 V, 0.60 V]
#   - 3.2 GHz Low-VDD  (total_div = 64, f_out = 50.0 MHz, max PNM band = 30 MHz):
#       [0.55 V, 0.50 V]
#   - 4.8 GHz Optimal  (total_div = 32, f_out = 150.0 MHz, max PNM band = 50 MHz,
#       settings mirrored from pll_capture_spectrum.py: 100 MHz span @ 10 kHz RBW, 10 averages):
#       [0.75 V, 0.70 V, 0.65 V, 0.60 V]
#
# Key features:
#   - Early exit on lock failure: if a configuration fails to lock at or below nominal VDD
#     (0.75 V), remaining lower voltages for that configuration are skipped.
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

# Wideband RF spectrum settings for 4.8 GHz (mirrored from sw/tests/pll_capture_spectrum.py)
WIDE_SPECTRUM_SPAN = 100e6
WIDE_SPECTRUM_RBW = 10e3
WIDE_SPECTRUM_AVERAGES = 10

# Zoomed reference spur settings:
# Narrow 10 kHz span (+-5 kHz) with 10 Hz RBW (5,001 points -> 5 points/RBW).
REF_SPUR_SPAN = 10e3
REF_SPUR_RBW = 10.0
REF_SPUR_AVERAGES = 5

# Default supply voltage steps to evaluate
VDD_STEPS = (0.85, 0.8, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50)

# Target configurations for VDD sensitivity sweep:
# Configuration 1: 3.2 GHz High VDD range (0.85 V to 0.60 V) with div = 64 (50 MHz out, 30 MHz PNM band)
# Configuration 2: 3.2 GHz Low VDD range (0.55 V down to 0.50 V) with div = 64 (50 MHz out, 30 MHz PNM band)
# Configuration 3: 4.8 GHz Optimal range (0.75 V down to 0.60 V) mirroring pll_capture_spectrum.py (div = 32, 150 MHz out, 50 MHz PNM band)
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
    {
        "label": "4.8GHz_opt",
        "f_vco": 4.8e9,
        "codes": dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=8),
        "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
        "total_div": 32,
        "span": WIDE_SPECTRUM_SPAN,
        "spectrum_rbw": WIDE_SPECTRUM_RBW,
        "spectrum_averages": WIDE_SPECTRUM_AVERAGES,
        "ref_spur_span": REF_SPUR_SPAN,
        "ref_spur_rbw": REF_SPUR_RBW,
        "ref_spur_averages": REF_SPUR_AVERAGES,
        "vdd_steps": (0.75, 0.70, 0.65, 0.60),
    },
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


def _first_valid(*vals):
    """Return the first non-None, non-NaN numeric value, or NaN."""
    for val in vals:
        if val is not None and not math.isnan(val):
            return val
    return float("nan")


def _fmt_val(val, fmt="{:.2f}", unit=""):
    """Format a float value safely, returning 'n/a' when None or NaN."""
    return f"{fmt.format(val)}{unit}" if val is not None and not math.isnan(val) else "n/a"


def _select_max_pnm_band(row):
    """Select the highest available PNM integration band and return (band_label, total_ps, random_ps, discrete_ps)."""
    band_candidates = (
        ("50M", "time_jitter_pnm_50MHz_ps", "time_jitter_pnm_random_50MHz_ps", "time_jitter_pnm_discrete_50MHz_ps"),
        ("40M", "time_jitter_pnm_40MHz_ps", "time_jitter_pnm_random_40MHz_ps", "time_jitter_pnm_discrete_40MHz_ps"),
        ("30M", "time_jitter_pnm_30MHz_ps", "time_jitter_pnm_random_30MHz_ps", "time_jitter_pnm_discrete_30MHz_ps"),
        ("20M", "time_jitter_pnm_ps", "time_jitter_pnm_random_ps", "time_jitter_pnm_discrete_ps"),
    )
    for band_label, tot_col, rand_col, disc_col in band_candidates:
        val = row.get(tot_col)
        if val is not None and not math.isnan(val):
            rand_val = _first_valid(
                row.get(rand_col), row.get("time_jitter_pnm_random_ps"), row.get("time_jitter_noise_ps")
            )
            disc_val = _first_valid(
                row.get(disc_col), row.get("time_jitter_pnm_discrete_ps"), row.get("time_jitter_spur_ps")
            )
            return band_label, val, rand_val, disc_val
    return (
        "n/a",
        float("nan"),
        _first_valid(row.get("time_jitter_pnm_random_ps"), row.get("time_jitter_noise_ps")),
        _first_valid(row.get("time_jitter_pnm_discrete_ps"), row.get("time_jitter_spur_ps")),
    )


def pll_vdd_sweep(configs=TARGET_CONFIGS, vdds=VDD_STEPS, default_total_div=64, sample="S5",
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
                 - 'total_div': Output division factor (default: default_total_div).
                 - Optional spectrum settings ('span', 'spectrum_rbw', 'spectrum_averages',
                   'ref_spur_span', 'ref_spur_rbw', 'ref_spur_averages').
        vdds: Tuple/list of default VDD voltages to sweep when config omits 'vdd_steps'.
        default_total_div: Fallback output division factor if a config omits 'total_div'.
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
    logging.info("  Default Supply Steps: %s", ", ".join(f"{v:.2f} V" for v in vdds))
    logging.info("  Configurations: %d target configurations", len(configs))
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
            total_div = int(cfg_item.get("total_div", default_total_div))
            span = cfg_item.get("span", 5e6)
            spectrum_rbw = cfg_item.get("spectrum_rbw", None)
            spectrum_averages = cfg_item.get("spectrum_averages", 20)
            cfg_ref_spur_span = cfg_item.get("ref_spur_span", ref_spur_span)
            cfg_ref_spur_rbw = cfg_item.get("ref_spur_rbw", ref_spur_rbw)
            cfg_ref_spur_averages = cfg_item.get("ref_spur_averages", ref_spur_averages)

            lf = dict(loop_filter) if loop_filter else {}
            lf["set_div_freq"] = int(round(math.log2(total_div)))

            logging.info("")
            logging.info("*" * 75)
            logging.info("  [%d/%d] EVALUATING: %s (f_vco = %.2f GHz, f_out = %.2f MHz, f_ref = %.4f MHz, div = %d)",
                         cfg_idx, total_cfgs, label, f_ghz, (f_vco / total_div) / 1e6, f_ref_mhz, total_div)
            logging.info("  VCO Codes: %s", codes)
            logging.info("  Loop Filter: %s", lf)
            logging.info("  Spectrum Settings: span=%.1f MHz, rbw=%s, avg=%d | Ref Spur: span=%.1f kHz, rbw=%.0f Hz, avg=%d",
                         span / 1e6,
                         f"{spectrum_rbw:.0f} Hz" if spectrum_rbw is not None else "auto",
                         spectrum_averages,
                         cfg_ref_spur_span / 1e3, cfg_ref_spur_rbw, cfg_ref_spur_averages)
            logging.info("  Supply Steps: %s", ", ".join(f"{v:.2f} V" for v in cfg_vdds))
            logging.info("*" * 75)

            for vdd_idx, vdd in enumerate(cfg_vdds, 1):
                logging.info("--- [%d/%d] Setting VDD = %.3f V on CH%d (settling %.1f s) ---",
                             vdd_idx, len(cfg_vdds), vdd, supply_channel, settle_s)
                supply.set(vdd, settle=settle_s)
                logging.info("  >>> Measuring %s | div=%d (f_out=%.2f MHz) @ VDD=%.3f V <<<",
                             label, total_div, (f_vco / total_div) / 1e6, vdd)

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
                        span=span,
                        spectrum_rbw=spectrum_rbw,
                        spectrum_averages=spectrum_averages,
                        ref_spur_span=cfg_ref_spur_span,
                        ref_spur_rbw=cfg_ref_spur_rbw,
                        ref_spur_averages=cfg_ref_spur_averages,
                        skip_unlocked=True,
                    )

                    locked = bool(row.get("locked", 0))
                    common_10m_ps = row.get("time_jitter_trace_common_ps", float("nan"))
                    trace_20m_ps = row.get("time_jitter_trace_ps", float("nan"))
                    pnm_20m_ps = row.get("time_jitter_pnm_ps", float("nan"))
                    pnm_30m_ps = row.get("time_jitter_pnm_30MHz_ps", float("nan"))
                    pnm_40m_ps = row.get("time_jitter_pnm_40MHz_ps", float("nan"))
                    pnm_50m_ps = row.get("time_jitter_pnm_50MHz_ps", float("nan"))
                    pnm_max_band, pnm_jitter_ps, noise_ps, spur_ps = _select_max_pnm_band(row)
                    jitter_ps = _first_valid(pnm_jitter_ps, trace_20m_ps)
                    pwr_mw = row.get("pll_p", float("nan")) * 1e3
                    v_meas = row.get("pll_vdd", float("nan"))
                    i_ma = row.get("pll_i", float("nan")) * 1e3
                    p_eff = pwr_mw / f_ghz if (not math.isnan(pwr_mw) and f_ghz > 0) else float("nan")
                    fom_db = (
                        10.0 * math.log10(((jitter_ps * 1e-12) ** 2) * pwr_mw)
                        if (not math.isnan(jitter_ps) and jitter_ps > 0 and not math.isnan(pwr_mw) and pwr_mw > 0)
                        else float("nan")
                    )
                    ref_spur_dbc = row.get("ref_spur_dbc")
                    ref_spur_lower_dbc = row.get("ref_spur_lower_dbc")
                    ref_spur_upper_dbc = row.get("ref_spur_upper_dbc")

                    ref_str = (
                        f"worst={_fmt_val(ref_spur_dbc, '{:.1f}', ' dBc')} "
                        f"(-fref={_fmt_val(ref_spur_lower_dbc, '{:.1f}', ' dBc')}, "
                        f"+fref={_fmt_val(ref_spur_upper_dbc, '{:.1f}', ' dBc')})"
                    )
                    logging.info(
                        "Result [div=%d] @ VDD=%.3f V: Locked=%s | Common 10M=%s | Trace 20M=%s | "
                        "PNM [20/30/40/50M]=%s/%s/%s/%s | MaxBand(%s)=%s (rand=%s/spur=%s) | "
                        "Power=%s (%s, Eff=%s) | FoM=%s | Ref Spur %s",
                        total_div, vdd, locked,
                        _fmt_val(common_10m_ps, "{:.2f}", " ps"),
                        _fmt_val(trace_20m_ps, "{:.2f}", " ps"),
                        _fmt_val(pnm_20m_ps, "{:.2f}", " ps"), _fmt_val(pnm_30m_ps, "{:.2f}", " ps"),
                        _fmt_val(pnm_40m_ps, "{:.2f}", " ps"), _fmt_val(pnm_50m_ps, "{:.2f}", " ps"),
                        pnm_max_band, _fmt_val(pnm_jitter_ps, "{:.2f}", " ps"),
                        _fmt_val(noise_ps, "{:.2f}", " ps"), _fmt_val(spur_ps, "{:.2f}", " ps"),
                        _fmt_val(pwr_mw, "{:.2f}", " mW"), _fmt_val(i_ma, "{:.2f}", " mA"),
                        _fmt_val(p_eff, "{:.3f}", " mW/GHz"), _fmt_val(fom_db, "{:.2f}", " dB"),
                        ref_str,
                    )

                    entry = {
                        "label": label,
                        "f_vco": f_vco,
                        "total_div": total_div,
                        "vdd_target": vdd,
                        "vdd_meas": v_meas,
                        "i_ma": i_ma,
                        "pwr_mw": pwr_mw,
                        "p_eff_mw_per_ghz": p_eff,
                        "fom_db": fom_db,
                        "locked": locked,
                        "pnm_max_band": pnm_max_band,
                        "jitter_ps": jitter_ps,
                        "pnm_jitter_ps": pnm_jitter_ps,
                        "common_10m_ps": common_10m_ps,
                        "trace_20m_ps": trace_20m_ps,
                        "trace_jitter_ps": trace_20m_ps,
                        "pnm_20m_ps": pnm_20m_ps,
                        "pnm_30m_ps": pnm_30m_ps,
                        "pnm_40m_ps": pnm_40m_ps,
                        "pnm_50m_ps": pnm_50m_ps,
                        "noise_ps": noise_ps,
                        "spur_ps": spur_ps,
                        "ref_spur_dbc": ref_spur_dbc,
                        "ref_spur_lower_dbc": ref_spur_lower_dbc,
                        "ref_spur_upper_dbc": ref_spur_upper_dbc,
                    }
                    summary_results.append(entry)

                    # Early exit: if PLL fails to lock at or below nominal VDD, skip lower voltages
                    if not locked and vdd <= NOMINAL_VDD:
                        logging.warning(
                            ">>> PLL lost lock for %s (div=%d) at VDD = %.3f V! "
                            "Skipping remaining lower voltages for this configuration. <<<",
                            label, total_div, vdd
                        )
                        break

                except pyvisa.VisaIOError:
                    raise  # Instrument communication lost: stop run safely
                except Exception:
                    logging.exception("Measurement failed for %s (div=%d) at VDD = %.3f V, continuing",
                                      label, total_div, vdd)

            # Restore supply to nominal 0.75 V before configuring the next frequency point
            logging.info("Restoring supply to nominal %.2f V before next configuration", NOMINAL_VDD)
            supply.set(NOMINAL_VDD, settle=settle_s)

    finally:
        if supply is not None:
            logging.info("Cleaning up and safely resetting PLL supply to nominal setpoint")
            supply.close()  # Restores nominal voltage (0.75 V) and releases connection

    logging.info("")
    logging.info("=" * 115)
    logging.info("  PLL VDD SENSITIVITY SWEEP COMPLETED")
    logging.info("  Results CSV: %s", csv_path)
    logging.info("=" * 115)
    for res in summary_results:
        lock_str = "LOCKED" if res["locked"] else "NOT LOCKED"
        logging.info(
            "  %-15s | div=%-2d | VDD=%.2f V (%.3f V) | %-10s | 10M=%s | Tr20M=%s | "
            "PNM [20/30/40/50M]=%s/%s/%s/%s ps | MaxBand(%s)=%s ps (rand=%s/spur=%s) | "
            "Power=%.2f mW (%.3f mW/GHz) | FoM=%s dB | Spur=%s (-:%s/+:%s) dBc",
            res["label"], res.get("total_div", default_total_div), res["vdd_target"], res["vdd_meas"], lock_str,
            _fmt_val(res.get("common_10m_ps")),
            _fmt_val(res.get("trace_20m_ps")),
            _fmt_val(res.get("pnm_20m_ps")), _fmt_val(res.get("pnm_30m_ps")),
            _fmt_val(res.get("pnm_40m_ps")), _fmt_val(res.get("pnm_50m_ps")),
            res.get("pnm_max_band", "n/a"), _fmt_val(res.get("pnm_jitter_ps")),
            _fmt_val(res.get("noise_ps")), _fmt_val(res.get("spur_ps")),
            res["pwr_mw"], res.get("p_eff_mw_per_ghz", float("nan")),
            _fmt_val(res.get("fom_db")),
            _fmt_val(res.get("ref_spur_dbc")),
            _fmt_val(res.get("ref_spur_lower_dbc")),
            _fmt_val(res.get("ref_spur_upper_dbc")),
        )
    logging.info("=" * 115)

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

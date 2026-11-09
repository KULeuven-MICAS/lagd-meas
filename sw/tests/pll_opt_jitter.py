# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

#
# PLL Jitter Optimization Sweep.
#
# Sweeps various PLL configurations (loop filter parameters: I_cp, R_1, C_1, C_2,
# and/or VCO operating points / codes) to evaluate phase noise and find the configuration
# yielding the minimum integrated RMS jitter.
#
# For each configuration point:
#   - Tunes and locks the PLL (with Vctrl pad off to avoid loop disturbance).
#   - Acquires phase noise and computes integrated jitter using `measure_pll_vctrl`
#     (incorporating both spectrum analyzer L(f) integration and Phase Noise mode FSW K40).
#   - Logs scalar results (total jitter, noise contribution, spur contribution, reference spur,
#     power, lock) into `results/pll/pll_opt_jitter_<sample>_<stamp>.csv`.
#   - Stores spectral and phase noise traces into `<stem>_traces.csv`.
#   - Tracks and highlights the best configuration in real time.
#
# Based on the sweep pattern in `sw/tests/pll_test_vdd.py` (vdd_sweep).
#

import itertools
import logging
import math
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_settings import (
    CFG_COARSE0_FAST,
    CFG_COARSE0_FASTEST,
    DEFAULT_FILTER,
    FILTER_FIELDS,
    LOOP_FILTER,
    MIN_JITTER_CFG,
)
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR
from sw.tests.pll_test_vctrl import measure_pll_vctrl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Default PLL supply configuration (0.75 V nominal on E36312A CH2)
SUPPLY_CHANNEL = 2
NOMINAL_VDD = 0.75

# Default VCO codes for target operating frequencies:
# - 4.8 GHz: CFG_COARSE0_FAST (coarse=0, min=8, max=8, Vctrl ~0.51 V, Fref = 37.5 MHz)
# - 6.0 GHz: CFG_COARSE0_FAST (coarse=0, min=8, max=8, Vctrl ~0.47 V, Fref = 46.875 MHz)
# - 7.0 GHz: LUT optimal (coarse=0, min=0, max=4, Vctrl ~0.55 V, Fref = 54.6875 MHz)
# - 8.0 GHz: CFG_COARSE0_FASTEST (coarse=0, min=0, max=0, Vctrl ~0.53 V, Fref = 62.5 MHz)
DEFAULT_FREQ_CONFIGS = {
    4.8e9: dict(label="4.8GHz", codes=vco_lut.vco_codes(CFG_COARSE0_FAST)),
    6.0e9: dict(label="6.0GHz", codes=vco_lut.vco_codes(CFG_COARSE0_FAST)),
    7.0e9: dict(label="7.0GHz", codes=dict(vco_tune_coarse=0, vco_current_min=0, vco_current_max=4)),
    8.0e9: dict(label="8.0GHz", codes=vco_lut.vco_codes(CFG_COARSE0_FASTEST)),
}


def build_filter_sweep_points(f_vco=4.8e9, codes=None, base_filter=None, mode="1d",
                              current_vals=(1, 3, 5, 7),
                              r1_vals=(0, 1, 3, 7),
                              c1_vals=(0, 1, 3, 7),
                              c2_vals=(0, 1, 3, 7),
                              dedup=True):
    """Generate configuration points for sweeping loop filter settings.

    Args:
        f_vco: Target VCO frequency [Hz] (e.g. 4.8e9, 6.0e9, 7.0e9, 8.0e9).
        codes: Specific VCO codes dict (e.g. from CFG_COARSE0_FAST), or None to
               auto-resolve from DEFAULT_FREQ_CONFIGS or VcoLUT lookup.
        base_filter: Baseline filter dict ({FILTER_FIELDS: value}). Defaults to LOOP_FILTER.
        mode: "1d" to sweep each parameter individually holding others at baseline;
              "grid" for a full Cartesian product of all parameter values.
        current_vals: Values to sweep for Charge Pump current `set_current` (0..7).
        r1_vals: Values to sweep for series resistor `set_r1` (0..7).
        c1_vals: Values to sweep for shunt capacitor `set_c1` (0..7).
        c2_vals: Values to sweep for capacitor `set_c2` (0..7).
        dedup: Whether to deduplicate identical filter parameter tuples.

    Returns:
        List of configuration point dicts compatible with `pll_opt_jitter_sweep`.
    """
    if codes is None:
        if f_vco in DEFAULT_FREQ_CONFIGS:
            codes = DEFAULT_FREQ_CONFIGS[f_vco]["codes"]
        else:
            try:
                lut = vco_lut.VcoLUT()
                codes = vco_lut.vco_codes(lut.update_config_vctrl({}, f_vco, 0.55))
            except Exception:
                codes = vco_lut.vco_codes(CFG_COARSE0_FAST)
    base = dict(LOOP_FILTER if base_filter is None else base_filter)
    points = []

    if mode == "1d":
        seen = set()
        # 1D sweeps: vary one parameter at a time from baseline
        for param_name, vals in [
            ("set_current", current_vals),
            ("set_r1", r1_vals),
            ("set_c1", c1_vals),
            ("set_c2", c2_vals),
        ]:
            for val in vals:
                filt = dict(base)
                filt[param_name] = val
                key = (filt["set_current"], filt["set_r1"], filt["set_c1"], filt["set_c2"])
                if dedup and key in seen:
                    continue
                seen.add(key)
                label = (f"{param_name}={val} (baseline: I={base['set_current']}, R1={base['set_r1']}, "
                         f"C1={base['set_c1']}, C2={base['set_c2']})")
                points.append({
                    "label": label,
                    "f_vco": f_vco,
                    "codes": codes,
                    "loop_filter": filt,
                })
    elif mode == "grid":
        # Cartesian grid sweep
        for curr, r1, c1, c2 in itertools.product(current_vals, r1_vals, c1_vals, c2_vals):
            filt = {"set_current": curr, "set_r1": r1, "set_c1": c1, "set_c2": c2}
            label = f"I={curr}, R1={r1}, C1={c1}, C2={c2}"
            points.append({
                "label": label,
                "f_vco": f_vco,
                "codes": codes,
                "loop_filter": filt,
            })
    else:
        raise ValueError(f"Unknown mode: {mode}. Must be '1d' or 'grid'.")

    return points


# Optimal filter configuration identified from coarse sweeps across frequencies:
# Charge pump current maxed (7), series damping resistor maxed (7), shunt cap maxed (7),
# and ripple cap minimum (0).
OPTIMAL_FILTER_BASELINE = dict(set_current=7, set_r1=7, set_c1=7, set_c2=0)


def build_fine_filter_sweep_points(f_vco=4.8e9, codes=None, base_filter=None,
                                   current_vals=(5, 6, 7),
                                   r1_vals=(5, 6, 7),
                                   c1_vals=(4, 5, 6, 7),
                                   c2_vals=(0, 1, 2)):
    """Generate ~10 configuration points tightly clustered around the optimal jitter region.

    Default baseline: `set_current=7, set_r1=7, set_c1=7, set_c2=0`.
    Explores:
      - Charge pump current: I = 5, 6, 7 (2 points perturbed + 1 baseline)
      - Series resistance: R1 = 5, 6, 7 (2 points perturbed)
      - Shunt capacitance: C1 = 4, 5, 6, 7 (3 points perturbed)
      - Ripple capacitance: C2 = 0, 1, 2 (2 points perturbed)
    Yields exactly 10 unique points around the minimum jitter region.
    """
    base = OPTIMAL_FILTER_BASELINE if base_filter is None else base_filter
    return build_filter_sweep_points(
        f_vco=f_vco,
        codes=codes,
        base_filter=base,
        mode="1d",
        current_vals=current_vals,
        r1_vals=r1_vals,
        c1_vals=c1_vals,
        c2_vals=c2_vals,
        dedup=True,
    )


def pll_opt_jitter_sweep(points, sample=None, vdd=NOMINAL_VDD, supply_channel=SUPPLY_CHANNEL,
                         phase_noise_mode=True, unplug_fpga=False, csv_path=None, tag=None):
    """Sweep PLL configurations defined in `points` to measure and optimize jitter.

    Adapted from `vdd_sweep` in `pll_test_vdd.py`.

    Args:
        points: Iterable of configuration point dicts, each with keys:
                - 'label': Human-readable label for logging.
                - 'f_vco': Target VCO frequency in Hz.
                - 'loop_filter': Dict with {FILTER_FIELDS: code} (set_current, set_r1, set_c1, set_c2).
                - 'codes': (Optional) VCO codes dict or None for LUT prediction.
                - 'vctrl': (Optional) Target Vctrl in V if codes is None (defaults to NaN).
        sample: Sample name string (e.g. "S5") for VCO LUT lookup and filename.
        vdd: PLL supply voltage in V (None if powered by battery/bench without remote control).
        supply_channel: Channel on the E36312A power supply (default CH2).
        phase_noise_mode: If True, also measures via the FSW Phase Noise mode application (K40).
        unplug_fpga: Attended mode; prompts to unplug the FPGA after lock and reconnect before config.
        csv_path: Optional exact CSV file path to write results into.
        tag: Optional string tag to include in filename (e.g. "4.8GHz").

    Returns:
        tuple: (csv_path, best_point)
               where best_point is a dict with details of the lowest-jitter configuration found.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if csv_path is None:
        tag_str = f"_{tag}" if tag else ""
        csv_path = RESULTS_DIR / "pll_opt_jitter_{}_{}{}.csv".format(
            sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"), tag_str
        )
    else:
        csv_path = Path(csv_path)

    lut = vco_lut.VcoLUT(sample=sample)
    supply = pll_setup.PllSupplyChannel(channel=supply_channel) if vdd is not None else None
    fpga = pll_setup.FpgaUnplug() if unplug_fpga else None

    best_jitter = float("inf")
    best_point = None
    results = []

    try:
        if supply is not None:
            logging.info("Setting PLL supply to %.3f V on channel %d", vdd, supply_channel)
            supply.set(vdd, settle=1.0)

        n_points = len(points)
        for k, point in enumerate(points, 1):
            label = point.get("label", f"point_{k}")
            f_vco = point["f_vco"]
            loop_filter = point.get("loop_filter")
            codes = point.get("codes")
            vctrl = point.get("vctrl", float("nan"))

            logging.info("=== [%d/%d] Evaluating configuration: %s (f_vco=%.2f MHz) ===",
                         k, n_points, label, f_vco / 1e6)

            try:
                row = measure_pll_vctrl(
                    f_vco=f_vco,
                    vctrl=vctrl,
                    sample=sample,
                    lut=lut,
                    csv_path=csv_path,
                    scope=None,
                    vctrl_pad="off",
                    supply=supply,
                    codes=codes,
                    loop_filter=loop_filter,
                    phase_noise_mode=phase_noise_mode,
                    fpga=fpga,
                )

                # Evaluate jitter result (prefer phase noise mode jitter if available, else trace jitter)
                jitter_ps = row.get("time_jitter_pnm_ps")
                if jitter_ps is None or math.isnan(jitter_ps):
                    jitter_ps = row.get("time_jitter_trace_ps", float("nan"))

                noise_ps = row.get("time_jitter_noise_ps", float("nan"))
                spur_ps = row.get("time_jitter_spur_ps", float("nan"))
                ref_spur_dbm = row.get("ref_spur_dbm")
                ref_spur_dbc = row.get("ref_spur_dbc")
                ref_spur_vco_dbc = row.get("ref_spur_vco_dbc")
                locked = bool(row.get("locked", 0))

                ref_spur_str = (
                    f"{ref_spur_dbc:.1f} dBc ({ref_spur_dbm:.1f} dBm pad, {ref_spur_vco_dbc:.1f} dBc VCO)"
                    if ref_spur_dbc is not None and not math.isnan(ref_spur_dbc)
                    else "n/a"
                )
                logging.info("[%d/%d] Status: %s | Locked: %s | Jitter: %.2f ps (noise: %.2f ps, spurs: %.2f ps) | "
                             "Ref spur: %s",
                             k, n_points, row.get("status", "unknown"), locked, jitter_ps, noise_ps, spur_ps,
                             ref_spur_str)

                if locked and not math.isnan(jitter_ps) and jitter_ps < best_jitter:
                    best_jitter = jitter_ps
                    best_point = {
                        "point": point,
                        "jitter_ps": jitter_ps,
                        "noise_ps": noise_ps,
                        "spur_ps": spur_ps,
                        "ref_spur_dbm": ref_spur_dbm,
                        "ref_spur_dbc": ref_spur_dbc,
                        "ref_spur_vco_dbc": ref_spur_vco_dbc,
                        "row": row,
                    }
                    logging.info(">>> New best configuration! Jitter: %.2f ps | Ref spur: %s <<<",
                                 best_jitter, ref_spur_str)

                results.append(row)

            except pyvisa.VisaIOError:
                raise  # Instrument communication lost: stop the run, safely restoring supply in finally
            except Exception:
                logging.exception("Configuration %s failed, continuing to next", label)

        if fpga is not None:
            fpga.plug()

    finally:
        if fpga is not None and fpga.unplugged:
            logging.warning("The FPGA is still unplugged: plug it back in")
        if supply is not None:
            supply.close()  # Restores nominal voltage and disconnects safely

    logging.info("================ SWEEP SUMMARY ================")
    logging.info("Total points evaluated: %d", len(points))
    logging.info("Results CSV written to: %s", csv_path)
    if best_point is not None:
        p = best_point["point"]
        filt = p.get("loop_filter", {})
        best_ref_dbc = best_point.get("ref_spur_dbc")
        best_ref_str = (
            f"{best_ref_dbc:.1f} dBc on pad ({best_point['ref_spur_vco_dbc']:.1f} dBc @ VCO)"
            if best_ref_dbc is not None and not math.isnan(best_ref_dbc)
            else "n/a"
        )
        logging.info("BEST JITTER: %.2f ps (Noise: %.2f ps, Spurs: %.2f ps) | Ref spur: %s",
                     best_point["jitter_ps"], best_point["noise_ps"], best_point["spur_ps"], best_ref_str)
        logging.info("Best configuration label: %s", p.get("label"))
        logging.info("Best filter parameters: Icp=%s, R1=%s, C1=%s, C2=%s",
                     filt.get("set_current"), filt.get("set_r1"), filt.get("set_c1"), filt.get("set_c2"))
    else:
        logging.warning("No valid locked measurement was obtained.")
    logging.info("===============================================")

    return csv_path, best_point


def start_log_file():
    """Write run logs to results/logs/pll_opt_jitter_<stamp>.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_opt_jitter_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    parser = Parser()

    # Target frequencies to evaluate: 4.8 GHz, 6.0 GHz, 7.0 GHz, 8.0 GHz
    target_freqs = [4.8e9, 6.0e9, 7.0e9, 8.0e9]
    sample = "S5"

    logging.info("=" * 70)
    logging.info("  PLL JITTER & FILTER OPTIMIZATION MULTI-FREQUENCY SWEEP")
    logging.info("  Target VCO Frequencies: %s", ", ".join(f"{f/1e9:.1f} GHz" for f in target_freqs))
    logging.info("=" * 70)

    sweep_results = {}

    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():
        for idx, f_vco in enumerate(target_freqs, 1):
            f_ghz = f_vco / 1e9
            tag = f"{f_ghz:.1f}GHz"
            f_ref_mhz = (f_vco / FB_DIV) / 1e6
            codes = DEFAULT_FREQ_CONFIGS[f_vco]["codes"]

            logging.info("")
            logging.info("*" * 70)
            logging.info("  [%d/%d] RUNNING OPTIMIZATION SWEEP FOR %.1f GHz (Fref = %.4f MHz)",
                         idx, len(target_freqs), f_ghz, f_ref_mhz)
            logging.info("  VCO Codes: %s", codes)
            logging.info("*" * 70)

            # ------------------------------------------------------------------
            # [PREVIOUS COARSE SWEEP - Commented out]
            # 1D sweep: varies each parameter (Icp, R1, C1, C2) independently around baseline LOOP_FILTER
            # points_1d = build_filter_sweep_points(
            #     f_vco=f_vco,
            #     codes=codes,
            #     base_filter=LOOP_FILTER,
            #     mode="1d",
            #     current_vals=(1, 3, 5, 7),
            #     r1_vals=(0, 1, 3, 7),
            #     c1_vals=(0, 1, 3, 7),
            #     c2_vals=(0, 1, 3, 7),
            # )
            #
            # csv_file, best_point = pll_opt_jitter_sweep(
            #     points=points_1d,
            #     sample=sample,
            #     vdd=NOMINAL_VDD,
            #     phase_noise_mode=True,
            #     unplug_fpga=False,
            #     tag=tag,
            # )
            # sweep_results[f_vco] = (csv_file, best_point)
            # logging.info(">>> Finished sweep for %.1f GHz! Results saved to %s <<<", f_ghz, csv_file.name)
            # ------------------------------------------------------------------

            # ------------------------------------------------------------------
            # [NEW FINE SWEEP - Active]
            # Finer sweep: ~10 measurement points clustered around optimal jitter
            # configuration: current=7, r1=7, c1=7, c2=0.
            # ------------------------------------------------------------------
            tag_fine = f"{f_ghz:.1f}GHz_fine"
            points_fine = build_fine_filter_sweep_points(
                f_vco=f_vco,
                codes=codes,
                base_filter=OPTIMAL_FILTER_BASELINE,
                current_vals=(5, 6, 7),
                r1_vals=(5, 6, 7),
                c1_vals=(5, 6, 7),
                c2_vals=(0, 1, 2),
            )

            csv_file, best_point = pll_opt_jitter_sweep(
                points=points_fine,
                sample=sample,
                vdd=NOMINAL_VDD,
                phase_noise_mode=True,
                unplug_fpga=False,
                tag=tag_fine,
            )
            sweep_results[f_vco] = (csv_file, best_point)
            logging.info(">>> Finished fine sweep for %.1f GHz! Results saved to %s <<<", f_ghz, csv_file.name)

    logging.info("")
    logging.info("=" * 70)
    logging.info("  MULTI-FREQUENCY SWEEP RUN COMPLETED")
    for f_vco, (csv_file, best) in sweep_results.items():
        if best:
            ref_spur_str = f"{best['ref_spur_dbc']:.1f} dBc pad" if best.get("ref_spur_dbc") is not None else "n/a"
            logging.info("  %.1f GHz: Best Jitter = %.2f ps (noise: %.2f ps, spur: %.2f ps, ref spur: %s) -> %s",
                         f_vco / 1e9, best["jitter_ps"], best["noise_ps"], best["spur_ps"], ref_spur_str, csv_file.name)
        else:
            logging.warning("  %.1f GHz: No lock obtained -> %s", f_vco / 1e9, csv_file.name)
    logging.info("=" * 70)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:
        logging.exception("Run stopped")
        raise


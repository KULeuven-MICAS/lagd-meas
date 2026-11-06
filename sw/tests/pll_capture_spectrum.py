# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

#
# PLL Phase Noise & Wide Output Spectrum Capture
#
# Dedicated test script to capture:
#   1. High-accuracy Phase Noise spectrum L(f) with respect to the carrier on the output pad,
#      including spot phase noise at key frequency offsets (10 kHz, 100 kHz, 1 MHz)
#      and integrated RMS jitter via FSW K40 Phase Noise Mode.
#   2. Full wideband output RF spectrum with the fundamental carrier dead-center and a 100 MHz
#      span at 10 kHz RBW, revealing both lower and upper reference spurs at f_carrier +- f_ref (37.5 MHz),
#      along with high-resolution zoomed reference spur measurements (10 kHz span, 10 Hz RBW).
#
# Target configuration:
#   - f_vco = 4.8 GHz
#   - Loop filter: current=7, r1=7, c1=7, c2=0
#   - VCO codes: coarse=0, min=8, max=8 (Vctrl ~0.51 V)
#   - Output divider: total_div = 64 (f_carrier = 75.0 MHz on the pad)
#   - Feedback divider: FB_DIV = 128 (f_ref = 37.5 MHz)
#   - Core supply: nominal 0.75 V (E36312A CH2)
#
# Results:
#   results/pll/pll_capture_spectrum_<sample>_<stamp>.csv
#   results/pll/pll_capture_spectrum_<sample>_<stamp>_traces.csv
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

# Target operating configuration: 4.8 GHz with optimal loop filter
TARGET_CONFIG = {
    "label": "4.8GHz_opt",
    "f_vco": 4.8e9,
    "codes": dict(vco_tune_coarse=0, vco_current_min=8, vco_current_max=8),
    "loop_filter": dict(set_current=7, set_r1=7, set_c1=7, set_c2=0),
    "total_div": 64,
}

# Wide RF spectrum settings: 100 MHz span centered on 75 MHz carrier
# (captures lower spur at 37.5 MHz and upper spur at 112.5 MHz) at 10 kHz RBW
# to avoid scalloping loss / filter sweep compression.
WIDE_SPECTRUM_SPAN = 100e6
WIDE_SPECTRUM_RBW = 10e3
WIDE_SPECTRUM_AVERAGES = 10

# High-resolution zoomed reference spur settings around f_carrier +- f_ref:
# narrow 10 kHz span (+-5 kHz) with 10 Hz RBW (5,001 points -> 5 points/RBW).
ZOOMED_REF_SPUR_SPAN = 10e3
ZOOMED_REF_SPUR_RBW = 10.0
ZOOMED_REF_SPUR_AVERAGES = 5


def run_pll_capture_spectrum(f_vco=TARGET_CONFIG["f_vco"],
                             codes=TARGET_CONFIG["codes"],
                             loop_filter=TARGET_CONFIG["loop_filter"],
                             total_div=TARGET_CONFIG["total_div"],
                             sample="S5",
                             span=WIDE_SPECTRUM_SPAN,
                             spectrum_rbw=WIDE_SPECTRUM_RBW,
                             spectrum_averages=WIDE_SPECTRUM_AVERAGES,
                             ref_spur_span=ZOOMED_REF_SPUR_SPAN,
                             ref_spur_rbw=ZOOMED_REF_SPUR_RBW,
                             ref_spur_averages=ZOOMED_REF_SPUR_AVERAGES,
                             supply_channel=SUPPLY_CHANNEL,
                             nominal_vdd=NOMINAL_VDD,
                             settle_s=SUPPLY_SETTLE_S,
                             phase_noise_mode=True,
                             csv_path=None,
                             tag="4.8GHz_opt"):
    """Capture Phase Noise spectrum and wide output RF spectrum with reference spurs for a single PLL setting.

    Args:
        f_vco: Target VCO frequency in Hz (default: 4.8 GHz).
        codes: Dict with {vco_tune_coarse, vco_current_min, vco_current_max}.
        loop_filter: Dict with {set_current, set_r1, set_c1, set_c2}.
        total_div: Output divider ratio (default: 64 -> 75 MHz pad carrier).
        sample: Chip sample identifier (default: 'S5').
        span: Span in Hz for the wide output RF spectrum (default: 100 MHz).
        spectrum_rbw: Resolution bandwidth in Hz for the wideband sweep (default: 10 kHz).
        spectrum_averages: Number of averages for the wideband sweep (default: 10).
        ref_spur_span: Span in Hz for the zoomed reference spur sweep (default: 10 kHz).
        ref_spur_rbw: Resolution bandwidth in Hz for the zoomed reference spur sweep (default: 10 Hz).
        ref_spur_averages: Number of averages for the zoomed reference spur sweep (default: 5).
        supply_channel: Channel on the E36312A power supply (default CH2).
        nominal_vdd: Core supply voltage setpoint (default: 0.75 V).
        settle_s: Settle time in seconds after applying supply setpoint.
        phase_noise_mode: If True, also runs FSW K40 Phase Noise Mode application.
        csv_path: Optional explicit CSV path.
        tag: String tag to include in filename.

    Returns:
        tuple: (csv_path, row_result)
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if csv_path is None:
        tag_str = f"_{tag}" if tag else ""
        csv_path = RESULTS_DIR / "pll_capture_spectrum_{}_{}{}.csv".format(
            sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"), tag_str
        )
    else:
        csv_path = Path(csv_path)

    lut = vco_lut.VcoLUT(sample=sample)
    supply = pll_setup.PllSupplyChannel(channel=supply_channel)

    f_carrier = f_vco / total_div
    f_ref = f_vco / FB_DIV

    logging.info("=" * 80)
    logging.info("  STARTING PLL PHASE NOISE & WIDE SPECTRUM CAPTURE")
    logging.info("  Target Frequency:    f_vco = %.2f GHz (Carrier = %.4f MHz, f_ref = %.4f MHz)",
                 f_vco / 1e9, f_carrier / 1e6, f_ref / 1e6)
    logging.info("  VCO Codes:           %s", codes)
    logging.info("  Loop Filter:         %s", loop_filter)
    logging.info("  Wide Spectrum Span:  %.1f MHz (centered at %.1f MHz, RBW = %.0f Hz, averages = %d)",
                 span / 1e6, f_carrier / 1e6, spectrum_rbw, spectrum_averages)
    logging.info("  Zoomed Ref Spur:     %.1f kHz span, RBW = %.0f Hz (averages = %d)",
                 ref_spur_span / 1e3, ref_spur_rbw, ref_spur_averages)
    logging.info("  Output CSV:          %s", csv_path.name)
    logging.info("=" * 80)

    try:
        # Apply nominal supply
        logging.info("Setting PLL supply VDD = %.3f V on CH%d (settling %.1f s)", nominal_vdd, supply_channel, settle_s)
        supply.set(nominal_vdd, settle=settle_s)

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
            loop_filter=loop_filter,
            phase_noise_mode=phase_noise_mode,
            span=span,
            spectrum_rbw=spectrum_rbw,
            spectrum_averages=spectrum_averages,
            ref_spur_span=ref_spur_span,
            ref_spur_rbw=ref_spur_rbw,
            ref_spur_averages=ref_spur_averages,
            skip_unlocked=True,
        )

        locked = bool(row.get("locked", 0))
        carrier_dbm = row.get("carrier_dbm", float("nan"))
        pnm_jitter_ps = row.get("time_jitter_pnm_ps", float("nan"))
        trace_jitter_ps = row.get("time_jitter_trace_ps", float("nan"))
        ref_spur_dbc = row.get("ref_spur_dbc", float("nan"))
        ref_spur_dbm = row.get("ref_spur_dbm", float("nan"))
        l_10k = row.get("L_pnm_10000", float("nan"))
        l_100k = row.get("L_pnm_100000", float("nan"))
        l_1m = row.get("L_pnm_1000000", float("nan"))

        logging.info("")
        logging.info("=" * 80)
        logging.info("  PLL SPECTRUM CAPTURE RESULTS SUMMARY")
        logging.info("=" * 80)
        logging.info("  Lock Status:               %s", "LOCKED" if locked else "NOT LOCKED")
        logging.info("  Carrier Output Power:      %.2f dBm @ %.4f MHz", carrier_dbm, row.get("f_out_meas", f_carrier) / 1e6)
        logging.info("  Reference Spur Level:      %.2f dBc (%.2f dBm) @ offset %.4f MHz",
                     ref_spur_dbc, ref_spur_dbm, row.get("ref_spur_offset", f_ref) / 1e6)
        logging.info("  Phase Noise @ 10 kHz:      %.2f dBc/Hz", l_10k)
        logging.info("  Phase Noise @ 100 kHz:     %.2f dBc/Hz", l_100k)
        logging.info("  Phase Noise @ 1 MHz:       %.2f dBc/Hz", l_1m)
        logging.info("  Integrated Jitter (PNM):   %.2f ps", pnm_jitter_ps)
        logging.info("  Integrated Jitter (Trace): %.2f ps", trace_jitter_ps)
        logging.info("=" * 80)

    finally:
        if supply is not None:
            logging.info("Cleaning up and safely releasing power supply channel")
            supply.close()

    return csv_path, row


def start_log_file():
    """Write run logs to results/logs/pll_capture_spectrum_<stamp>.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_capture_spectrum_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():
        csv_file, row = run_pll_capture_spectrum(
            f_vco=TARGET_CONFIG["f_vco"],
            codes=TARGET_CONFIG["codes"],
            loop_filter=TARGET_CONFIG["loop_filter"],
            total_div=TARGET_CONFIG["total_div"],
            sample="S5",
            span=WIDE_SPECTRUM_SPAN,
            spectrum_rbw=WIDE_SPECTRUM_RBW,
            spectrum_averages=WIDE_SPECTRUM_AVERAGES,
            ref_spur_span=ZOOMED_REF_SPUR_SPAN,
            ref_spur_rbw=ZOOMED_REF_SPUR_RBW,
            ref_spur_averages=ZOOMED_REF_SPUR_AVERAGES,
            supply_channel=SUPPLY_CHANNEL,
            nominal_vdd=NOMINAL_VDD,
            phase_noise_mode=True,
        )
        logging.info("Measurement complete! Output written to %s", csv_file.name)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:
        logging.exception("Run stopped")
        raise

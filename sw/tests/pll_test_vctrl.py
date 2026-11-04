# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Influence of the control-voltage operating point on the locked PLL. One output frequency; only the VCO codes change:
# per Vctrl target the lookup table (lib/vco_lut.py, VcoLUT.update_config_vctrl) picks the setting whose expected
# Vctrl is closest, so the loop settles at a different Vctrl for the same f_vco, reference and loop filter.
# Background: in the 2026-10-13/20 runs every lock with a predicted Vctrl above ~0.58 V had a ~20 dB higher in-band
# floor (300-2000 ps), most below ~0.56 V were clean (15-110 ps).
#
# Vctrl itself is put on its pad (set_v_ctrl = V_CTRL_PEEK, loop still closed) and watched there on the RTB2004
# (meas_setup.yaml `scope`), channel SCOPE_CH: mean (the real operating point, against the table's prediction),
# peak-to-peak and AC RMS (ripple). The pad disturbs the loop (~10x more jitter, with or without probe, 2026-10-20),
# so by default (vctrl_pad="read") it is connected only to read Vctrl right after lock; the same config is then
# reloaded with the pad off and the lock waited for again before the analyzer measurement (VCTRL_PAD_MODES).
# The output pad is measured on the analyzer with lib/pll_spectrum.measure_output (full phase-noise curve, spurs,
# jitter); phase_noise_mode=True adds the FSW K40.
#
# Results (plotted in sw/tools/notebooks/pll_test_vctrl.ipynb):
#   results/pll/pll_test_vctrl_<sample>_<stamp>.csv          one row per setting: codes, Vctrl pred/meas, jitter, ...
#   results/pll/pll_test_vctrl_<sample>_<stamp>_traces.csv   averaged spectrum + phase-noise traces per setting
#
# Tests:
#   vctrl_sweep(f_vco, n_vctrl, sample)        # n_vctrl Vctrl targets spread over what the table offers at f_vco
#   (the vco_current_max tests: sw/tests/pll_test_current_max.py)
#   measure_pll_vctrl(f_vco, vctrl, sample)    # one setting
#

import logging
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8_LOOP, FILTER_FIELDS
from sw.lib.pll_spectrum import (FB_DIV, OFFSET_SPAN_MAP, OUTPUT_COLUMNS, PNM_COLUMNS, RESULTS_DIR, TRACE_FIELDS,
                                 append_rows, log_method_comparison, measure_output, measure_phase_noise_mode,
                                 offsets_for, pad_divider, trace_csv_path, trace_rows)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

# Vctrl window the settings are picked from (VcoLUT.window, its margin 20 mV stays): wider at the bottom than the
# default (0.5-0.7 V), so the sweep reaches below the ~0.56 V where the runs so far were clean.
VCTRL_WINDOW = (0.45, 0.7)
# Scope on the control node: channel, probe attenuation (10: 10:1 passive probe), vertical scale [V/div] around the
# predicted Vctrl (8 div: +-4 div on screen; an unlocked loop can rail off screen -> NaN), timebase [s/div] (10 us
# on screen: ~20 periods of the ~1.95 MHz interferer, ~80 of a 7.8 MHz reference).
SCOPE_CH = 1
PROBE_ATT = 10
SCOPE_SCALE = 0.05
SCOPE_CENTRE = 0.55  # [V] screen centre when there is no predicted Vctrl (+-0.2 V on screen)
SCOPE_TIMEBASE = 1e-6
# set_v_ctrl (pll_command_api: "00 for default and 11 for out pad", 10 "debug mode"): 0b10 keeps the loop closed with
# the control node also on the Vctrl pad, so the scope can see it; 0b00 is the internal-only default of the other
# scripts (pad disconnected); 0b11 drives the VCO from the pad (open loop, vco_lut), never here.
V_CTRL_PEEK = 0b10
V_CTRL_INTERNAL = 0b00
# What the Vctrl pad does during a measurement (vctrl_pad of measure_pll_vctrl / vctrl_sweep):
#   "off"   pad disconnected the whole time (set_v_ctrl 0b00): no Vctrl reading, the reference behaviour
#   "on"    pad connected the whole time (0b10): Vctrl read before and after the analyzer measurement, but the pad
#           disturbs the loop (~10x more jitter, 32.8 kHz spur family, 2026-10-20), so the spectrum is no reference
#   "read"  pad connected only to read Vctrl right after lock, then the same config reloaded with the pad off (0b00),
#           lock waited for again, then the analyzer measurement: the real operating point and a clean spectrum
VCTRL_PAD_MODES = ("off", "on", "read")
# Band integrated for every setting (time_jitter_trace_common_ps): fits every pad from 25 MHz up.
COMMON_BAND = (1e3, 1e7)

VCTRL_COLUMNS = ["vctrl_meas", "vctrl_meas_std", "vctrl_pkpk", "vctrl_ac_rms", "vctrl_meas_end", "vctrl_pkpk_end",
                 "vctrl_ac_rms_end", "scope_ch", "probe_att"]
RESULT_COLUMNS = (["time", "lut_csv", "f_vco", "vctrl_target", "kvco_request"] + list(vco_lut.LUT_FIELDS)
                  + list(FILTER_FIELDS) + ["vctrl_pred", "kvco_pred", "f_ref", "set_div_freq", "vctrl_pad",
                                           "set_v_ctrl", "total_div", "locked_peek", "locked"]
                  + VCTRL_COLUMNS + OUTPUT_COLUMNS + list(pll_setup.SUPPLY_COLUMNS) + PNM_COLUMNS)
TRACE_COLUMNS = (["f_vco", "vctrl_target"] + list(vco_lut.LUT_FIELDS) + list(FILTER_FIELDS) + ["pll_vdd"]
                 + TRACE_FIELDS)  # codes, filter and measured supply: unique per measured setting


def loop_cfg(f_vco, pad_on=False, loop_filter=None):
    """Closed-loop config (CFG_REF8_LOOP: loop filter LOOP_FILTER) on the direct output, divided inside the PLL to
    50-100 MHz on the pad (pll_spectrum.pad_divider). `pad_on`: the control node also on its pad (set_v_ctrl
    V_CTRL_PEEK), else internal only (V_CTRL_INTERNAL, as in the other scripts). `loop_filter`: another filter
    ({FILTER_FIELDS: code}) instead of LOOP_FILTER. The VCO codes are added by the lookup table or the caller."""
    cfg = dict(CFG_REF8_LOOP, pll_clk_o_en=1, set_div_freq=pad_divider(f_vco),
               set_v_ctrl=V_CTRL_PEEK if pad_on else V_CTRL_INTERNAL)
    if loop_filter:
        cfg.update(loop_filter)
    return cfg


def read_vctrl(scope, end=False):
    """Vctrl on the scope (set up with setup_dc_level) as result columns, the *_end columns when `end`; NaN without
    a scope."""
    nan = float("nan")
    level = {"mean": nan, "mean_std": nan, "pkpk": nan, "ac_rms": nan}
    if scope is not None:
        level = scope.read_dc_level()
    if end:
        return {"vctrl_meas_end": level["mean"], "vctrl_pkpk_end": level["pkpk"], "vctrl_ac_rms_end": level["ac_rms"]}
    return {"vctrl_meas": level["mean"], "vctrl_meas_std": level["mean_std"], "vctrl_pkpk": level["pkpk"],
            "vctrl_ac_rms": level["ac_rms"]}


def measure_pll_vctrl(f_vco=1e9, vctrl=0.55, kvco=None, sample=None, lut=None, csv_path=None, scope=None,
                      vctrl_pad="read", scope_ch=SCOPE_CH, probe_att=PROBE_ATT, supply=None, span=5e6,
                      spectrum_averages=20, n_averages=10, offset_span_map=None, lock_timeout=3.0,
                      skip_unlocked=True, common_band=COMMON_BAND, phase_noise_mode=False, fixed=None,
                      lock_only=False, codes=None, loop_filter=None, fpga=None):
    """Lock the PLL at `f_vco` [Hz] with the VCO codes whose expected Vctrl is closest to `vctrl` [V]
    (VcoLUT.update_config_vctrl; among near-equal Vctrl the |Kvco| closest to `kvco` [Hz/V], None: any), read Vctrl on
    `scope` (pll_setup.open_rtb_scope, channel `scope_ch`; None: no Vctrl reading), measure the output pad with
    pll_spectrum.measure_output.

    `vctrl_pad`: "read" (default): pad on only to read Vctrl right after lock, then the config reloaded with the pad
    off and lock waited for again before the measurement; "on": pad on the whole time (Vctrl also read after the
    measurement; the pad disturbs the loop); "off": pad off the whole time, no reading (VCTRL_PAD_MODES).
    `fixed`: only VCO settings with these codes (VcoLUT.update_config_vctrl), e.g. {"vco_current_max": 14}.
    `codes`: exactly these VCO codes ({LUT_FIELDS: code}) instead of a pick from the table (`vctrl`, `kvco`, `fixed`
    unused; vctrl_pred / kvco_pred NaN where the table says the codes do not reach f_vco).
    `loop_filter`: another loop filter ({FILTER_FIELDS: code}) instead of LOOP_FILTER.
    `phase_noise_mode`: also measure the same lock in the analyzer's Phase Noise application (FSW K40).
    `skip_unlocked`: no analyzer measurement without lock (Vctrl is still read: where the loop rails).
    `lock_only`: only lock (and read Vctrl), no analyzer measurement: status "locked" or "not_locked" (a quick check
    of a sweep before the full run).
    `fpga`: a pll_setup.FpgaUnplug: asks to plug the FPGA in before the configuration and to unplug it before the
    analyzer measurement (None: the FPGA stays connected).
    The reference (f_vco / FB_DIV from the 33600A) is started here and turned off at the end; the scope stays open
    (the caller closes it). Appends one row to `csv_path` (default a new
    results/pll/pll_test_vctrl_<sample>_<stamp>.csv) and the traces to <stem>_traces.csv; returns the row.
    """
    offset_span_map = offset_span_map or OFFSET_SPAN_MAP
    csv_path = csv_path or result_csv_path(sample)
    lut = lut or vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    if vctrl_pad not in VCTRL_PAD_MODES:
        raise ValueError("vctrl_pad must be one of %s, not %r" % (VCTRL_PAD_MODES, vctrl_pad))
    base = loop_cfg(f_vco, pad_on=vctrl_pad != "off", loop_filter=loop_filter)
    if codes:
        cfg = dict(base, **codes)
    else:
        cfg = lut.update_config_vctrl(base, f_vco, vctrl, kvco=kvco, fixed=fixed)
    cfg_meas = dict(cfg, set_v_ctrl=V_CTRL_PEEK if vctrl_pad == "on" else V_CTRL_INTERNAL)  # during the analyzer
    try:
        op = lut.predict(cfg, f_vco)
    except ValueError:  # `codes` the table does not expect at f_vco (it is ~5 % off since 2026-10-20)
        op = {"vctrl_pred": float("nan"), "kvco_pred": float("nan")}
    _, total_div = calculate_div_factor(cfg)
    offset_span_map = offsets_for(f_vco / total_div, offset_span_map)  # band limited by the pad frequency
    f_ref = f_vco / FB_DIV
    row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, f_vco=f_vco,
               vctrl_target=vctrl, kvco_request=kvco, f_ref=f_ref, set_div_freq=cfg["set_div_freq"],
               vctrl_pad=vctrl_pad, set_v_ctrl=cfg_meas["set_v_ctrl"], total_div=total_div,
               scope_ch=scope_ch if scope is not None else None, probe_att=probe_att, status="error",
               **vco_lut.vco_codes(cfg), **{k: cfg[k] for k in FILTER_FIELDS}, **op,
               **read_vctrl(None), **read_vctrl(None, end=True))  # Vctrl columns NaN until read
    traces = []

    fg = pll = None
    try:
        if scope is not None and vctrl_pad != "off":
            centre = op["vctrl_pred"] if not math.isnan(op["vctrl_pred"]) else SCOPE_CENTRE
            scope.setup_dc_level(scope_ch, scale=SCOPE_SCALE, offset=centre, timebase=SCOPE_TIMEBASE,
                                 probe_att=probe_att)
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        if fpga is not None:
            fpga.plug()
        pll = pll_setup.open_pll(cfg)
        locked = pll.wait_lock(timeout=lock_timeout)
        row["locked"] = int(locked)
        if vctrl_pad != "off":
            row["locked_peek"] = int(locked)
            row.update(read_vctrl(scope))
        logging.info("PLL %s at %.1f MHz (ref %.4f MHz x %d), Vctrl predicted %.3f V, measured %.3f V "
                     "(%.1f mV pk-pk, %.2f mV AC RMS), |Kvco| %.0f MHz/V, pad %.4f MHz",
                     "LOCKED" if locked else "NOT LOCKED", f_vco / 1e6, f_ref / 1e6, FB_DIV, op["vctrl_pred"],
                     row["vctrl_meas"], row["vctrl_pkpk"] * 1e3, row["vctrl_ac_rms"] * 1e3, op["kvco_pred"] / 1e6,
                     f_vco / total_div / 1e6)
        if vctrl_pad == "read":
            # Vctrl read: the same config with the pad off for the measurement (the pad disturbs the loop)
            pll_setup.load_config(pll, cfg_meas)
            locked = pll.wait_lock(timeout=lock_timeout)
            row["locked"] = int(locked)
            logging.info("Vctrl pad off (set_v_ctrl %d): PLL %s", cfg_meas["set_v_ctrl"],
                         "LOCKED" if locked else "NOT LOCKED")
        row.update(pll_setup.measure_pll_supply(supply, label="%.1f MHz, Vctrl %.3f V" % (f_vco / 1e6,
                                                                                         op["vctrl_pred"])))
        if not locked and skip_unlocked:
            logging.warning("Not locked: setting not measured (Vctrl target %.3f V)", vctrl)
            row["status"] = "not_locked"
            return row  # the finally block still closes everything and writes the row
        if lock_only:
            row["status"] = "locked" if locked else "not_locked"
            return row

        if fpga is not None:
            fpga.unplug()
        meas, traces = measure_output(f_vco, total_div, offset_span_map, n_averages=n_averages, span=span,
                                      spectrum_averages=spectrum_averages, common_band=common_band)
        row.update(meas)

        if phase_noise_mode and meas["status"] in ("ok", "overload"):
            try:
                pnm, pnm_traces = measure_phase_noise_mode(f_vco, total_div, list(offset_span_map),
                                                           carrier_dbm=meas.get("carrier_dbm"), our_traces=traces)
                row.update(pnm)
                traces += pnm_traces
                log_method_comparison(row, traces)
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop, outputs off in the finally block
            except Exception:
                logging.exception("Phase-noise mode measurement failed; the measure_output results are kept")
                row["pnm_status"] = "error"

        if vctrl_pad == "on":
            row.update(read_vctrl(scope, end=True))  # drift during the measurement
        logging.info("Vctrl after the measurement %.3f V (pad on only); jitter %.1f ps (noise %.1f, spurs %.1f)",
                     row.get("vctrl_meas_end", float("nan")), row.get("time_jitter_trace_ps", float("nan")),
                     row.get("time_jitter_noise_ps", float("nan")), row.get("time_jitter_spur_ps", float("nan")))
    finally:
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
        append_rows(csv_path, RESULT_COLUMNS, [row])
        append_rows(trace_csv_path(csv_path), TRACE_COLUMNS, trace_rows(traces, f_vco=f_vco, vctrl_target=vctrl,
                                                                               **vco_lut.vco_codes(cfg),
                                                                               **{k: cfg[k] for k in FILTER_FIELDS},
                                                                               pll_vdd=row.get("pll_vdd")))
        logging.info("Results written to %s (traces: %s)", csv_path, trace_csv_path(csv_path).name)
    return row


def vctrl_sweep(f_vco=1e9, n_vctrl=8, kvco=None, sample=None, lut=None, scope_ch=SCOPE_CH, probe_att=PROBE_ATT,
                vctrl_pad="read", **kwargs):
    """measure_pll_vctrl for `n_vctrl` Vctrl targets evenly spread over the expected Vctrl of the settings that reach
    `f_vco` (VCTRL_WINDOW), all into one CSV. Targets that pick the same VCO codes as an earlier one are skipped.
    `scope_ch`: scope channel with the probe on the control node; None: no scope (probe removed, for comparison).
    `vctrl_pad`: when the Vctrl pad is connected (VCTRL_PAD_MODES, see measure_pll_vctrl); "off" needs no scope
    (scope_ch=None).
    A setting that fails is recorded and the sweep continues; a VISA error stops it. The scope is closed at the end.
    `kwargs` go to measure_pll_vctrl. Returns the CSV path.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample, window=VCTRL_WINDOW)
    v_lo, v_hi = lut.vctrl_range(f_vco)
    picks, seen = [], []
    for v in np.linspace(v_lo, v_hi, n_vctrl):
        cfg = lut.update_config_vctrl(loop_cfg(f_vco, pad_on=vctrl_pad != "off"), f_vco, v, kvco=kvco)
        codes = vco_lut.vco_codes(cfg)
        if codes in seen:
            logging.info("Vctrl %.3f V: same setting as before (%s), skipped", v, codes)
            continue
        seen.append(codes)
        picks.append(float(v))
    logging.info("Vctrl sweep at %.1f MHz: %d settings, Vctrl targets %s V (table range %.3f-%.3f V)",
                 f_vco / 1e6, len(picks), ", ".join("{:.3f}".format(v) for v in picks), v_lo, v_hi)

    csv_path = result_csv_path(sample)
    scope = pll_setup.open_rtb_scope() if scope_ch is not None else None
    try:
        for i, v in enumerate(picks, 1):
            logging.info("=== Vctrl sweep %d/%d: Vctrl %.3f V ===", i, len(picks), v)
            try:
                measure_pll_vctrl(f_vco, v, kvco=kvco, sample=sample, lut=lut, csv_path=csv_path, scope=scope,
                                  scope_ch=scope_ch, probe_att=probe_att, vctrl_pad=vctrl_pad,
                                  **kwargs)
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop
            except Exception:
                logging.exception("Setting %d (Vctrl %.3f V) failed, continuing", i, v)
    finally:
        if scope is not None:
            scope.close()
    logging.info("Vctrl sweep written to %s", csv_path)
    return csv_path

def result_csv_path(sample, prefix="pll_test_vctrl"):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / "{}_{}_{}.csv".format(prefix, sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def start_log_file():
    """Also write the log to results/logs/pll_test_vctrl_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_test_vctrl_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()), pll_setup.core_in_reset():  # core in reset: no pollution
        # PLL supply: fixed on the board, always on (no SMU since 2026-10-19): power columns stay NaN
        # 1 GHz (ref 7.8125 MHz, pad 62.5 MHz), 8 Vctrl targets over what the S5 table offers; among settings with
        # near-equal Vctrl the |Kvco| closest to 2 GHz/V, so Kvco varies as little as possible (~1.5 min per setting).

        # Reference: Vctrl pad off (set_v_ctrl 0b00, like the earlier runs), no scope: the same settings as the peek
        # runs, x axis = predicted Vctrl. Peeking with the pad on degraded the loop ~10x (2026-10-20 13:13 / 13:45 runs:
        # 32.8 kHz spur family, probe or not), so those runs are no performance reference.
        # (done 2026-10-20 14:10, pll_test_vctrl_S5_20261020_141011)
        # vctrl_sweep(1e9, n_vctrl=8, kvco=2e9, sample="S5", scope_ch=None, vctrl_pad="off")

        # Read Vctrl, then pad off: per setting lock with the pad on, read Vctrl on RTB2004 channel 1 (10:1 passive
        # probe on the pin header), reload with the pad off, lock again, measure. Same settings as the reference.
        # (2026-10-20 14:44, 144402: probe not connected, Vctrl NaN; done again 14:55,
        # pll_test_vctrl_S5_20261020_145555)
        # vctrl_sweep(1e9, n_vctrl=8, kvco=2e9, sample="S5", scope_ch=1, probe_att=10, vctrl_pad="read")

        # Vctrl pad on for the whole measurement (disturbs the loop; without the probe: scope_ch=None)
        # vctrl_sweep(1e9, n_vctrl=8, kvco=2e9, sample="S5", scope_ch=1, probe_att=10, vctrl_pad="on")

        # Active probe (1:1 at the scope input, check its attenuation): only probe_att changes
        # vctrl_sweep(1e9, n_vctrl=8, kvco=2e9, sample="S5", scope_ch=1, probe_att=1, vctrl_pad="read")

        logging.info("Nothing selected in main(): uncomment a sweep above")


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

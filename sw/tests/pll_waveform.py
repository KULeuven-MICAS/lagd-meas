# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# The PLL output clock as it arrives in a 50 Ohm load, on the Keysight MXR058A (lib/lab_instruments/drivers/
# keysight_scope_mxr058a.py): the pad cable into a 50 Ohm scope input instead of the spectrum analyzer, to see the
# waveform the analyzer gets (amplitude, levels, edges, ringing, duty cycle) at the different pad frequencies.
# One VCO frequency, locked (codes from the lookup table for |Kvco| `kvco`, reference f_vco / FB_DIV from the 33600A,
# loop filter `loop_filter`), and the divider inside the PLL stepped (pll_clk_o_en = 1: pad = f_vco / 2**set_div_freq),
# so only the pad frequency changes. Per divider:
#   - lock bit and PLL supply power;
#   - the scope fitted to the clock (timebase for N_PERIODS periods, vertical scale, trigger at the middle); a pad
#     that delivers no usable clock (e.g. above PAD_F_MAX) is captured anyway with the starting settings;
#   - one acquisition: the scope's clock measurements (frequency, Vmax/Vmin/Vpp, top/base/amplitude, rise/fall
#     10-90 %, duty cycle, overshoot/preshoot), the waveform and a screenshot.
#
# Results:
#   results/pll/pll_waveform_<sample>_<stamp>.csv          one row per divider: setting, lock, supply, measurements
#   results/pll/pll_waveform_<sample>_<stamp>_traces.csv   the waveform per divider (time [s], voltage [V])
#   results/pll/pll_waveform_<sample>_<stamp>_div<n>.png   scope screenshot per divider
#
# Tests:
#   waveform_sweep(f_vco, dividers, sample)   # every divider in `dividers` at one VCO frequency
#

import logging
import time
from datetime import datetime
from pathlib import Path

import pyvisa

from sw.lib import pll_setup, vco_lut
from sw.lib.lab_instruments.drivers.keysight_scope_mxr058a import CLOCK_MEASUREMENTS
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_command_api import calculate_div_factor
from sw.lib.pll_settings import CFG_REF8, DEFAULT_FILTER, FILTER_FIELDS
from sw.lib.pll_spectrum import FB_DIV, RESULTS_DIR, append_rows, kvco_target_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"

SCOPE_CH = 1  # scope input the pad cable goes into (set to 50 Ohm)
N_PERIODS = 5  # clock periods over the screen
# Starting vertical setting before the fit: 0.1 V/div around 0.3 V shows -0.2..0.8 V (a 0.6 V swing on 50 Ohm is
# about the +1.8 dBm carrier the analyzer measured at 64 MHz).
START_SCALE, START_OFFSET = 0.1, 0.3

RESULT_COLUMNS = (["time", "lut_csv", "f_vco", "f_ref", "kvco_target"] + list(vco_lut.LUT_FIELDS)
                  + list(FILTER_FIELDS) + ["vctrl_pred", "kvco_pred", "set_div_freq", "total_div", "f_pad", "locked",
                                           "fitted", "averages", "n_samples", "sample_interval"]
                  + list(CLOCK_MEASUREMENTS) + list(pll_setup.SUPPLY_COLUMNS) + ["screenshot", "status"])
TRACE_COLUMNS = ["set_div_freq", "f_pad", "t", "v"]


def waveform_sweep(f_vco=1e9, dividers=range(8), kvco=2e9, loop_filter=DEFAULT_FILTER, sample=None, lut=None,
                   supply=None, channel=SCOPE_CH, n_periods=N_PERIODS, averages=1, lock_timeout=3.0):
    """Lock the PLL at `f_vco` [Hz] and capture the pad clock on the MXR058A (50 Ohm input `channel`) for every divider
    n in `dividers` (pad = f_vco / 2**n).

    VCO codes from the lookup table for |Kvco| `kvco` (pll_spectrum.kvco_target_for), loop filter `loop_filter`
    (pll_settings.DEFAULT_FILTER or LOOP_FILTER), reference f_vco / FB_DIV. `averages` > 1: average that many
    acquisitions per waveform (shows the shape without the jitter). A divider that fails is recorded and the sweep
    continues; a VISA error stops it. The reference and the FPGA link are closed at the end, also on an error; the PLL
    supply `supply` (pll_setup.pll_supply) must already be on. `lut`: the lookup table (vco_lut.VcoLUT); None = the
    newest table of `sample`. Returns the CSV path.
    """
    lut = lut or vco_lut.VcoLUT(sample=sample)
    target, _, _ = kvco_target_for(lut, f_vco, kvco)
    vco_cfg = lut.update_config(dict(CFG_REF8, **loop_filter, pll_clk_o_en=1), f_vco, target)
    op = lut.predict(vco_cfg, f_vco)
    f_ref = f_vco / FB_DIV
    csv_path = result_csv_path(sample)
    logging.info("Waveform sweep at %.1f MHz (ref %.4f MHz x %d), dividers %s, scope CH%d at 50 Ohm",
                 f_vco / 1e6, f_ref / 1e6, FB_DIV, list(dividers), channel)

    fg = pll = scope = None
    try:
        fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        pll = pll_setup.connect()  # one link; every divider loads its own config on it
        scope = pll_setup.open_mxr_scope()
        scope.set_bandwidth("MAX")
        scope.set_acquisition(sample_rate="MAX", points="AUTO", averages=averages)

        for n in dividers:
            cfg = dict(vco_cfg, set_div_freq=n)
            _, total_div = calculate_div_factor(cfg)
            f_pad = f_vco / total_div
            row = dict(time=datetime.now().isoformat(timespec="seconds"), lut_csv=lut.path.name, f_vco=f_vco,
                       f_ref=f_ref, kvco_target=target, set_div_freq=n, total_div=total_div, f_pad=f_pad,
                       averages=averages, status="error", **vco_lut.vco_codes(cfg),
                       **{k: cfg[k] for k in FILTER_FIELDS}, **op)
            traces = []
            logging.info("=== Divider /%d: pad %.4f MHz ===", total_div, f_pad / 1e6)
            try:
                pll_setup.load_config(pll, cfg)
                locked = pll.wait_lock(timeout=lock_timeout)
                row["locked"] = int(locked)
                row.update(pll_setup.measure_pll_supply(supply, label="/%d" % total_div))

                # Start from a fixed view at the expected frequency, then fit to what arrives
                scope.set_channel(channel, scale=START_SCALE, offset=START_OFFSET, impedance=50)
                scope.set_timebase(n_periods / f_pad / 10)
                scope.set_edge_trigger(channel, level=START_OFFSET)
                scope.run()
                time.sleep(0.5)
                row["fitted"] = int(scope.fit_to_signal(channel, n_periods=n_periods))
                scope.digitize(channel)
                meas = scope.measure_clock(channel)
                row.update(meas)
                t, v = scope.get_waveform(channel)
                row.update(n_samples=len(t), sample_interval=t[1] - t[0] if len(t) > 1 else float("nan"))
                traces = [dict(set_div_freq=n, f_pad=f_pad, t=ti, v=vi) for ti, vi in zip(t, v)]
                png = csv_path.with_name("{}_div{}.png".format(csv_path.stem, total_div))
                scope.screenshot(png)
                row["screenshot"] = png.name
                row["status"] = "ok" if row["fitted"] else "no_clock"
                logging.info("/%d: %s, pad %.4f MHz -> scope %.4f MHz, %.3f .. %.3f V (%.3f Vpp, top %.3f / base "
                             "%.3f V), rise %.0f ps, fall %.0f ps, duty %.1f %%, overshoot %.1f %%",
                             total_div, "locked" if locked else "NOT locked", f_pad / 1e6, meas["freq"] / 1e6,
                             meas["vmin"], meas["vmax"], meas["vpp"], meas["vtop"], meas["vbase"],
                             meas["rise"] * 1e12, meas["fall"] * 1e12, meas["duty"], meas["overshoot"])
            except pyvisa.VisaIOError:
                raise  # instrument connection lost: stop, outputs off in the finally block below
            except Exception:
                logging.exception("/%d failed, continuing", total_div)
            finally:
                append_rows(csv_path, RESULT_COLUMNS, [row])
                append_rows(csv_path.with_name(csv_path.stem + "_traces.csv"), TRACE_COLUMNS, traces)
    finally:
        if scope is not None:
            scope.close()
        if pll is not None:
            pll.close()
        if fg is not None:
            fg.close()  # reference off
    logging.info("Waveform sweep written to %s", csv_path)
    return csv_path


def result_csv_path(sample, prefix="pll_waveform"):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / "{}_{}_{}.csv".format(prefix, sample or "nosample", datetime.now().strftime("%Y%m%d_%H%M%S"))


def start_log_file():
    """Also write the log to results/logs/pll_waveform_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "pll_waveform_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
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
            # 1 GHz VCO, |Kvco| ~2 GHz/V, old filter (locks over the widest range): pad 1 GHz, 500 MHz ... 7.8 MHz
            waveform_sweep(1e9, dividers=range(8), kvco=2e9, loop_filter=DEFAULT_FILTER, sample="S5", supply=supply)


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

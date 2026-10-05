# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

#
# Equipment check for the Keysight E36312A triple supply (meas_setup.yaml `power_supply_pll`, 10.91.16.86):
# sets every channel to its voltage / current limit from the YAML, turns the outputs on, reads the voltages
# back and the current and power of CH2 and CH3 (CH3 = PLL supply), then waits for Enter and turns everything
# off again. On any error the outputs are turned off and the connection closed.
#
# Tests:
#   test_psu()      # CH1 5 V / 0.1 A, CH2 0.75 V / 0.01 A, CH3 0.75 V / 0.2 A; CH2 + CH3 current and power
#   test_current_offset()  # nothing connected: current offset of CH2 + CH3 vs output voltage (0 V zero valid?)
#   test_pll_supply()      # 2450 SMU as PLL supply: 0.75 V, current and power
#

import logging
import time
from datetime import datetime
from pathlib import Path

from sw.lib import vco_measure
from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keithley_smu_2450 import KeithleySMU2450
from sw.lib.lab_instruments.drivers.keysight_psu_e36300 import KeysightPSUE36300
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "logs"


def test_psu(cfg_key="power_supply_pll", i_channels=(2, 3), v_tol=0.01, settle=0.5, wait=True):
    """Set every channel from the YAML (voltage, current limit), outputs on, read the voltages back (PASS within
    `v_tol` [V]) and the current and power of `i_channels` (CH3 = PLL supply). With `wait`, the outputs stay on
    until Enter is pressed.
    Outputs off and connection closed at the end, also on an error. Returns True when all voltages pass.
    """
    config = vco_measure.load_instr_cfg()
    psu_cfg = config[cfg_key]
    psu = KeysightPSUE36300(inst.BasePowerSupplyData.from_mapping(psu_cfg))
    ok = True
    try:
        psu.set_verbose(True)
        psu.status()
        channels = list(range(1, len(psu_cfg["channels"]) + 1))
        for ch in channels:
            psu.set_channel(ch)  # voltage + current limit from the YAML
        psu.turn_on_channels(channels)
        time.sleep(settle)
        for ch, ch_cfg in zip(channels, psu_cfg["channels"]):
            v = psu.get_voltage(ch)
            step_ok = abs(v - ch_cfg["voltage"]) <= v_tol
            ok &= step_ok
            logging.info("%s: %s set %.3f V / %.3f A limit -> measured %.4f V", "PASS" if step_ok else "FAIL",
                         ch_cfg["name"], ch_cfg["voltage"], ch_cfg["current"], v)
        for ch in i_channels:
            v, i, p = psu.measure(ch)
            logging.info("%s: %.4f V, %.3f mA, %.3f mW", psu_cfg["channels"][ch - 1]["name"], v, i * 1e3, p * 1e3)
        if wait:
            input("Supplies on. Press Enter to turn all outputs off...")
    finally:
        psu.close()  # outputs off, connection closed
    return ok


def test_current_offset(cfg_key="power_supply_pll", channels=(2, 3), voltages=(0.0, 0.1, 0.25, 0.5, 0.75),
                        n=20, settle=0.5):
    """Current readback offset vs output voltage, with NOTHING connected: per channel and voltage the mean and
    spread of `n` current readings. When the offset does not move with the voltage (beyond the noise of the mean),
    a zero_current() at 0 V at the start of a run calibrates it. Outputs off and connection closed at the end,
    also on an error. Returns {channel: [(v_set, v_meas, i_mean, i_std), ...]}.
    """
    config = vco_measure.load_instr_cfg()
    psu_cfg = config[cfg_key]
    psu = KeysightPSUE36300(inst.BasePowerSupplyData.from_mapping(psu_cfg))
    results = {}
    try:
        psu.status()
        for ch in channels:
            ch_cfg = psu_cfg["channels"][ch - 1]
            psu.set_voltage(ch, voltages[0], current_limit=ch_cfg["current"])
            psu.turn_on_channels(ch)
            results[ch] = []
            for v_set in voltages:
                psu.set_voltage(ch, v_set)
                time.sleep(settle)
                v_meas = psu.get_voltage(ch)
                i_mean, i_std = psu.measure_current_stats(ch, n)
                results[ch].append((v_set, v_meas, i_mean, i_std))
                logging.info("%s at %.3f V (measured %.4f V): offset %+.2f uA, spread %.2f uA (%d readings, "
                             "mean known to %.2f uA)", ch_cfg["name"], v_set, v_meas, i_mean * 1e6, i_std * 1e6,
                             n, i_std / n ** 0.5 * 1e6)
            means = [r[2] for r in results[ch]]
            sem = max(r[3] for r in results[ch]) / n ** 0.5
            change = max(means) - min(means)
            logging.info("%s: offset %+.2f .. %+.2f uA over %.2f-%.2f V, change %.2f uA vs %.2f uA noise of the mean "
                         "-> %s", ch_cfg["name"], min(means) * 1e6, max(means) * 1e6, voltages[0], voltages[-1],
                         change * 1e6, sem * 1e6,
                         "constant: a 0 V zero calibrates it" if change <= 3 * sem else
                         "moves with the voltage: a 0 V zero alone is not enough")
            psu.set_voltage(ch, 0.0)
    finally:
        psu.close()  # outputs off, connection closed
    return results


def test_pll_supply(cfg_key="smu_vdd_pll", vdd=0.75, n=20, settle=0.5, wait=True):
    """The 2450 SMU as PLL supply at `vdd`; logs voltage, current and power (mean of `n` readings). With `wait`,
    VDD stays on until Enter is pressed. Back to 0 V, output off and connection closed at the end, also on an
    error. Returns (v, i, p).
    """
    config = vco_measure.load_instr_cfg()
    smu = KeithleySMU2450(inst.BaseInstrumentData.from_mapping(config[cfg_key]))
    try:
        smu.status()
        smu.set_voltage(vdd)
        smu.output_on()
        smu.wait_settled(vdd)
        time.sleep(settle)
        v, i, i_std = smu.measure_stats(n)
        logging.info("VDD %.4f V: %.4f mA (spread %.3f uA, %d readings), %.4f mW%s", v, i * 1e3, i_std * 1e6, n,
                     v * i * 1e3, "; IN COMPLIANCE: current limited" if smu.in_compliance() else "")
        if wait:
            input("PLL supply on. Press Enter to turn it off...")
    finally:
        smu.close()  # back to 0 V, output off, connection closed
    return v, i, v * i


def start_log_file():
    """Also write the log to results/logs/psu_test_<stamp>.log; returns its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "psu_test_{}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.info("Logging to %s", log_path)
    return log_path


def main():
    # IC-LAB firewall login: opens the lab network to the instruments
    parser = Parser()
    with iclab_session(parser.get_credentials()):
        # test_psu()

        # Current readback offset vs output voltage (nothing connected)
        # test_current_offset()

        # PLL supply from the 2450 SMU (smu_vdd_pll): 0.75 V, current and power
        test_pll_supply()


if __name__ == "__main__":
    start_log_file()
    try:
        main()
    except BaseException:  # also Ctrl+C: record where the run stopped
        logging.exception("Run stopped")
        raise

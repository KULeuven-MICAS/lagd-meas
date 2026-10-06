# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

import sys
import logging
import statistics
import time
import pyvisa
from typing import Union, Dict, List
import random
import contextlib
import csv
import itertools
import os
from datetime import datetime

import yaml
from pathlib import Path

from sw.lib import pll_setup
from sw.lib.pll_driver import PllDriver
from sw.lib.pll_command_api import (
    calculate_div_factor,
    pack_pll_cfg,
    default_cfg_word,
    OP_WRITEBACK,
    STRB_HZ,
    CFG_BITS,
    header,
)
from sw.lib.pll_settings import *

from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.rohde_schwarz_fsv_spectrum import RohdeSchwarzFSVSpectrum
from sw.lib.lab_instruments.drivers.keysight_fg_33600 import KeysightFG33600
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser
from sw.lib.pll_util import calculate_integrated_jitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Device files for the PLL write/read ports (8-bit Xillybus stream).
WRITE_DEV = "/dev/xillybus_write_8"
READ_DEV = "/dev/xillybus_read_8"

# Populated by open_ports(); declared here so the interactive helpers below
# (and `python -i tests/pll_test.py` sessions) can refer to it as a global.
pll: PllDriver

PRJ_ROOT = Path(__file__).resolve().parent.parent
INSTR_CFG_PATH = PRJ_ROOT/"lib"/"lab_instruments"/"config"/"meas_setup.yaml"


def open_ports():
    """Open the PLL ports, exposing them via the module-global `pll`."""
    global pll
    pll = PllDriver(WRITE_DEV, READ_DEV)
    pll.open()


def test_writeback():
    """Send one WRITEBACK command and check the 0xFF header loops back.

    This is the controller-liveness check: it proves the host->FPGA read/write
    path and the command decode are all working, without touching the PLL.
    """
    expected = header(OP_WRITEBACK)  # 0xFF
    received = pll.writeback()
    if received is None:
        logging.error("FAIL: writeback sent 0x%02X, received None", expected)
        return False
    if received == expected:
        logging.info("PASS: writeback echoed 0x%02X. The PLL controller is alive.", received)
        return True
    logging.error("FAIL [mismatch]: writeback sent 0x%02X, received 0x%02X", expected, received)
    return False


def start_pll():
    """Start procedure for the PLL."""
    open_ports()

    if not test_writeback():
        return 1

    # Tune the strobe rate, 1kHz
    pll.set_strb_hz(STRB_HZ)

    # Put the PLL registers in a known state before configuring them.
    pll.reset()
    # Set the clock mux to the external reference
    pll.select_reference()

def config_pll(cfg):
    # Build and load a config
    word = pack_pll_cfg(**cfg)
    if pll.verify_load(word) == word:
        logging.info("config check OK: 0x%012X", word)
        logging.info("Division factor on chip clock: %d, total: %d", *calculate_div_factor(cfg))
    else:
        logging.error("config check FAILED: 0x%012X", word)

    readback = pll.readback()
    logging.info("readback = 0x%012X", readback)
    assert readback == word

    # Move the SoC onto the PLL
    locked = pll.wait_lock(timeout=3)
    if locked:
        pll.select_pll()
        logging.info("PLL lock = %s and selected as the SoC clock", pll.read_lock())
    else:
        logging.error("PLL did not lock; SoC left on the reference clock")

    return 0

def start_pll_and_config(cfg):
    """Start the PLL and load a configuration."""
    start_pll()

    config_pll(cfg)

    return 0


def setup_function_generator():
    parser = Parser()
    # Load the instrument configuration from a YAML file.
    logging.info(f"Loading instrument config from: {INSTR_CFG_PATH}")

    with INSTR_CFG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with iclab_session(parser.get_credentials()):
        # Create an instance of the KeysightFG33600 class with the loaded configuration.
        spectrum = KeysightFG33600(inst.BaseInstrumentData.from_mapping(config["function_generator"]))
        return spectrum

def setup_spectrum_analyzer():
    parser = Parser()
    # Load the instrument configuration from a YAML file.
    logging.info(f"Loading instrument config from: {INSTR_CFG_PATH}")

    with INSTR_CFG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with iclab_session(parser.get_credentials()):
        # Create an instance of the RohdeSchwarzFSVSpectrum class with the loaded configuration.
        spectrum = RohdeSchwarzFSVSpectrum(inst.BaseSpectrumAnalyzerData.from_mapping(config["spectrum_analyzer"]))
        return spectrum


def reset_remote_timer():
    """Workaround: open and close a dummy session to reset the analyzer's 300 s remote-control timer.
    Both the extra instrument connection and the dummy session are closed again."""
    tmp = None
    try:
        tmp = setup_spectrum_analyzer()
        temp_session = tmp._open_resource()
        temp_session.close()
    except pyvisa.VisaIOError as e:
        logging.warning("Failed to open/close dummy session: %s", e)
    finally:
        if tmp is not None:
            tmp.close()


def measure_integrated_jitter(spectrum: RohdeSchwarzFSVSpectrum, center_freq: float, n_averages: int = 10) -> Union[float, float]:
    """
    Measure the integrated jitter using the spectrum analyzer.

    Args:
        spectrum: An instance of the RohdeSchwarzFSVSpectrum class.
        center_freq: Coarse estimate of the fundamental frequency (Hz).
    """

    # Center on the fundamental frequency
    spectrum.center_on_fundamental(center_freq=center_freq, search_span=2.1e3)
    carrier_freq = float(spectrum.query('FREQ:CENT?').strip())
    logging.info(f"Carrier frequency centered at: {carrier_freq} Hz")

    offset_span_map = {
        100.0: 2.1e3,       # 100 Hz offset measured at 2.1 kHz span
        1000.0: 2.1e3,      # 1 kHz offset measured at 2.1 kHz span
        10000.0: 21e3,      # 10 kHz offset measured at 21 kHz span
        100000.0: 210e3,    # 100 kHz offset measured at 210 kHz span
        500000.0: 2.1e6,    # 500 kHz offset measured at 2.1 MHz span
        1000000.0: 2.1e6    # 1 MHz offset measured at 2.1 MHz span
    }

    # Measure the phase noise profile
    phase_noise_profile = spectrum.measure_phase_noise_profile(averages=n_averages, offset_span_map=offset_span_map)

    freq_offsets = list(phase_noise_profile.keys())
    phase_noise_values = list(phase_noise_profile.values())
    logging.info("Frequency offsets: %s", freq_offsets)
    logging.info("Phase noise values: %s", phase_noise_values)

    # Integrated jitter calculation
    rms_time_jitter, rms_phase_jitter = calculate_integrated_jitter(carrier_freq, freq_offsets, phase_noise_values)

    logging.info("Phase Noise Measurements Complete")
    logging.info("Carrier Frequency (Hz): %f", carrier_freq)
    logging.info("Offset Frequency Range (Hz): %f to %f", min(freq_offsets), max(freq_offsets))
    logging.info("RMS Time Jitter: %f ps", rms_time_jitter * 1e12)
    logging.info("RMS Phase Jitter: %f mrad", rms_phase_jitter * 1e3)

    return rms_time_jitter, rms_phase_jitter

def jitter_statistic_variation():
    spectrum = setup_spectrum_analyzer()
    jitter_results = {}
    with contextlib.closing(spectrum):  # analyzer closed on exit, also on an error
        for n_averages in (5, 10, 20):
            measurements = []
            for _ in range(5):

                # Workaround: Reset the 300s remote-control timer
                reset_remote_timer()

                measurements.append(
                    measure_integrated_jitter(
                        spectrum,
                        center_freq=37.5e6,
                        n_averages=n_averages,
                    )
                )

            jitter_results[n_averages] = measurements

    logging.info("Integrated jitter statistical variation results:")
    for n_avg, results in jitter_results.items():
        # Separate the time and phase jitter tuples returned by the measurement function
        time_jitters = [res[0] for res in results]
        phase_jitters = [res[1] for res in results]

        # Calculate means and standard deviations
        time_mean = statistics.mean(time_jitters)
        time_std = statistics.stdev(time_jitters)

        phase_mean = statistics.mean(phase_jitters)
        phase_std = statistics.stdev(phase_jitters)

        # Log the results (scaling to ps and mrad to match your previous measurement logs)
        logging.info(f"--- {n_avg} Sweeps/Averages ---")
        logging.info(f"Time Jitter (ps)   - Mean: {time_mean * 1e12:.4f}, Stdev: {time_std * 1e12:.4f}")
        logging.info(f"Phase Jitter (mrad)- Mean: {phase_mean * 1e3:.4f}, Stdev: {phase_std * 1e3:.4f}")

def sweep_random_configurations(n_averages: int = 10, n_configs: int = 25, supply=None):
    """
    Perform a random sweep of PLL filter configurations and measure integrated jitter.
    """
    # Time estimation based on ~1m45s for 10 averages (10.5s per average)
    acq_time_seconds = 10.5 * n_averages
    total_time_minutes = (acq_time_seconds * n_configs) / 60.0

    # Define the full 4D parameter space and sample
    parameter_space = list(itertools.product(range(8), repeat=4))
    random.seed(42)
    sampled_configs = random.sample(parameter_space, n_configs)

    # Main spectrum analyzer session
    spectrum = setup_spectrum_analyzer()

    # Prepare CSV for incremental saving
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    os.makedirs("results/jitter", exist_ok=True)
    csv_filename = f"results/jitter/jitter_sweep_random_{timestamp}.csv"

    with open(csv_filename, mode='w', newline='') as f, contextlib.closing(spectrum):  # analyzer closed on exit
        writer = csv.writer(f)
        writer.writerow(["set_current", "set_c1", "set_c2", "set_r1", "time_jitter_ps", "phase_jitter_mrad",
                         "pll_vdd_v", "pll_i_ma", "pll_p_mw"])

        logging.info(f"Starting sweep of {n_configs} configurations (n_averages={n_averages}).")
        logging.info(f"Estimated time: {total_time_minutes:.1f} minutes.")
        logging.info(f"Data will be saved to {csv_filename}")

        for idx, (curr, c1, c2, r1) in enumerate(sampled_configs, 1):
            logging.info(f"[{idx}/{n_configs}] Testing cfg: current={curr}, c1={c1}, c2={c2}, r1={r1}")

            # Apply configuration
            cfg = CFG_COARSE2.copy()
            cfg.update(
                set_div_freq=0b110,
                pll_clk_o_en=1,
                set_current=curr,
                set_c1=c1,
                set_c2=c2,
                set_r1=r1,
            )
            config_pll(cfg)

            # PLL supply current and power with this configuration (NaN without the supply SMU)
            p = pll_setup.measure_pll_supply(supply, label=f"cfg {curr},{c1},{c2},{r1}")
            supply_vals = [p["pll_vdd"], p["pll_i"] * 1e3, p["pll_p"] * 1e3]

            # Workaround: Reset the 300s remote-control timer
            reset_remote_timer()

            # Measure
            try:
                time_jitter, phase_jitter = measure_integrated_jitter(
                    spectrum,
                    center_freq=37.5e6,
                    n_averages=n_averages,
                )

                time_jitter_ps = time_jitter * 1e12
                phase_jitter_mrad = phase_jitter * 1e3

                logging.info(f"Result: time = {time_jitter_ps:.3f} ps | phase = {phase_jitter_mrad:.3f} mrad")

                writer.writerow([curr, c1, c2, r1, time_jitter_ps, phase_jitter_mrad] + supply_vals)
                f.flush()

            except Exception as e:
                if isinstance(e, pyvisa.errors.VisaIOError):
                    raise  # instrument connection lost: stop the run, outputs off in the main block
                logging.error(f"Measurement failed for config {curr},{c1},{c2},{r1}: {e}")
                writer.writerow([curr, c1, c2, r1, "ERROR", "ERROR"] + supply_vals)
                f.flush()

    logging.info("Sweep complete!")

def sweep_grid_configurations(sweep_curr: list, sweep_c1: list, sweep_c2: list, sweep_r1: list, n_averages: int = 10,
                              supply=None):
    """
    Perform a grid sweep of specific PLL filter configurations and measure integrated jitter.
    """
    # Generate the full grid of combinations from the provided lists
    parameter_space = list(itertools.product(sweep_curr, sweep_c1, sweep_c2, sweep_r1))
    n_configs = len(parameter_space)

    # Time estimation based on ~1m45s for 10 averages (10.5s per average)
    acq_time_seconds = 10.5 * n_averages
    total_time_minutes = (acq_time_seconds * n_configs) / 60.0

    # Main spectrum analyzer session
    spectrum = setup_spectrum_analyzer()

    # Prepare CSV for incremental saving
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    os.makedirs("results/jitter", exist_ok=True)
    csv_filename = f"results/jitter/jitter_sweep_grid_{timestamp}.csv"

    with open(csv_filename, mode='w', newline='') as f, contextlib.closing(spectrum):  # analyzer closed on exit
        writer = csv.writer(f)
        writer.writerow(["set_current", "set_c1", "set_c2", "set_r1", "time_jitter_ps", "phase_jitter_mrad",
                         "pll_vdd_v", "pll_i_ma", "pll_p_mw"])

        logging.info(f"Starting grid sweep of {n_configs} configurations (n_averages={n_averages}).")
        logging.info(f"Estimated time: {total_time_minutes:.1f} minutes ({total_time_minutes/60:.2f} hours).")
        logging.info(f"Data will be saved to {csv_filename}")

        for idx, (curr, c1, c2, r1) in enumerate(parameter_space, 1):
            logging.info(f"[{idx}/{n_configs}] Testing cfg: current={curr}, c1={c1}, c2={c2}, r1={r1}")

            # Apply configuration
            cfg = CFG_COARSE2.copy()
            cfg.update(
                set_div_freq=0b110,
                pll_clk_o_en=1,
                set_current=curr,
                set_c1=c1,
                set_c2=c2,
                set_r1=r1,
            )
            config_pll(cfg)  # ports already open (main block); reopening them fails

            # PLL supply current and power with this configuration (NaN without the supply SMU)
            p = pll_setup.measure_pll_supply(supply, label=f"cfg {curr},{c1},{c2},{r1}")
            supply_vals = [p["pll_vdd"], p["pll_i"] * 1e3, p["pll_p"] * 1e3]

            # Workaround: Reset the 300s remote-control timer
            reset_remote_timer()

            # Measure
            try:
                time_jitter, phase_jitter = measure_integrated_jitter(
                    spectrum,
                    center_freq=37.5e6,
                    n_averages=n_averages,
                )

                time_jitter_ps = time_jitter * 1e12
                phase_jitter_mrad = phase_jitter * 1e3

                logging.info(f"Result: time = {time_jitter_ps:.3f} ps | phase = {phase_jitter_mrad:.3f} mrad")

                writer.writerow([curr, c1, c2, r1, time_jitter_ps, phase_jitter_mrad] + supply_vals)
                f.flush()

            except Exception as e:
                if isinstance(e, pyvisa.errors.VisaIOError):
                    raise  # instrument connection lost: stop the run, outputs off in the main block
                logging.error(f"Measurement failed for config {curr},{c1},{c2},{r1}: {e}")
                writer.writerow([curr, c1, c2, r1, "ERROR", "ERROR"] + supply_vals)
                f.flush()

    logging.info("Grid sweep complete!")

if __name__ == "__main__":
    cfg = CFG_COARSE2.copy()
    cfg.update(
            set_div_freq=0b110,
            pll_clk_o_en=1,
            set_current=0b011,
            set_c1=0b011,
            set_c2=0b011,
            set_r1=0b011,
    )

    # Reference clock: 18.75 MHz (Fvco = 128 * Fref = 2.4 GHz -> 37.5 MHz on the pad with set_div_freq /64),
    # 0 -> 1.8 V square, 50 % duty, 50 Ohm load. Stays on for the whole run, off when the generator is closed.
    # PLL supply: 0.75 V from the 2450 SMU (smu_vdd_pll), on before the PLL is configured; its current and power
    # are recorded per configuration.
    with iclab_session(Parser().get_credentials()):
        supply = pll_setup.start_pll_supply(0.75)
        try:
            fg = pll_setup.start_reference(18.75e6, vpp=1.8, channel=1, load=50)
        except BaseException:
            supply.close()
            raise
    try:
        start_pll_and_config(cfg)

        sweep_random_configurations(n_averages=10, n_configs=5, supply=supply)

        sweep_grid_configurations(
            sweep_curr=[1, 3, 5, 7],
            sweep_c1=[0, 2, 5, 7],
            sweep_c2=[0, 2, 5, 7],
            sweep_r1=[0, 2, 5, 7],
            n_averages=10,
            supply=supply,
        )
    finally:
        # Also on an error (a VISA error stops the sweeps): reference output off, FPGA ports closed, PLL supply
        # off. The analyzer is closed by the sweep functions themselves.
        fg.close()
        if "pll" in globals():
            pll.close()
        supply.close()

    sys.exit(0)

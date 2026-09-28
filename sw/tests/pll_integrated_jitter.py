# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

import sys
import logging
import time
from typing import Union, Dict, List

import yaml
from pathlib import Path

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


def start_pll_and_config(cfg):
    """Start the PLL and load a configuration."""
    start_pll()

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


def measure_integrated_jitter(spectrum: RohdeSchwarzFSVSpectrum, center_freq: float):
    """
    Measure the integrated jitter using the spectrum analyzer.

    Args:
        spectrum: An instance of the RohdeSchwarzFSVSpectrum class.
        center_freq: Coarse estimate of the fundamental frequency (Hz).
    """

    # Center on the fundamental frequency
    spectrum.center_on_fundamental(center_freq=center_freq, search_span=2.1e3)
    carrier_freq = float(spectrum.query('FREQ:CENT?').strip())

    offset_span_map = {
        100.0: 2.1e3,       # 100 Hz offset measured at 2.1 kHz span
        1000.0: 2.1e3,      # 1 kHz offset measured at 2.1 kHz span
        10000.0: 21e3,      # 10 kHz offset measured at 21 kHz span
        100000.0: 210e3,    # 100 kHz offset measured at 210 kHz span
        500000.0: 2.1e6,    # 500 kHz offset measured at 2.1 MHz span
        1000000.0: 2.1e6    # 1 MHz offset measured at 2.1 MHz span
    }

    # Measure the phase noise profile
    phase_noise_profile = spectrum.measure_phase_noise_profile(averages=10, offset_span_map=offset_span_map)

    freq_offsets = list(phase_noise_profile.keys())
    phase_noise_values = list(phase_noise_profile.values())

    # Integrated jitter calculation
    rms_time_jitter, rms_phase_jitter = calculate_integrated_jitter(carrier_freq, freq_offsets, phase_noise_values)

    logging.info("Phase Noise Measurements Complete")
    logging.info("Carrier Frequency (Hz): %f", carrier_freq)
    logging.info("Offset Frequency Range (Hz): %f to %f", min(freq_offsets), max(freq_offsets))
    logging.info("RMS Time Jitter: %f ps", rms_time_jitter)
    logging.info("RMS Phase Jitter: %f rad", rms_phase_jitter)


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

    start_pll_and_config(cfg)

    spectrum = setup_spectrum_analyzer()
    measure_integrated_jitter(spectrum, center_freq=37.5e6)

    sys.exit(0)

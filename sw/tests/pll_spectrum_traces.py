# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Ivan Ramirez <ivan.ramirezlechuga@kuleuven.be>

import sys
import logging
import time
import pyvisa
from typing import Union, Dict, List
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
from sw.lib.vco_lut import *
from sw.lib.pll_spectrum import *

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

def sweep_grid_averaged_trace(cfgs: list, center_freq: float, span: float,
                              sweep_curr: list = None, sweep_c1: list = None,
                              sweep_c2: list = None, sweep_r1: list = None,
                              n_averages: int = 10, supply=None):
    """
    Perform a grid sweep of PLL filter configurations across a list of base configurations
    and measure the averaged spectrum trace.
    Saves the results in long-format to a CSV file (one row per sweep point).
    """
    if not cfgs:
        logging.warning("No base configurations provided to sweep.")
        return

    # Default to a single None value if a sweep list is not provided
    sweep_curr = sweep_curr if sweep_curr is not None else [None]
    sweep_c1 = sweep_c1 if sweep_c1 is not None else [None]
    sweep_c2 = sweep_c2 if sweep_c2 is not None else [None]
    sweep_r1 = sweep_r1 if sweep_r1 is not None else [None]

    # Generate the full grid: every base config * every parameter combination
    parameter_space = list(itertools.product(range(len(cfgs)), sweep_curr, sweep_c1, sweep_c2, sweep_r1))
    n_configs = len(parameter_space)

    # Time estimation based on ~1m45s for 10 averages (10.5s per average)
    acq_time_seconds = 10.5 * n_averages
    total_time_minutes = (acq_time_seconds * n_configs) / 60.0

    # Main spectrum analyzer session
    spectrum = setup_spectrum_analyzer()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("results/spectrum", exist_ok=True)
    csv_filename = f"results/spectrum/averaged_trace_grid_{timestamp}.csv"

    # Extract base config keys (excluding the sweep parameters to avoid duplicate columns)
    sweep_keys = {"set_current", "set_c1", "set_c2", "set_r1"}
    base_config_keys = [k for k in cfgs[0].keys() if k not in sweep_keys]

    with open(csv_filename, mode='w', newline='') as f, contextlib.closing(spectrum):
        writer = csv.writer(f)

        # Long format header
        header = ["cfg_idx"] + base_config_keys + [
            "set_current", "set_c1", "set_c2", "set_r1",
            "pll_vdd_v", "pll_i_ma", "pll_p_mw",
            "center_hz", "span_hz", "rbw_hz", "vbw_hz",
            "freq_hz", "level_dbm"
        ]
        writer.writerow(header)

        logging.info(f"Starting grid sweep of {n_configs} configurations for averaged trace.")
        logging.info(f"Estimated time: {total_time_minutes:.1f} minutes.")
        logging.info(f"Data will be saved to {csv_filename}")

        for idx, (cfg_idx, curr, c1, c2, r1) in enumerate(parameter_space, 1):
            # Apply configuration
            current_cfg = cfgs[cfg_idx].copy()
            current_cfg['pll_clk_o_en'] = 1

            # Only apply sweep parameters if they were provided; otherwise fall back to base config
            if curr is not None: current_cfg['set_current'] = curr
            if c1 is not None: current_cfg['set_c1'] = c1
            if c2 is not None: current_cfg['set_c2'] = c2
            if r1 is not None: current_cfg['set_r1'] = r1
            # Extract the actual values for logging and CSV (whether swept or from base config)
            actual_curr = current_cfg.get('set_current', "")
            actual_c1 = current_cfg.get('set_c1', "")
            actual_c2 = current_cfg.get('set_c2', "")
            actual_r1 = current_cfg.get('set_r1', "")

            logging.info(f"[{idx}/{n_configs}] Testing base cfg {cfg_idx}: current={actual_curr}, c1={actual_c1}, c2={actual_c2}, r1={actual_r1}")

            config_pll(current_cfg)

            # Extract base config values for the CSV
            base_config_vals = [current_cfg.get(k, "") for k in base_config_keys]

            # Measure PLL supply current and power
            p = pll_setup.measure_pll_supply(supply, label=f"cfg {cfg_idx} - {actual_curr},{actual_c1},{actual_c2},{actual_r1}")
            supply_vals = [p["pll_vdd"], p["pll_i"] * 1e3, p["pll_p"] * 1e3]

            # Workaround: Reset the 300s remote-control timer
            reset_remote_timer()

            try:
                # Measure the averaged trace
                trace = spectrum.averaged_trace(
                    center=center_freq,
                    span=span,
                    averages=n_averages,
                    rbw=10,
                    vbw=10,
                    detector="RMS",
                )

                center = trace['center']
                meas_span = trace['span']
                rbw = trace['rbw']
                vbw = trace['vbw']

                # Write each point in the trace to the CSV
                for f_hz, lvl in zip(trace['freq'], trace['level']):
                    writer.writerow(
                        [cfg_idx] + base_config_vals + [actual_curr, actual_c1, actual_c2, actual_r1] +
                        supply_vals + [center, meas_span, rbw, vbw, f_hz, lvl]
                    )

                f.flush()
                logging.info(f"Trace acquired: {len(trace['freq'])} points.")

            except Exception as e:
                if isinstance(e, pyvisa.errors.VisaIOError):
                    raise  # instrument connection lost: stop the run, outputs off in the main block
                logging.error(f"Measurement failed for config {cfg_idx} - {actual_curr},{actual_c1},{actual_c2},{actual_r1}: {e}")

                # Write an error row so the configuration combination isn't completely lost
                writer.writerow(
                    [cfg_idx] + base_config_vals + [actual_curr, actual_c1, actual_c2, actual_r1] +
                    supply_vals + ["ERROR"] * 6
                )
                f.flush()

    logging.info("Averaged trace grid sweep complete")


def sweep_grid_measure_output(cfgs: list, f_vco: float,
                              sweep_curr: list = None, sweep_c1: list = None,
                              sweep_c2: list = None, sweep_r1: list = None,
                              n_averages: int = 10, span: float = 5e6,
                              spectrum_averages: int = 20, supply=None,
                              common_band=(1e3, 1e6)):
    """
    Perform a grid sweep of PLL filter configurations and evaluate the output
    using the full measure_output() flow.
    Saves the scalar results and detailed traces to separate CSV files.
    """
    if not cfgs:
        logging.warning("No base configurations provided to sweep.")
        return

    # Default to a single None value if a sweep list is not provided
    sweep_curr = sweep_curr if sweep_curr is not None else [None]
    sweep_c1 = sweep_c1 if sweep_c1 is not None else [None]
    sweep_c2 = sweep_c2 if sweep_c2 is not None else [None]
    sweep_r1 = sweep_r1 if sweep_r1 is not None else [None]

    # Generate the full grid: every base config * every parameter combination
    parameter_space = list(itertools.product(range(len(cfgs)), sweep_curr, sweep_c1, sweep_c2, sweep_r1))
    n_configs = len(parameter_space)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("results/spectrum", exist_ok=True)
    csv_path = Path(f"results/spectrum/measure_output_grid_{timestamp}.csv")

    # Extract base config keys (excluding the sweep parameters to avoid duplicate columns)
    sweep_keys = {"set_current", "set_c1", "set_c2", "set_r1"}
    base_config_keys = [k for k in cfgs[0].keys() if k not in sweep_keys]

    # Merge base keys, sweep keys, measure_output columns, and supply columns
    RESULT_COLUMNS = (["time", "cfg_idx"] + base_config_keys +
                      ["set_current", "set_c1", "set_c2", "set_r1"] +
                      OUTPUT_COLUMNS + list(pll_setup.SUPPLY_COLUMNS))

    TRACE_COLUMNS = ["cfg_idx", "set_current", "set_c1", "set_c2", "set_r1", "set_div_freq"] + TRACE_FIELDS

    logging.info(f"Starting grid sweep with measure_output() for {n_configs} configurations.")
    logging.info(f"Data will be saved to {csv_path} and its traces counterpart.")

    for idx, (cfg_idx, curr, c1, c2, r1) in enumerate(parameter_space, 1):
        # Apply configuration
        current_cfg = cfgs[cfg_idx].copy()
        current_cfg['pll_clk_o_en'] = 1

        if curr is not None: current_cfg['set_current'] = curr
        if c1 is not None: current_cfg['set_c1'] = c1
        if c2 is not None: current_cfg['set_c2'] = c2
        if r1 is not None: current_cfg['set_r1'] = r1

        actual_curr = current_cfg.get('set_current', "")
        actual_c1 = current_cfg.get('set_c1', "")
        actual_c2 = current_cfg.get('set_c2', "")
        actual_r1 = current_cfg.get('set_r1', "")

        label = f"cfg {cfg_idx} - {actual_curr},{actual_c1},{actual_c2},{actual_r1}"
        logging.info(f"[{idx}/{n_configs}] Testing {label}")

        base_config_vals = {k: current_cfg.get(k, "") for k in base_config_keys}
        row = dict(time=datetime.now().isoformat(timespec="seconds"), cfg_idx=cfg_idx,
                   set_current=actual_curr, set_c1=actual_c1, set_c2=actual_c2, set_r1=actual_r1,
                   status="error")
        row.update(base_config_vals)
        traces = []

        try:
            config_pll(current_cfg)

            # Extract internal and total division factors needed for measure_output calculations
            pll_div, total_div = calculate_div_factor(current_cfg)

            # Record PLL supply current and power
            row.update(pll_setup.measure_pll_supply(supply, label=label))

            # Filter offsets that fit within the carrier bounds
            offsets = offsets_for(f_vco / total_div)
            if f_vco / total_div > PAD_F_MAX:
                logging.warning(f"{label}: pad frequency > PAD_F_MAX, not measured.")
                row["status"] = "pad_too_high"
            elif len(offsets) < 2:
                logging.warning(f"{label}: pad frequency too low for offsets, not measured.")
                row["status"] = "too_low"
            else:
                # Workaround: Reset the 300s remote-control timer
                reset_remote_timer()

                # Measure carrier, phase noise, jitter, and traces
                meas, traces = measure_output(f_vco=f_vco, total_div=total_div,
                                              offset_span_map=offsets, n_averages=n_averages,
                                              span=span, spectrum_averages=spectrum_averages,
                                              common_band=common_band, pll_div=pll_div)
                row.update(meas)

        except pyvisa.VisaIOError:
            raise # Instrument connection lost: stop the run
        except Exception as e:
            logging.exception(f"{label} failed: {e}")
        finally:
            # Append measurement scalar values to the primary CSV
            append_rows(csv_path, RESULT_COLUMNS, [row])
            if traces:
                # Flatten the traces and append them to the secondary _traces.csv file
                append_rows(trace_csv_path(csv_path), TRACE_COLUMNS,
                            trace_rows(traces, cfg_idx=cfg_idx, set_current=actual_curr,
                                       set_c1=actual_c1, set_c2=actual_c2, set_r1=actual_r1, set_div_freq=current_cfg.get('set_div_freq', "")))

    logging.info("Grid sweep complete.")

if __name__ == "__main__":

    cfg0 = CFG_COARSE0.copy()
    cfg1 = CFG_COARSE1.copy()
    cfg2 = CFG_COARSE2.copy()
    #cfg3 = CFG_REF18_75.copy()

    for cfg in (cfg0, cfg1, cfg2):
        cfg.update(
            set_div_freq=0b101,
            set_v_ctrl=0b00,
            #set_current=0b111,
            #set_c1=0b000,
            #set_c2=0b001,
            #set_r1=0b111,
        )


    cfg_fast = CFG_COARSE0_FAST.copy()
    cfg_fast.update(
        set_div_freq=0b110,
        set_v_ctrl=0b00,
        set_current=0b111,
        set_c1=0b000,
        set_c2=0b001,
        set_r1=0b111,
    )

    cfg_bypass = PLL_BYPASS_CFG.copy()
    cfg_bypass.update(
        pdown_PD=0b1,
        pdown_VCO=0b1,
    )

    lut = VcoLUT(sample="S5")
    cfg_opt = lut.update_config(MIN_JITTER_CFG, f_vco=8e9, kvco=10e9)
    cfg_opt.update(
        set_div_freq=0b110,
        set_v_ctrl=0b00,
    )

    f_ref = 75e6

    # Reference clock: 18.75 MHz (Fvco = 128 * Fref = 2.4 GHz -> 37.5 MHz on the pad with set_div_freq /64),
    # 0 -> 1.8 V square, 50 % duty, 50 Ohm load. Stays on for the whole run, off when the generator is closed.
    # PLL supply: 0.75 V from the 2450 SMU (smu_vdd_pll), on before the PLL is configured; its current and power
    # are recorded per configuration.
    with iclab_session(Parser().get_credentials()):
        supply = pll_setup.start_pll_supply(0.75)
        try:
            fg = pll_setup.start_reference(f_ref, vpp=1.8, channel=1, load=50)
        except BaseException:
            supply.close()
            raise
    try:
        start_pll()

        # Spectrum of bypassed clock
        cfg_bypass_list = []
        for div in (0b000, 0b001, 0b010):
            cfg = cfg_bypass.copy()
            cfg.update(set_div_freq=div)
            cfg_bypass_list.append(cfg)

        sweep_grid_measure_output(
            cfgs=cfg_bypass_list,
            f_vco=75e6,
            n_averages=10,
            span=21e6,
            spectrum_averages=10,
            supply=supply,
            common_band=(1e2, 100e6),
        )

        '''
        # Sweep different division factors
        cfg_div_list = []
        for div in (0b100, 0b101, 0b110, 0b111):
            cfg = cfg_fast.copy()
            cfg.update(set_div_freq=div)
            cfg_div_list.append(cfg)

        sweep_grid_measure_output(
            cfgs=cfg_div_list,
            f_vco=4.8e9,
            n_averages=10,
            span=41e6,
            spectrum_averages=10,
            supply=supply,
            common_band=(1e2, 100e6),
        )
        '''
        '''
        # Sweep the different filter parameters for the 'fast' configuration

        # Current sweep
        sweep_grid_measure_output(
            cfgs=[cfg_fast],
            f_vco=4.8e9,
            sweep_curr=[0b001, 0b011, 0b111],
            sweep_c1=[0b000],
            sweep_c2=[0b000],
            sweep_r1=[0b111],
            n_averages=10,
            span=41e6,
            spectrum_averages=10,
            supply=supply,
            common_band=(1e2, 100e6),
        )

        # Sweep R1
        sweep_grid_measure_output(
            cfgs=[cfg_fast],
            f_vco=4.8e9,
            sweep_curr=[0b111],
            sweep_c1=[0b000],
            sweep_c2=[0b000],
            sweep_r1=[0b000, 0b001, 0b011, 0b111],
            n_averages=10,
            span=41e6,
            spectrum_averages=10,
            supply=supply,
            common_band=(1e2, 100e6),
        )

        # Sweep C1
        sweep_grid_measure_output(
            cfgs=[cfg_fast],
            f_vco=4.8e9,
            sweep_curr=[0b111],
            sweep_c1=[0b000, 0b001, 0b011, 0b111],
            sweep_c2=[0b000],
            sweep_r1=[0b111],
            n_averages=10,
            span=41e6,
            spectrum_averages=10,
            supply=supply,
            common_band=(1e2, 100e6),
        )

        # Sweep C2
        sweep_grid_measure_output(
            cfgs=[cfg_fast],
            f_vco=4.8e9,
            sweep_curr=[0b111],
            sweep_c1=[0b000],
            sweep_c2=[0b000, 0b001, 0b011, 0b111],
            sweep_r1=[0b111],
            n_averages=10,
            span=41e6,
            spectrum_averages=10,
            supply=supply,
            common_band=(1e2, 100e6),
        )

        '''

        '''
        # Observation of different phase noise profiles for different VCO configurations

        sweep_grid_averaged_trace(
            cfgs=[cfg0, cfg1, cfg2],
            center_freq=37.5e6,
            span=21e6,
            n_averages=10,
            supply=supply,
        )

        for cfg in (cfg0, cfg1, cfg2):
            cfg.update(
                set_div_freq=0b101
            )

        sweep_grid_averaged_trace(
            cfgs=[cfg0, cfg1, cfg2],
            center_freq=75e6,
            span=21e6,
            n_averages=10,
            supply=supply,
        )
        '''

    finally:
        # Also on an error (a VISA error stops the sweeps): reference output off, FPGA ports closed, PLL supply
        # off. The analyzer is closed by the sweep functions themselves.
        fg.close()
        if "pll" in globals():
            pll.close()
        supply.close()

    sys.exit(0)

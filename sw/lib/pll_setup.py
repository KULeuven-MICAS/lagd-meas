# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Willem Vandesteene

# Connect to the PLL controller and load a configuration with a silicon readback check; the PLL reference clock
# (start_reference) and the PLL supply with its current measurement (pll_supply, measure_pll_supply).
# Shared by sw/tests/pll_test.py and the VCO measurement code (sw/lib/vco_measure.py, sw/lib/vco_lut.py).

import contextlib
import logging

from sw.lib.pll_driver import PllDriver
from sw.lib.pll_command_api import OP_WRITEBACK, STRB_HZ, calculate_div_factor, header, pack_pll_cfg

logger = logging.getLogger(__name__)

# Device files for the PLL write/read ports (8-bit Xillybus stream).
WRITE_DEV = "/dev/xillybus_write_8"
READ_DEV = "/dev/xillybus_read_8"


def connect(write_dev=WRITE_DEV, read_dev=READ_DEV):
    """Open the PLL ports and check the controller answers a WRITEBACK; returns the PllDriver."""
    pll = PllDriver(write_dev, read_dev)
    pll.open()
    expected = header(OP_WRITEBACK)  # 0xFF
    received = pll.writeback()
    if received != expected:
        raise RuntimeError("PLL controller did not answer the writeback (sent 0x%02X, received %s)"
                           % (expected, "None" if received is None else "0x%02X" % received))
    logger.info("PASS: writeback echoed 0x%02X. The PLL controller is alive.", received)
    return pll


def load_config(pll, cfg):
    """Put the PLL registers in a known state and load `cfg` (field dict), on the reference clock.

    Sets the default strobe rate, resets the registers, selects the reference as the SoC clock, loads
    the config with the FPGA echo check and reads it back out of the silicon. Returns the config word.
    """
    pll.set_strb_hz(STRB_HZ)
    pll.reset()
    pll.select_reference()
    word = pack_pll_cfg(**cfg)
    if pll.verify_load(word) == word:
        logger.info("config check OK: 0x%012X", word)
        logger.info("Division factor on chip clock: %d, total: %d", *calculate_div_factor(cfg))
    else:
        logger.error("config check FAILED: 0x%012X", word)
    # READBACK the chip's shallow register out of the PLL's data_o (recirculating, so non-destructive).
    readback = pll.readback()
    logger.info("readback = 0x%012X", readback)
    assert readback == word
    return word


def open_pll(cfg):
    """Connect to the PLL controller and load `cfg` (connect + load_config); returns the PllDriver.
    pll.close() closes the FPGA ports only; the config stays on the chip."""
    pll = connect()
    load_config(pll, cfg)
    return pll


def open_reference_generator():
    """The Keysight 33600A of meas_setup.yaml (`function_generator`), reset: all outputs off. Needs the lab network
    (iclab_session)."""
    import yaml  # instrument imports only when a reference is needed
    from pathlib import Path
    from sw.lib.lab_instruments import instrument as inst
    from sw.lib.lab_instruments.drivers.keysight_fg_33600 import KeysightFG33600

    cfg_path = Path(__file__).resolve().parent / "lab_instruments" / "config" / "meas_setup.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return KeysightFG33600(inst.BaseInstrumentData.from_mapping(config["function_generator"]))


def start_reference(freq, vpp=1.8, channel=1, load=50, duty=50.0, fg=None):
    """Reference clock for the PLL from the Keysight 33600A (meas_setup.yaml `function_generator`): a 0 -> `vpp`
    square wave at `freq` [Hz], `duty` [%], amplitude programmed for a `load` [Ohm] termination. Output on.

    `fg`: an already open generator (open_reference_generator); None opens one.
    Returns the generator: keep it open while the PLL runs, close() turns the output off. Needs the lab
    network (iclab_session).
    """
    fg = fg or open_reference_generator()
    fg.set_load(channel, load)
    fg.set_square(channel, freq, vpp, offset=vpp / 2, duty=duty)
    fg.output_on(channel)
    logger.info("Reference on FG ch%d: %.4f MHz square, 0 -> %.2f V (%.3f Vpp, offset %.3f V), %.0f %% duty, "
                "%s Ohm load", channel, fg.get_frequency(channel) / 1e6, vpp, fg.get_amplitude(channel),
                fg.get_offset(channel), duty, load)
    return fg


# Columns added to a result CSV by measure_pll_supply.
SUPPLY_COLUMNS = ("pll_vdd", "pll_i", "pll_p")


def open_pll_smu():
    """The 2450 SMU supplying the PLL (meas_setup.yaml `smu_vdd_pll`), reset: 0 V, output off. Needs the lab
    network (iclab_session)."""
    import yaml  # instrument imports only when the supply is used
    from pathlib import Path
    from sw.lib.lab_instruments import instrument as inst
    from sw.lib.lab_instruments.drivers.keithley_smu_2450 import KeithleySMU2450

    cfg_path = Path(__file__).resolve().parent / "lab_instruments" / "config" / "meas_setup.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return KeithleySMU2450(inst.BaseInstrumentData.from_mapping(config["smu_vdd_pll"]))


def start_pll_supply(vdd=0.75, settle=0.5, smu=None):
    """PLL supply from the 2450 SMU (meas_setup.yaml `smu_vdd_pll`): output on at `vdd` [V]. Start it before
    the PLL is configured (an unpowered PLL loses its config).

    `smu`: an already open SMU (open_pll_smu), e.g. to change the voltage of a running supply; None opens one.
    Returns the SMU: keep it open while the PLL runs, close() goes back to 0 V and turns the output off. Prefer
    `with pll_supply():`, which also turns it off on an error. Needs the lab network (iclab_session).
    """
    import time

    opened_here = smu is None
    smu = smu or open_pll_smu()
    try:
        smu.set_voltage(vdd)
        smu.output_on()
        smu.wait_settled(vdd)
        time.sleep(settle)
    except BaseException:
        if opened_here:
            smu.close()  # back to 0 V, output off; a passed-in SMU is closed by its owner
        raise
    logger.info("PLL supply on: %.3f V from %s", vdd, smu.info.name)
    return smu


@contextlib.contextmanager
def pll_supply(vdd=0.75, settle=0.5):
    """`with pll_supply() as supply:` PLL supply on (start_pll_supply) for the block, off afterwards, also on an
    error."""
    smu = start_pll_supply(vdd, settle)
    try:
        yield smu
    finally:
        smu.close()  # back to 0 V, output off, connection closed
        logger.info("PLL supply off")


def measure_pll_supply(supply, n=10, label=""):
    """PLL supply voltage, current and power (mean of `n` readings) as {pll_vdd [V], pll_i [A], pll_p [W]};
    all NaN when `supply` is None (no supply SMU used). Logs one line, prefixed with `label`."""
    if supply is None:
        return dict.fromkeys(SUPPLY_COLUMNS, float("nan"))
    v, i, _ = supply.measure_stats(n)
    logger.info("%sPLL supply %.4f V, %.4f mA, %.4f mW%s", label + ": " if label else "", v, i * 1e3, v * i * 1e3,
                " (IN COMPLIANCE: current limited)" if supply.in_compliance() else "")
    return dict(pll_vdd=v, pll_i=i, pll_p=v * i)

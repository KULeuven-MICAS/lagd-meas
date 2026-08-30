# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

"""Configure the lab B2901BL SMU over LAN.

Use SMU 1's YAML default (50 uA with a 0.75 V voltage compliance) and leave
the output on after the script exits::

    python3 -m sw.tests.smu_control --smu smu_1 --on

Explicitly turn the same output off and leave it off::

    python3 -m sw.tests.smu_control --smu smu_1 --off

Override the default with -1 uA.  The ``=`` form avoids argparse treating a
negative scientific-notation value as an option::

    python3 -m sw.tests.smu_control --smu smu_1 --setpoint=-1e-6 --enable

The default and ``--off`` leave output off.  ``--on`` (and the legacy
``--enable`` alias) persist the enabled output after the script exits.
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

from sw.tests.smu_calibrate import calibrate_smu
from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keysight_smu_b2900 import KeysightSMUB2900


PRJ_ROOT = Path(__file__).resolve().parent.parent
INSTR_CFG_PATH = PRJ_ROOT / "lib" / "lab_instruments" / "config" / "meas_setup.yaml"


def parse_args():
    """Parse an SMU selection and optional overrides of its YAML defaults."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smu", default="smu_1",
        help="YAML SMU key to use (smu_1, smu_2, or smu_3; default: smu_1).")
    parser.add_argument(
        "--mode", choices=("current", "voltage"),
        help="Override the YAML source mode; --compliance limits the other quantity.")
    parser.add_argument(
        "--setpoint", type=float,
        help="Override source value, in A for current mode or V for voltage mode.")
    parser.add_argument(
        "--compliance", type=float,
        help="Override positive voltage limit (V) or current limit (A).")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--on", "--enable", dest="output", action="store_const", const="on",
        help="Enable output and leave it on after this program exits.")
    output_group.add_argument(
        "--off", dest="output", action="store_const", const="off",
        help="Disable output and leave it off after this program exits (the default).")
    parser.set_defaults(output="off")
    parser.add_argument("--verbose", action="store_true", help="Log each SCPI command.")
    return parser.parse_args()

def main():
    """Configure the SMU, optionally sample it, and safely turn it off."""
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    with INSTR_CFG_PATH.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    source_measure_units = config["source_measure_units"]
    leave_output_on = False
    try:
        smu_config = source_measure_units[args.smu]
    except KeyError:
        raise ValueError(
            f"Unknown SMU '{args.smu}'; choose one of: "
            f"{', '.join(sorted(source_measure_units))}")

    mode = args.mode or smu_config["mode"]
    if mode == "current":
        setpoint = args.setpoint if args.setpoint is not None else smu_config["current"]
        compliance = (
            args.compliance if args.compliance is not None else smu_config["voltage_limit"])
    elif args.setpoint is None or args.compliance is None:
        raise ValueError("Voltage mode requires both --setpoint and --compliance")
    else:
        setpoint = args.setpoint
        compliance = args.compliance

    smu = KeysightSMUB2900(
        inst.BaseInstrumentData(name=smu_config["name"], IP=smu_config["IP"]),
        verbose=args.verbose,
    )
    try:
        logging.info("Connected to %s", smu.status())
        if mode == "current":
            smu.set_current_source(setpoint, compliance)
        else:
            smu.set_voltage_source(setpoint, compliance)

        if args.output == "on":
            smu.enable_output()
            leave_output_on = True
            voltage_v, current_a = smu.measure()
            logging.info("Measured %.12g V, %.12g A", voltage_v, current_a)
            calibrate_smu(smu, 0.05, 0.1, 0.01, 0.75, "j")
        else:
            logging.info("Configured with output OFF (pass --on to source persistently).")
    finally:
        smu.close(disable_output=not leave_output_on)


if __name__ == "__main__":
    main()

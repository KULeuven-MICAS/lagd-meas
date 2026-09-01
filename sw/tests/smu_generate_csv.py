# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

import yaml
import csv

from sw.tests.smu_setup import setup_smu
from sw.tests.smu_calibrate import calibrate_smu
from openising import TOP_MEAS

CONFIG_FILE = TOP_MEAS / "sw/lib/lab_instruments/config/meas_setup.yaml"


def generate_calibration_files(chip: int, core: int, calibrateH: bool = False):

    with CONFIG_FILE.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
        config = config["source_measure_units"]

    instruments = dict()
    for smu in config.keys():
        # Turn on all smu's
        instruments[smu] = setup_smu(smu, True, "current", CONFIG_FILE)
        print(instruments[smu].measure())

    calibration_smu = ["smu_2", "smu_3", "smu_4"]
    if calibrateH:
        scalingFactors = list(range(1, 32))
    else:
        scalingFactors = [1]

    currents = {"base": config["smu_1"]["current"]}
    for smu in calibration_smu:
        mode = config[smu].get("calibration_mode")
        if mode == "j":
            # include the smu name in the key to avoid collisions between SMUs
            currents[mode] = calibrate_smu(
                instruments[smu],
                "j",
                config[smu]["min_current"],
                config[smu]["max_current"],
                (config[smu]["max_current"] - config[smu]["min_current"]) / 10,
                config[smu]["voltage_limit"],
                core=core,
            )
        else:
            for factor in scalingFactors:
                key = f"{mode}_sf{factor}"
                currents[key] = calibrate_smu(
                    instruments[smu],
                    mode,
                    config[smu]["min_current"],
                    config[smu]["max_current"],
                    (config[smu]["max_current"] - config[smu]["min_current"]) / 10,
                    config[smu]["voltage_limit"],
                    scalingFactor=factor,
                    core=core,
                )
    for instrument in instruments.values():
        instrument.disable_output()
    fieldnames = list(currents.keys())
    csv_file = TOP_MEAS / f"openising/calibration_currents/currents_chip{chip}_core{core}.csv"
    # use newline='' and explicit encoding for consistent CSV output across platforms
    if csv_file.exists():
        with csv_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(currents)
    else:
        with csv_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(currents)

if __name__ == "__main__":
    generate_calibration_files(2, 1)

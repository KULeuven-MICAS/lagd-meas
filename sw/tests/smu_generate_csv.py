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


def get_calibration_field_order(calibrateH: bool = False):
    fieldnames = ["base", "j"]
    scaling_factors = list(range(1, 32)) if calibrateH else [1]
    for factor in scaling_factors:
        fieldnames.extend([f"hup_sf{factor}", f"hdn_sf{factor}"])
    return fieldnames


def load_calibration_values(csv_path, fieldnames):
    values = {field: "" for field in fieldnames}
    if not csv_path.exists():
        return values

    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return values

        last_row = None
        for row in reader:
            if row:
                last_row = row

    if last_row is None:
        return values

    for field in fieldnames:
        if field in last_row and last_row[field] not in (None, ""):
            values[field] = last_row[field]
    return values


def write_calibration_values(csv_path, fieldnames, values):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not csv_path.exists()
    with csv_path.open("a" if not needs_header else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if needs_header:
            writer.writeheader()
        writer.writerow({field: values.get(field, "") for field in fieldnames})


def generate_calibration_files(chip: int, core: int, calibrateH: bool = False):

    with CONFIG_FILE.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
        config = config["source_measure_units"]

    fieldnames = get_calibration_field_order(calibrateH)
    csv_file = TOP_MEAS / f"openising/calibration_currents/currents_chip{chip}_core{core}.csv"
    currents = load_calibration_values(csv_file, fieldnames)
    if not currents.get("base"):
        currents["base"] = config["smu_1"]["current"]
        write_calibration_values(csv_file, fieldnames, currents)

    instruments = dict()
    for smu in config.keys():
        # Turn on all smu's
        instruments[smu] = setup_smu(smu, True, "current", CONFIG_FILE)
        print(instruments[smu].measure())

    calibration_smu = ["smu_2", "smu_3", "smu_4"]
    scaling_factors = list(range(1, 32)) if calibrateH else [1]
    for smu in calibration_smu:
        mode = config[smu].get("calibration_mode")
        if mode == "j":
            if currents.get("j", "") in (None, ""):
                currents["j"] = calibrate_smu(
                    instruments[smu],
                    "j",
                    config[smu]["min_current"],
                    config[smu]["max_current"],
                    (config[smu]["max_current"] - config[smu]["min_current"]) / 10,
                    config[smu]["voltage_limit"],
                    core=core,
                )
                write_calibration_values(csv_file, fieldnames, currents)
        else:
            for factor in scaling_factors:
                key = f"{mode}_sf{factor}"
                if currents.get(key, "") in (None, ""):
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
                    write_calibration_values(csv_file, fieldnames, currents)

    for instrument in instruments.values():
        instrument.disable_output()

if __name__ == "__main__":
    generate_calibration_files(chip=2, core=1, calibrateH=True)

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import yaml
import time
from pathlib import Path

from sw.lib.lab_instruments import instrument as inst
from sw.lib.lab_instruments.drivers.keysight_pa_n6700 import KeysightPAN6700
from sw.lib.os_utils.iclab_session import iclab_session
from sw.lib.os_utils.parser import Parser

PRJ_ROOT = Path(__file__).resolve().parent.parent
INSTR_CFG_PATH = PRJ_ROOT/"lib"/"lab_instruments"/"config"/"meas_setup.yaml"

def main():

    parser = Parser()
    # Load the instrument configuration from a YAML file.
    print(f"Loading instrument config from: {INSTR_CFG_PATH}")

    with INSTR_CFG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with iclab_session(parser.get_credentials()):
        # Create an instance of the KeysightPAN6700 class with the loaded configuration.
        smu = KeysightPAN6700(inst.BasePowerSupplyData.from_mapping(config["power_analyzer_chip"]), verbose=True)
        # Example usage: Set voltage and current limit for channel 2.
        smu.set_voltage("CH2", 0.75)
        smu.set_current_limit("CH2", 1.0)
        smu.turn_on_channels("CH2")  # Turn on channel 2

        # Get the voltage for channel 2.
        voltage = smu.get_voltage("CH2")
        print(f"Voltage on CH2: {voltage} V")

        smu.set_current_meter("CH2", auto_curr_range = 1,
            sample_int = 5.12e-06, sample_points = 524288)  # Set current meter for channel 2
        # Repeat some times to validate consistency of the measurement.
        for i in range(5):
            current = smu.measure_current("CH2")  # Measure current on channel 2
            print(f"{i}: Current on CH2: {current} A")
            time.sleep(1)  # Wait for 1 second before the next measurement
        print(f"Current on CH2: {current} A")

        # Close the instrument connection.
        smu.close()

if __name__ == "__main__":
    main()

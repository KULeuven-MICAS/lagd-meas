# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import yaml
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
        smu = KeysightPAN6700(inst.BasePowerSupplyData.from_mapping(config["power_analyzer_chip"]))

        smu.set_verbose(True)
        # Example usage: Set voltage and current limit for channel 2.
        smu.set_voltage("CH2", 0.75)
        smu.set_current_limit("CH2", 1.0)
        smu.turn_on_channels("CH2")  # Turn on channel 2

        # Report the maximum settings of the instrument.
        _ = input("Press Enter to continue...")
        smu.report_max_settings()

        # Get the voltage for channel 2.
        voltage = smu.get_voltage("CH2")
        print(f"Voltage on CH2: {voltage} V")

        # Close the instrument connection.
        smu.close()

if __name__ == "__main__":
    main()

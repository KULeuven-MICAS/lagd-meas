# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import yaml
import sys
from pathlib import Path

# This is quite bad! To fix this would require a lot of refactoring and directory structure changes
# I highly suggest to look into this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.lab_instruments.drivers.keysight_psu_e36300 import KeysightPSUE36300
from lib.os_utils.iclab_session import iclab_session
from lib.os_utils.crypto_utils import get_credentials_from_keyfile
from lib.os_utils.parser import Parser

PRJ_ROOT = Path(__file__).resolve().parent.parent.parent
INSTR_CFG_PATH = PRJ_ROOT/"sw"/"lib"/"lab_instruments"/"config"/"instruments.yaml"

def main():

    parser = Parser()
    # Load the instrument configuration from a YAML file.
    print(f"Loading instrument config from: {INSTR_CFG_PATH}")

    with INSTR_CFG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    credentials = None
    # Load credentials from the keyfile
    while credentials is None:
        try:
            credentials = get_credentials_from_keyfile(parser.args.keyfile)
        except FileNotFoundError:
            print("Credentials key file not found. Please run keygen.py to create it.")
            return
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return

    with iclab_session(credentials):
        # Create an instance of the KeysightPSUE36300 class with the loaded configuration.
        psu = KeysightPSUE36300(config[0])

        # Example usage: Set voltage and current limit for channel 3.
        psu.set_voltage("CH3", 0.75)
        psu.set_current_limit("CH3", 1.0)
        psu.turn_channel_on("CH3")  # Turn on channel 3

        # Get the voltage for channel 3.
        voltage = psu.get_voltage("CH3")
        print(f"Voltage on CH3: {voltage} V")

        # Close the instrument connection.
        psu.close()


if __name__ == "__main__":
    main()

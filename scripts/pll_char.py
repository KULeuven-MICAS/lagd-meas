# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import logging
import sys

from sw.lib.utils.parser import Parser
from sw.lib.lab_instruments import instrument
from sw.lib.lab_instruments.drivers.keysight_psu_e36300 import KeysightPSUE36300
from sw.lib.os_utils.iclab_session import iclab_session

def power_off()

def main():
    parser = Parser()

    logging.basicConfig(
        level=parser.get_logging_level(),
        format=parser.get_logging_format(),
        stream=sys.stdout)
    # TODO: Add file logging as:
    # https://chatgpt.com/share/6a68a9b0-2e74-83eb-850f-8a1e5c6bad34

    with parser.config_file.open(encoding="utf-8") as f:
        configs = parser.yaml.safe_load(f)

    with iclab_session(parser.get_credentials()):
        try:
            psu = KeysightPSUE36300(
                instrument.BasePowerSupplyData.from_mapping(configs["power_supply_pcb"]),
                verbose=parser.get_verbose())
            # Settings should be specified in the YAML config file
            psu.set_channels(["CH1", "CH2", "CH3"])

            # Order is important
            psu.turn_on_channels(["CH1", "CH2", "CH3"], delay=0.5)

        except Exception as e:
            logging.error(f"Error occurred: {e}")

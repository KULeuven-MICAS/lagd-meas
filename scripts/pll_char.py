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

import scripts.common.load_configs as load_configs

from sw.lib.pll_driver import PllDriver


parser = Parser()
ZEDB_CFGS = load_configs.load_zedb_lagd_configs()
CFGS = load_configs.load_configs(parser.config_file)  # DEBT - function doesn't exist

def main():

    logging.basicConfig(
        level=parser.get_logging_level(),  # DEBT - function doesn't exist
        format=parser.get_logging_format(),  # DEBT - function doesn't exist
        stream=sys.stdout)
    # TODO: Add file logging as:
    # https://chatgpt.com/share/6a68a9b0-2e74-83eb-850f-8a1e5c6bad34

    with parser.config_file.open(encoding="utf-8") as f:
        configs = parser.yaml.safe_load(f)

    with iclab_session(parser.get_credentials()):
        try:
            psu = KeysightPSUE36300(
                instrument.BasePowerSupplyData.from_mapping(configs["power_supply_pcb"]),
                verbose=parser.get_verbose())  # DEBT - function doesn't exist
            # Settings should be specified in the YAML config file
            psu.set_channels(["CH1", "CH2", "CH3"]) # DEBT - function doesn't exist

            pll = PllDriver(ZEDB_CFGS["WRITE_DEV"], ZEDB_CFGS["READ_DEV"])

            psu.turn_on_channels(["CH1", "CH2", "CH3"], delay=0.5)
            # Operations
            if parser.interactive:
                logging.info("Interactive mode: waiting for user input to proceed...")
                # TODO: the idea is that people can provide different configurations and test/measure/...
            else:
                logging.info("Non-interactive mode: proceeding with operations...")
                pll.reset()  # Reset the PLL to default configuration
                pll.load_readback(CFGS["pll_config"])  # Load the PLL configuration


            # Order is important
            psu.turn_off()  # DEBT - function doesn't exist
        except Exception as e:
            # Ensure all secutity actions are taken in case of an error

            psu.turn_off()  # Ensure PSU is turned off in case of error
            logging.error(f"Error occurred: {e}")

# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

import logging
import sys

from sw.lib.utils.parser import Parser
from sw.lib.lab_instruments import instrument
from sw.lib.lab_instruments.drivers.keysight_psu_e36300 import KeysightPSUE36300
from sw.lib.utils.iclab_session import iclab_session
from sw.lib.perip_driver import PeripDriver

import scripts.common.load_configs as load_configs
from scripts.utils.pll_char_menu import PllCharMenu

from sw.lib.pll_driver import PllDriver


parser = Parser()
ZEDB_CFGS = load_configs.load_zedb_lagd_configs()
CFGS = load_configs.load_configs(parser.config_file)

def main():

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
            # Connecting to the instrument
            psu = KeysightPSUE36300(
                instrument.BasePowerSupplyData.from_mapping(configs["power_supply_pcb"]),
                verbose=parser.get_verbose())

            pll = PllDriver(ZEDB_CFGS["WRITE_DEV"], ZEDB_CFGS["READ_DEV"])
            pcb_driver = PeripDriver(ZEDB_CFGS["WRITE_DEV"], ZEDB_CFGS["READ_DEV"])

            # Automatically set all channels based on the instrument info in YML cofig file.
            # This is equivalent to:
            #    psu.set_channels(["CH1", "CH2", "CH3"])
            psu.autoset()

            # Turn on the channels with a delay of 0.5 seconds between each channel.
            # Order matters! This is equivalent to:
            #    psu.turn_on(delay=0.5) if priority is set in the YML config file.
            psu.turn_on_channels(["CH1", "CH2", "CH3"], delay=0.5)

            # Operations
            if parser.interactive:
                menu = PllCharMenu(
                    pll_driver=pll,
                    pcb_driver=pcb_driver,
                    psu_driver=psu,
                    initial_vref=configs["pll_igen_vref"],
                    initial_pll_config=configs["pll_config"],
                    logger=logging.getLogger(__name__),
                    bench_config=configs
                )

                menu.run()

            else:
                logging.info("Non-interactive mode: proceeding with operations...")
                pcb_driver.set_voltage(
                    channel=configs["pll_dac_channel"],
                    vref=configs["pll_igen_vref"])
                pll.reset()  # Reset the PLL to default configuration
                pll.load_readback(CFGS["pll_config"])  # Load the PLL configuration
                _ = input("Setup complete. Press Enter to shut down...")

            psu.close()  # Close the PSU connection
        except Exception as e:
            # Ensure all secutity actions are taken in case of an error

            psu.close()  # Ensure PSU is turned off in case of error
            logging.error(f"Error occurred: {e}")

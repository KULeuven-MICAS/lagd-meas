# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

from dataclasses import dataclass
from typing import Any, Dict
import logging

import scripts.common.load_configs as load_configs
from sw.lib.utils.terminal.menu import InteractiveMenu, MenuAction
from sw.lib.utils.terminal.prompts import Prompt
import sw.lib.pll_command_api as pll_api

from sw.lib.perip_driver import PeripDriver
from sw.lib.pll_driver import PllDriver


@dataclass
class PllCharMenuState:
    """Runtime state managed by the interactive menu."""

    vref: float
    vdd: float
    pll_config: Any

# TODO storing pll_config is redundant
class PllCharMenu(InteractiveMenu):
    """Interactive menu for PLL characterization."""

    def __init__(
        self,
        pll_driver: PllDriver,
        pcb_driver: PeripDriver,
        psu_driver: Any,
        bench_config: Dict[str, Any],
        initial_vref: float = 2.5,
        initial_avdd: float = 0.75,
        initial_pll_config: Dict[str, int] = pll_api.DEFAULT_CFG,

        logger: logging.Logger | None = None,
    ) -> None:
        self.state = PllCharMenuState(
            vref=initial_vref, avdd=initial_avdd, pll_config=initial_pll_config
        )
        super().__init__(
            title="PLL Characterization Menu",
            actions=self._build_actions(),
        )

    def _build_actions(self) -> list[MenuAction]:
        """Build menu actions for the PLL characterization flow."""
        return [
            MenuAction("1",
                "Input a new vdd for pcb_driver",
                lambda: self._update_vdd(),
            ),
            MenuAction("2",
                "Input a new vref for pcb_driver",
                lambda: self._update_vref(),
            ),
            MenuAction("3",
                "Input a new configuration file",
                lambda: self._update_pll_config(),
            ),
            MenuAction("4",
                "Quit",
                lambda: logging.info("Exiting interactive menu"), exits_menu=True),
        ]
    def _update_vdd(self) -> None:
        """Prompt for and apply a new vdd value."""
        new_vdd = Prompt.ask_float("Enter new vdd value: ")
        self.state.vdd = new_vdd
        self.psu_driver.set_voltage(channel="VDD_PLL", voltage=self.state.vdd)
        logging.info("Updated vdd to %.6f", self.state.vdd)

    def _update_vref(self) -> None:
        """Prompt for and apply a new vref value."""
        new_vref = Prompt.ask_float("Enter new vref value: ")
        self.state.vref = new_vref
        self.pcb_driver.set_voltage(
            channel=self.bench_config["pcb_vref_channel"], 
            voltage=self.state.vref)
        logging.info("Updated vref to %.6f", self.state.vref)

    def _update_pll_config(self) -> None:
        """Prompt for config file and apply pll_config when valid."""
        config_path = Prompt.ask_file("Enter path to YAML config file: ")
        pll_config = self._load_pll_config(config_path)
        self.pll_driver.load_readback(pll_config)
        if pll_config is None:
            return

        self.state.pll_config = pll_config
        logging.info("Updated pll_config from '%s'", config_path)

    def _load_pll_config(self, path: str) -> Dict[str, int] | None:
        """Load PLL config from YAML file and validate it."""

        pll_config = load_configs.load_configs(path)
        # Validate the loaded pll_config against expected fields
        # TODO maybe allow defaults?
        for field in pll_api.FIELDS:
            if field.name not in pll_config:
                logging.error(
                    "Missing field '%s' in pll_config from '%s'", field.name, path
                )
                return None

        return pll_config

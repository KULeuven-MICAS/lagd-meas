# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class MenuAction:
    """One selectable menu action."""

    key: str
    label: str
    callback: Callable[[], None]
    exits_menu: bool = False


class InteractiveMenu:
    """Small reusable interactive terminal menu."""

    def __init__(
        self,
        title: str,
        actions: Sequence[MenuAction],
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> None:
        self.title = title
        self.input_func = input_func
        self.output_func = output_func
        self._actions = {action.key: action for action in actions}

        if len(self._actions) != len(actions):
            raise ValueError("Menu action keys must be unique")

    def add_action(self, action: MenuAction) -> None:
        """Add a new action to the menu."""
        if action.key in self._actions:
            raise ValueError(f"Action key '{action.key}' already exists")
        self._actions[action.key] = action

    def run(self) -> None:
        """Run the menu loop until an exit action is selected."""
        while True:
            self._render()
            choice = self.input_func("Select an option: ").strip()
            action = self._actions.get(choice)

            if action is None:
                self.output_func(f"Invalid option '{choice}'. Please try again.")
                continue

            action.callback()
            if action.exits_menu:
                return

    def _render(self) -> None:
        self.output_func("")
        self.output_func(self.title)
        for action in self._actions.values():
            self.output_func(f"{action.key}. {action.label}")

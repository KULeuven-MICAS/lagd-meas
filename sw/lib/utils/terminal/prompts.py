# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Giuseppe M. Sarda <giuseppe.sarda@esat.kuleuven.be>

from typing import Callable
from pathlib import Path

from prompt_toolkit import prompt
from prompt_toolkit.completion import PathCompleter

class Prompt:

    @staticmethod
    def _prompt_until_valid(
        input_str: str,
        validation_func: Callable[[str], bool],
        error_msg: str,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print
    ) -> str:
        """Prompt the user until a valid input is provided."""
        while True:
            value = input_func(input_str)
            try:
                if validation_func(value):
                    return value
                else:
                    raise ValueError(f"'{value}'")
            except Exception as e:
                output_func(f"{error_msg}: {e}. Please try again.")

    @staticmethod
    def ask_float(input_str: str,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print
        ) -> float:
        """Prompt the user for a float value."""
        return Prompt._prompt_until_valid(
            input_str,
            validation_func=lambda x: float(x),
            error_msg="Invalid float value",
            input_func=input_func,
            output_func=output_func
        )

    @staticmethod
    def ask_file(input_str: str,
        input_func: Callable[[str], str] = lambda s: prompt(s,
            completer=PathCompleter(only_files=True)),
        output_func: Callable[[str], None] = print
        ) -> str:
        """Prompt the user for a file path and check if it exists."""
        return Prompt._prompt_until_valid(
            input_str,
            validation_func=lambda x: Path(x).is_file(),
            error_msg="Invalid file path",
            input_func=input_func,
            output_func=output_func
        )

    @staticmethod
    def ask_integer(input_str: str,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print
        ) -> int:
        raise NotImplementedError("ask_integer is not implemented yet.")

    @staticmethod
    def ask_yes_no(input_str: str,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print
        ) -> bool:
        """Prompt the user for a yes/no answer."""
        return Prompt._prompt_until_valid(
            input_str,
            validation_func=lambda x: x.strip().lower() in ['y', 'yes', 'n', 'no'],
            error_msg="Invalid input. Please enter 'y' or 'n'.",
            input_func=input_func,
            output_func=output_func
        )

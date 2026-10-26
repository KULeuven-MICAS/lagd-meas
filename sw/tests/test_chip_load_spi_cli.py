# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Hardware-free command-line tests for chip_load_spi.py.

import contextlib
import io
import unittest
from unittest import mock

from sw.tests import chip_load_spi, chip_load_spi_repeat
from sw.tests.chip_load_spi import DEFAULT_ELF, parse_args
from sw.tools.spi_program_loader import (
    DEFAULT_EOC_INITIAL_DELAY,
    DEFAULT_EOC_TIMEOUT,
    EocTimeoutError,
)


class TestChipLoadSpiCli(unittest.TestCase):

    def test_defaults_are_fast_checks_off_and_finite_wait(self):
        args = parse_args([DEFAULT_ELF])
        self.assertFalse(args.verify)
        self.assertFalse(args.smoke_test)
        self.assertEqual(args.run_timeout, DEFAULT_EOC_TIMEOUT)
        self.assertEqual(args.eoc_initial_delay, DEFAULT_EOC_INITIAL_DELAY)

    def test_all_optional_controls(self):
        args = parse_args([
            DEFAULT_ELF,
            "--sck", "1250000",
            "--verify",
            "--smoke-test",
            "--run-timeout", "0",
            "--eoc-initial-delay", "0.5",
        ])
        self.assertEqual(args.sck, 1_250_000)
        self.assertTrue(args.verify)
        self.assertTrue(args.smoke_test)
        self.assertEqual(args.run_timeout, 0)
        self.assertEqual(args.eoc_initial_delay, 0.5)

    def test_negative_run_timeout_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args([DEFAULT_ELF, "--run-timeout", "-1"])

    def test_negative_eoc_initial_delay_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args([DEFAULT_ELF, "--eoc-initial-delay", "-1"])

    def test_repeat_cli_accepts_eoc_initial_delay(self):
        args = chip_load_spi_repeat.parse_args([
            DEFAULT_ELF,
            "--eoc-initial-delay", "0.5",
        ])
        self.assertEqual(args.eoc_initial_delay, 0.5)

    @mock.patch("sw.tests.chip_load_spi.SpiProgramLoader")
    def test_run_elf_with_chip_resets_each_program(self, loader_class):
        chip = mock.Mock()

        chip_load_spi.run_elf_with_chip(
            chip,
            DEFAULT_ELF,
            sck_hz=12_500_000,
            run_timeout=5.0,
        )

        chip.reset_chip.assert_called_once_with(hold=0.001, chip_clk_en=1)
        chip.set_sck_hz.assert_called_once_with(12_500_000)
        loader_class.assert_called_once_with(chip)
        loader_class.return_value.load_and_run.assert_called_once_with(
            DEFAULT_ELF,
            init_spi=True,
            verify=False,
            wait=True,
            eoc_timeout=5.0,
            eoc_initial_delay=DEFAULT_EOC_INITIAL_DELAY,
        )

    @mock.patch("sw.tests.chip_load_spi.SpiProgramLoader")
    @mock.patch("sw.tests.chip_load_spi.ChipDriver")
    def test_eoc_timeout_returns_nonzero_status(self, chip_driver, loader_class):
        chip_driver.return_value = mock.MagicMock()
        loader_class.return_value.load_and_run.side_effect = EocTimeoutError("timeout")

        with self.assertLogs(level="ERROR"):
            status = chip_load_spi.main(DEFAULT_ELF, 1_250_000, False, 1.0)

        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

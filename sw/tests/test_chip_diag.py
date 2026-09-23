# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Hardware-free regression checks (testbench for chip_diag.py): python3 -m unittest sw.tests.test_chip_diag

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from sw.tests import chip_diag


class FakeChip:
    def __init__(self, read_limit=25e6, write_limit=25e6):
        self.sck_hz = 2e6
        self.read_limit = read_limit
        self.write_limit = write_limit
        self.memory = []

    def set_sck_hz(self, hz):
        self.sck_hz = hz
        return hz

    def write_mem(self, addr, data):
        if self.sck_hz <= self.write_limit:
            self.memory = list(data)

    def read_mem(self, addr, length):
        if self.sck_hz > self.read_limit:
            return []  # A truncated read must fail, too.
        return self.memory[:length]


class TestSckSweep(unittest.TestCase):
    def sweep(self, chip):
        with self.assertLogs(chip_diag.logger, level="INFO"):
            return chip_diag.test_h_sck_sweep(chip, freqs=(10e6, 25e6), n=4, rounds=2)

    def test_read_failure_does_not_stop_write_sweep(self):
        chip = FakeChip(read_limit=5e6)
        result = self.sweep(chip)
        self.assertTrue(result["baseline_ok"])
        self.assertEqual(len(result["rates"]), 2)
        self.assertTrue(all(not r["read_ok"] and r["write_ok"] for r in result["rates"]))
        self.assertEqual(chip.sck_hz, 2e6)

    def test_dropped_writes_cannot_pass_from_stale_contents(self):
        # Even identical random data every round must expose an ignored write.
        with patch.object(chip_diag.random, "getrandbits", return_value=0x12345678):
            result = self.sweep(FakeChip(write_limit=5e6))
        self.assertTrue(all(r["read_ok"] and not r["write_ok"] for r in result["rates"]))

    def test_all_rates_pass(self):
        result = self.sweep(FakeChip())
        self.assertTrue(all(r["read_ok"] and r["write_ok"] for r in result["rates"]))

    def test_bad_baseline_is_inconclusive(self):
        chip = FakeChip(read_limit=1e6)
        result = self.sweep(chip)
        self.assertFalse(result["baseline_ok"])
        self.assertEqual(result["rates"], [])
        self.assertEqual(chip.sck_hz, 2e6)

    def test_exception_restores_clock(self):
        chip = FakeChip()
        with patch.object(chip, "read_mem", side_effect=OSError("link error")):
            with self.assertRaises(OSError), self.assertLogs(chip_diag.logger, level="INFO"):
                chip_diag.test_h_sck_sweep(chip, freqs=(25e6,))
        self.assertEqual(chip.sck_hz, 2e6)

    def run_main(self, sweep_result, noise=None):
        with ExitStack() as stack:
            driver = stack.enter_context(patch.object(chip_diag, "ChipDriver"))
            driver.return_value.sck_hz = 5e6
            stack.enter_context(patch.object(chip_diag.sys, "argv", ["chip_diag.py", "--sck-sweep"]))
            for name, value in {
                "release_chip_reset": None,
                "test_a_fpga_loopback": True,
                "test_b_bootrom_read": True,
                "test_c_read_stability": True,
                "test_d_burst_sweep": {1: (True, 1)},
                "test_e_single_vs_burst": (True, True),
                "test_g_switching_noise": noise or {"quiet": (96, 96)},
                "test_h_sck_sweep": sweep_result,
            }.items():
                stack.enter_context(patch.object(chip_diag, name, return_value=value))
            with self.assertLogs(chip_diag.logger, level="INFO") as logs:
                code = chip_diag.main()
            return code, "\n".join(logs.output)

    def test_sweep_failure_is_reported_separately(self):
        code, logs = self.run_main({"baseline_ok": True, "rates": [
            {"hz": 25e6, "read_ok": False, "write_ok": True}]})
        self.assertEqual(code, 0)  # Finding the ceiling is a successful diagnostic.
        self.assertIn("SWEEP VERDICT: failures observed", logs)
        self.assertIn("BASELINE VERDICT: PASS", logs)
        self.assertNotIn("every test passed", logs)

    def test_inconclusive_sweep_has_failure_exit(self):
        code, logs = self.run_main({"baseline_ok": False, "rates": []})
        self.assertEqual(code, 1)
        self.assertIn("SWEEP VERDICT: INCONCLUSIVE", logs)

    def test_noise_failure_counts_in_baseline_verdict(self):
        code, logs = self.run_main({"baseline_ok": True, "rates": []}, {"quiet": (95, 96)})
        self.assertEqual(code, 1)
        self.assertIn("BASELINE VERDICT: FAIL", logs)


if __name__ == "__main__":
    unittest.main()

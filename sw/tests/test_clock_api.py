# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Hardware-free tests for the shared clock model (sw/lib/clock_api.py).
#
# Two jobs:
#
#   1. Behaviour. The Hz <-> half-period conversion, the clamps, the bypass, and
#      the round trip. Ordinary unit tests.
#
#   2. THE MIRROR. clock_api.py hand-copies numbers that really live in the RTL
#      (xillydemo.v's parameters and the field widths in the *_command_api.sv
#      files). A hand-maintained mirror drifts silently, and the failure mode is
#      not a crash -- it is software believing the hardware is running at a rate
#      it is not. So these tests PARSE THE RTL and compare. Change a parameter in
#      xillydemo.v without updating clock_api.py and this file fails.
#
# Run with the repo root on PYTHONPATH (source env.sh):
#   python3 -m unittest sw.tests.test_clock_api
#
# Targets Python 3.6 (locked Zedboard runtime).

import re
import unittest
from pathlib import Path

from sw.lib.chip_command_api import chip_clk_half_for, sck_half_for as chip_sck_half_for
from sw.lib.clock_api import (
    ClockKnob, CHIP_CLK, CHIP_SCK, DAC_SCK, S2P_SCK, PLL_STRB, ALL_KNOBS,
    BUS_CLK_HZ, set_clock,
)
from sw.lib.perip_command_api import sck_half_for as perip_sck_half_for
from sw.lib.pll_command_api import strb_half_for

_REPO = Path(__file__).resolve().parent.parent.parent      # sw/tests -> repo root
_RTL = _REPO / "fpga" / "src" / "verilog"


def _sv_int(text, name):
    """Read `parameter integer NAME = 1_234;` (or localparam) out of RTL text."""
    m = re.search(r"(?:parameter|localparam)\s+(?:integer|int)"
                  r"(?:\s+(?:unsigned|signed))?\s+" + name +
                  r"\s*=\s*([0-9_]+)", text)
    if m is None:
        raise AssertionError(f"could not find parameter {name} in the RTL")
    return int(m.group(1).replace("_", ""))


def _sv_field_bits(text, struct_field):
    """Read the width of `bit [19:0] sck_half;`-style field declarations."""
    m = re.search(r"bit\s*\[\s*(\d+)\s*:\s*0\s*\]\s+" + struct_field + r"\s*;", text)
    if m is None:
        raise AssertionError(f"could not find field {struct_field} in the RTL")
    return int(m.group(1)) + 1


class TestKnobBehaviour(unittest.TestCase):
    """The conversion itself."""

    def test_exact_divisors_round_trip(self):
        for knob in ALL_KNOBS:
            for half in (knob.half_min, 25, 50, 1000, knob.half_max):
                if not (knob.half_min <= half <= knob.half_max):
                    continue
                hz = knob.hz_for(half)
                self.assertEqual(knob.half_for(hz)[0], half,
                                 f"{knob.name}: half {half} did not round trip")

    def test_frequency_formula(self):
        # f = bus/(2*half) -- the one equation the whole module exists to share.
        self.assertEqual(CHIP_CLK.hz_for(25), 2e6)
        self.assertEqual(CHIP_SCK.hz_for(10), 5e6)
        self.assertEqual(DAC_SCK.hz_for(50_000), 1e3)
        self.assertEqual(PLL_STRB.hz_for(50_000), 1e3)

    def test_clamps_to_hardware_window(self):
        # Requests outside the window come back clamped, NOT raised: the hardware
        # saturates, so the model must report what the hardware will really do.
        self.assertEqual(CHIP_SCK.half_for(50e6), (2, 25e6))    # fast end clamped
        self.assertEqual(DAC_SCK.half_for(1e9), (2, 25e6))
        self.assertEqual(DAC_SCK.half_for(1), (1_000_000, 50.0))  # slow end clamped
        self.assertEqual(PLL_STRB.half_for(1), (1_000_000, 50.0))

    def test_rejects_nonpositive(self):
        for knob in ALL_KNOBS:
            self.assertRaises(ValueError, knob.half_for, 0)
            self.assertRaises(ValueError, knob.half_for, -1)

    def test_only_chip_clk_has_a_bypass(self):
        # The bypass is what reaches the full bus clock; a toggle divider cannot.
        self.assertEqual(CHIP_CLK.half_for(100e6), (0, 100e6))
        self.assertEqual(CHIP_CLK.hz_for(0), 100e6)
        for knob in (CHIP_SCK, DAC_SCK, S2P_SCK, PLL_STRB):
            self.assertIsNone(knob.bypass_code, knob.name)
            self.assertLessEqual(knob.fastest_hz, BUS_CLK_HZ / 2)

    def test_bypass_gap_snaps_to_nearer_end(self):
        # Nothing between 50 and 100 MHz is reachable; the split is the log-domain
        # midpoint (~70.7 MHz), not the arithmetic one.
        self.assertEqual(CHIP_CLK.half_for(80e6)[1], 100e6)
        self.assertEqual(CHIP_CLK.half_for(60e6)[1], 50e6)

    def test_check_half_bounds_the_payload(self):
        # Encodable range, i.e. what fits the command field (wider than the clamp).
        self.assertRaises(ValueError, CHIP_SCK.check_half, 0)         # would hang
        self.assertRaises(ValueError, CHIP_SCK.check_half, 1 << 20)   # overflows
        self.assertEqual(CHIP_CLK.check_half(0), 0)                   # bypass is legal
        self.assertRaises(ValueError, PLL_STRB.check_half, 1 << 24)

    def test_is_clamped_flags_unreachable_requests(self):
        self.assertTrue(CHIP_SCK.is_clamped(50e6, 25e6))
        self.assertFalse(CHIP_SCK.is_clamped(5e6, 5e6))

    def test_set_clock_emits_the_code_and_returns_the_actual(self):
        sent = []
        actual = set_clock(CHIP_CLK, 2e6, sent.append)
        self.assertEqual(sent, [25])
        self.assertEqual(actual, 2e6)

    def test_empty_range_is_rejected_at_construction(self):
        self.assertRaises(ValueError, ClockKnob, "bad", field_bits=20,
                          default_hz=1e3, min_hz=int(1e9), max_hz=1)


class TestMirrorsTheRtl(unittest.TestCase):
    """clock_api.py's numbers must equal the RTL's. Parse and compare."""

    @classmethod
    def setUpClass(cls):
        cls.xilly = (_RTL.parent / "verilog" / "xillydemo.v").read_text()
        cls.chip_api = (_RTL / "chip_command_api.sv").read_text()
        cls.perip_api = (_RTL / "perip_command_api.sv").read_text()
        cls.pll_api = (_RTL / "pll_command_api.sv").read_text()

    def test_bus_clock(self):
        self.assertEqual(BUS_CLK_HZ, _sv_int(self.xilly, "CLK_HZ"))

    def test_chip_sck_bounds(self):
        self.assertEqual(CHIP_SCK.default_hz, _sv_int(self.xilly, "CHIP_SCK_HZ"))
        self.assertEqual(CHIP_SCK.max_hz, _sv_int(self.xilly, "CHIP_SCK_MAX_HZ"))

    def test_perip_bounds(self):
        default = _sv_int(self.xilly, "PERIP_SCK_HZ")
        hi = _sv_int(self.xilly, "PERIP_SCK_MAX_HZ")
        lo = _sv_int(self.xilly, "PERIP_SCK_MIN_HZ")
        for knob in (DAC_SCK, S2P_SCK):   # both are driven by the same parameters
            self.assertEqual(knob.default_hz, default, knob.name)
            self.assertEqual(knob.max_hz, hi, knob.name)
            self.assertEqual(knob.min_hz, lo, knob.name)

    def test_pll_strb_bounds(self):
        self.assertEqual(PLL_STRB.default_hz, _sv_int(self.xilly, "PLL_STRB_HZ"))
        self.assertEqual(PLL_STRB.max_hz, _sv_int(self.xilly, "PLL_STRB_MAX_HZ"))
        self.assertEqual(PLL_STRB.min_hz, _sv_int(self.xilly, "PLL_STRB_MIN_HZ"))

    def test_chip_clk_defaults_to_the_bus_clock(self):
        # chip_controller.sv resets chip_clk_half_r to 0 = bypass = full bus clock.
        self.assertEqual(CHIP_CLK.default_hz, BUS_CLK_HZ)
        self.assertEqual(CHIP_CLK.bypass_code, 0)
        rtl = (_RTL / "chip_controller.sv").read_text()
        self.assertIn("chip_clk_half_r <= '0", rtl,
                      "chip_controller no longer resets the chip clock to bypass")

    def test_command_field_widths(self):
        self.assertEqual(CHIP_SCK.field_bits, _sv_field_bits(self.chip_api, "sck_half"))
        self.assertEqual(CHIP_CLK.field_bits, _sv_field_bits(self.chip_api, "clk_half"))
        self.assertEqual(DAC_SCK.field_bits, _sv_field_bits(self.perip_api, "sck_half"))
        self.assertEqual(S2P_SCK.field_bits, _sv_field_bits(self.perip_api, "sck_half"))
        strb_bytes = _sv_int(self.pll_api, "PLL_STRB_BYTES")
        self.assertEqual(PLL_STRB.field_bits, 8 * strb_bytes)

    def test_clamp_bounds_fit_their_command_field(self):
        # A clamp bound the payload cannot express would be silently truncated.
        for knob in ALL_KNOBS:
            self.assertLessEqual(knob.half_max, (1 << knob.field_bits) - 1, knob.name)
            self.assertGreaterEqual(knob.half_min, 1, knob.name)

    def test_bound_formula_matches_the_shared_rtl_function(self):
        # clock_div_api.sv derives the same bounds; the double integer division is
        # load-bearing, so check the formula text itself rather than trusting it.
        rtl = (_RTL / "clock_div_api.sv").read_text()
        self.assertIn("clk_hz / max_hz / 2", rtl)
        self.assertIn("clk_hz / min_hz / 2", rtl)
        for knob in ALL_KNOBS:
            if knob.max_hz is not None:
                expect = max(1, BUS_CLK_HZ // knob.max_hz // 2)
                self.assertEqual(knob.half_min, expect, knob.name)
            if knob.min_hz is not None:
                self.assertEqual(knob.half_max,
                                 min(BUS_CLK_HZ // knob.min_hz // 2,
                                     (1 << knob.field_bits) - 1), knob.name)

    def test_all_three_controllers_use_the_shared_clamp(self):
        # The point of clock_div_api.sv: one copy of the saturation, not three.
        for name in ("quad_spi_master.sv", "perip_controller.sv", "pll_controller.sv"):
            self.assertIn("clk_half_clamp", (_RTL / name).read_text(), name)


class TestLegacyHelpersStillAgree(unittest.TestCase):
    """The per-module helper names are kept as wrappers; they must not diverge
    from the knob they now delegate to."""

    def test_chip_helpers(self):
        for hz in (1e3, 1e6, 5e6, 25e6):
            self.assertEqual(chip_sck_half_for(hz), CHIP_SCK.half_for(hz))
            self.assertEqual(chip_clk_half_for(hz), CHIP_CLK.half_for(hz))

    def test_perip_helper(self):
        for hz in (50, 1e3, 1e6):
            self.assertEqual(perip_sck_half_for(hz), DAC_SCK.half_for(hz))

    def test_pll_helper(self):
        for hz in (50, 1e3, 1e6):
            self.assertEqual(strb_half_for(hz), PLL_STRB.half_for(hz))

    def test_a_foreign_bus_clock_is_refused(self):
        # These used to take a bus_clk_hz override that silently produced codes
        # for a bitstream that does not exist.
        self.assertRaises(ValueError, chip_sck_half_for, 1e6, 50_000_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)

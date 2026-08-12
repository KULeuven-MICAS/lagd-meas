# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# One model for every runtime-configurable clock on the board.
#
# f = BUS_CLK_HZ / (2 * half)
#
# The ceilings differ per clock, on purpose. They are physical, not stylistic:
#
#   * The four serial clocks come from toggle dividers, so half=1 gives
#     BUS_CLK_HZ/2 = 50 MHz and nothing faster exists. Even that is unusable for
#     a data clock -- SCK would toggle every bus clock, leaving the data no setup
#     against its own edge (see chip_diag.py's SCK sweep).
#   * The 25 MHz clamp is deliberately tied to what the XDC timing-constrained,
#     so software can never select a rate the bitstream was not signed off for.
#   * The DAC path additionally owes a 40 ns CSB hold (datasheet), and the
#     measured chip-SCK ceiling is ~8-17 MHz from cable + IO round trip on the
#     read turnaround.
#
# Only clk_chip_o legitimately reaches the full 100 MHz, because it is a CLOCK TO
# A CHIP rather than a data clock -- and it gets there through a bypass code
# (half == 0) rather than the counter, since a toggle divider has no divide-by-1.
#
# STAYING IN SYNC WITH THE RTL
# ----------------------------
# The bounds below mirror the parameters in fpga/src/verilog/xillydemo.v and the
# clamps in quad_spi_master.sv / perip_controller.sv / pll_controller.sv. That
# mirror is checked automatically by sw/tests/test_clock_api.py, which parses the
# RTL -- so a divergence fails a test instead of silently mis-driving hardware.

import math

# The bus clock feeding every controller (xillydemo.v: CLK_HZ).
BUS_CLK_HZ = 100_000_000


def _fmt_hz(hz):
    """Render a rate in whichever unit keeps it readable (these span 47 Hz..100 MHz)."""
    if hz >= 1e6:
        return "{:.6g} MHz".format(hz / 1e6)
    if hz >= 1e3:
        return "{:.6g} kHz".format(hz / 1e3)
    return "{:.6g} Hz".format(hz)


class ClockKnob(object):
    """One runtime-configurable clock: Hz <-> half-period code, plus its limits.

    `max_hz` is the fastest rate the HARDWARE CLAMP permits (None = the clamp
    only stops the divider from hanging, so the field width is the sole limit).
    `min_hz` is the slowest the clamp permits (None = field-width limited).
    `bypass_code` is the half value that forwards the bus clock untouched, for
    the one knob that can do it; None for the rest.
    """

    def __init__(self, name, field_bits, default_hz, min_hz=None, max_hz=None,
                 bypass_code=None, bus_hz=BUS_CLK_HZ, note=""):
        self.name = name
        self.bus_hz = bus_hz
        self.field_bits = field_bits
        self.default_hz = float(default_hz)
        # Kept as ints: the half-period bounds derived from them are command
        # payload codes, and a float code would be sent as a float.
        self.min_hz = None if min_hz is None else int(min_hz)
        self.max_hz = None if max_hz is None else int(max_hz)
        self.bypass_code = bypass_code
        self.note = note

        # Deliberately the same double-floor-division the RTL localparams use
        # (`CLK_HZ / SCK_MAX_HZ / 2` in SystemVerilog is integer division twice).
        # Writing it as ceil(bus/(2*max)) would be more "correct" arithmetic but
        # could land one code away from the hardware, which is worse than being
        # theoretically tidy: the clamp is what the hardware actually does.
        self.half_min = 1 if self.max_hz is None else max(1, bus_hz // self.max_hz // 2)
        field_max = (1 << field_bits) - 1
        self.half_max = field_max if self.min_hz is None else min(
            bus_hz // self.min_hz // 2, field_max)
        if self.half_max < self.half_min:
            raise ValueError("{}: empty range".format(name))

    # ---- reachable range ----
    @property
    def fastest_hz(self):
        """Highest rate this knob can produce, bypass included."""
        if self.bypass_code is not None:
            return float(self.bus_hz)
        return self.bus_hz / (2.0 * self.half_min)

    @property
    def fastest_divided_hz(self):
        """Highest rate the COUNTER can produce (below `fastest_hz` when a
        bypass exists -- the gap between them is unreachable)."""
        return self.bus_hz / (2.0 * self.half_min)

    @property
    def slowest_hz(self):
        return self.bus_hz / (2.0 * self.half_max)

    # ---- conversion ----
    def half_for(self, hz):
        """Half-period code for a requested rate, and the rate actually achieved.

        Returns (half, actual_hz). The divider is integer and the request is
        clamped to what the hardware permits, so actual_hz generally differs from
        the request -- always use the returned value rather than assuming.
        """
        if hz <= 0:
            raise ValueError("{}: frequency must be positive, got {}".format(
                self.name, hz))
        # A bypass reaches bus_hz while the counter tops out at bus_hz/2, so
        # requests in that gap snap to whichever end is nearer in the log domain
        # (bus_hz/sqrt(2), i.e. ~70.7 MHz on a 100 MHz bus).
        if self.bypass_code is not None and hz >= self.bus_hz / math.sqrt(2.0):
            return self.bypass_code, float(self.bus_hz)
        half = int(round(self.bus_hz / (2.0 * hz)))
        half = max(self.half_min, min(half, self.half_max))
        return half, self.bus_hz / (2.0 * half)

    def hz_for(self, half):
        """Rate produced by a half-period code (inverse of half_for)."""
        if self.bypass_code is not None and half == self.bypass_code:
            return float(self.bus_hz)
        if half <= 0:
            raise ValueError("{}: half must be >= 1".format(self.name))
        return self.bus_hz / (2.0 * half)

    def check_half(self, half):
        """Raise ValueError if `half` cannot be encoded in the command payload."""
        lo = 0 if self.bypass_code is not None else 1
        hi = (1 << self.field_bits) - 1
        if not (lo <= half <= hi):
            raise ValueError("{}: half {} out of range {}..{}".format(
                self.name, half, lo, hi))
        return half

    def is_clamped(self, requested_hz, actual_hz, tol=0.01):
        """True when the achieved rate misses the request by more than `tol`.

        Worth surfacing to the user: an out-of-range request comes back as a
        DIFFERENT frequency rather than an error, and silently running at 47 Hz
        instead of the 10 Hz you asked for just looks like slow hardware.
        """
        return abs(actual_hz - requested_hz) > tol * requested_hz

    def describe(self):
        """One-line human summary of what this knob can do."""
        gap = ""
        if self.bypass_code is not None:
            gap = " (nothing between {} and {})".format(
                _fmt_hz(self.fastest_divided_hz), _fmt_hz(self.fastest_hz))
        return "{}: {} .. {}, default {}{}".format(
            self.name, _fmt_hz(self.slowest_hz), _fmt_hz(self.fastest_hz),
            _fmt_hz(self.default_hz), gap)


# --- the five knobs -----------------------------------------------------------
# field_bits is the width of the command payload carrying the code; min_hz/max_hz
# are the HARDWARE clamp bounds (None = that end is limited only by the field).

CHIP_CLK = ClockKnob(
    "chip_clk", field_bits=20, default_hz=100e6, bypass_code=0,
    note="clock to the chip; the only knob that reaches the full bus clock, "
         "via the bypass code. No hardware clamp: it is not a data clock.")

CHIP_SCK = ClockKnob(
    "chip_sck", field_bits=20, default_hz=5e6, max_hz=25e6,
    note="Quad-SPI clock to the chip. Clamped fast-end only (quad_spi_master.sv); "
         "the practical ceiling is lower still (~8-17 MHz) from the read turnaround.")

DAC_SCK = ClockKnob(
    "dac_sck", field_bits=20, default_hz=1e3, min_hz=50, max_hz=25e6,
    note="DAC SPI clock. Clamped both ends (perip_controller.sv).")

S2P_SCK = ClockKnob(
    "s2p_sck", field_bits=20, default_hz=1e3, min_hz=50, max_hz=25e6,
    note="HV9308 shift clock. Same clamp as dac_sck; note the HV9308 itself is "
         "only rated to 8 MHz, which the FPGA-side clamp does not enforce.")

PLL_STRB = ClockKnob(
    "pll_strb", field_bits=24, default_hz=1e3, min_hz=50, max_hz=25e6,
    note="PLL serial-config strobe. 24-bit field because it rides a 3-byte "
         "little-endian payload rather than a 32-bit command word.")

ALL_KNOBS = (CHIP_CLK, CHIP_SCK, DAC_SCK, S2P_SCK, PLL_STRB)


def set_clock(knob, hz, emit, logger=None):
    """Shared body of every set_*_hz() driver method.

    Converts, sends via `emit(half)`, logs uniformly, warns when the request was
    not reachable, and returns the rate actually achieved. Keeping this in one
    place is the point of the module: five knobs, one set of user-facing
    semantics.
    """
    half, actual = knob.half_for(hz)
    emit(half)
    if logger is not None:
        code = "bypass" if half == knob.bypass_code else "{} bus cycles".format(half)
        logger.info("%s set to %s (half-period %s; requested %s)",
                    knob.name, _fmt_hz(actual), code, _fmt_hz(hz))
        if knob.is_clamped(hz, actual):
            logger.warning("%s %s is not reachable; running at %s. %s",
                           knob.name, _fmt_hz(hz), _fmt_hz(actual), knob.describe())
    return actual


def describe_all():
    """Every knob's range, for `--help`-style output and bring-up notes."""
    return "\n".join(k.describe() for k in ALL_KNOBS)

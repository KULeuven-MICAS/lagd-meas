# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# ISA of the PLL serial-configuration controller.
# Must stay in sync with fpga/src/verilog/pll_command_api.sv and the field layout
# in lagd-im/target/syn/tech/tsmc7ff/rtl/configs/pomelo_pll_wrap_cfg.yml.
#
# The PLL hangs off the 8-bit Xillybus stream (/dev/xillybus_{write,read}_8), so a
# command is a multi-byte frame. The first byte is the header: top nibble is the
# marker (0xF = "this is a command"), bottom nibble is the opcode.
#
#   byte 0    : header  = (0xF << 4) | opcode
#   byte 1..N : opcode-dependent payload (little-endian for LOAD)
#
#   opcode | header | name          | payload | action
#   -------+--------+---------------+---------+--------------------------------------
#   0x0    | 0xF0   | LOAD          | 6 bytes | shift 47 bits MSB-first, then commit
#   0x1    | 0xF1   | LOAD_LOOPBACK | 6 bytes | LOAD + echo the 6 payload bytes back
#   0x2    | 0xF2   | CLK_SEL       | 1 byte  | set static clk_sel (byte[0])
#   0x3    | 0xF3   | RESET         | 0 bytes | pulse both strobes -> reset PLL regs
#   0x4    | 0xF4   | READBACK      | 0 bytes | scan shallow reg out of data_o -> 6 bytes
#   0x5    | 0xF5   | STATUS        | 0 bytes | return 1 status byte (bit0 = pll_lock)
#   0x6    | 0xF6   | CONFIG_STRB   | 3 bytes | set the strobe half-period (LE)
#   0xF    | 0xFF   | WRITEBACK     | 0 bytes | echo the 0xFF header back (liveness)
#
# READBACK returns the 47-bit shallow-register content (what the PLL silicon
# captured) as 6 little-endian bytes -- reassemble with join_le and compare. It is
# stronger than LOAD_LOOPBACK (which only echoes what the FPGA assembled), but it
# observes the shallow register, not the hidden one (no scan tap on the latter).
#
# The 47-bit config word is the value the FPGA shifts into the PLL's shallow
# register MSB-first; here it is split little-endian into 6 bytes (byte0 = bits
# [7:0] ... byte5 = bits [46:40]).
#
# clk_sel: 0 -> PLL output drives the SoC clock; 1 -> reference/bypass clock.
# The PLL's reset defaults power it down (pdown_PD=pdown_VCO=1), so boot on the
# reference (clk_sel=1) and switch to the PLL only after configuring it.

from collections import namedtuple
from typing import Dict, List

from sw.lib import clock_api
from sw.lib.clock_api import PLL_STRB

# Handshake marker and opcodes (mirror pll_command_api.sv).
CMD_MARKER = 0xF
OP_LOAD = 0x0  # shift 47 bits + commit
OP_LOAD_LOOPBACK = 0x1  # LOAD + echo the 6 payload bytes
OP_CLK_SEL = 0x2  # set clk_sel from 1 payload byte
OP_RESET = 0x3  # pulse both strobes (reset registers)
OP_READBACK = 0x4  # scan shallow register out of data_o -> 6 bytes
OP_STATUS = 0x5  # return 1 status byte (bit0 = pll_lock)
OP_CONFIG_STRB = 0x6  # set the strobe half-period (3 little-endian bytes)
OP_WRITEBACK = 0xF  # echo header (no PLL action)

CFG_BITS = 47
CFG_BYTES = 6

# CONFIG_STRB payload: a 24-bit half-period, little-endian.
STRB_BYTES = 3

BUS_CLK_HZ = clock_api.BUS_CLK_HZ  # xillydemo.v: CLK_HZ
STRB_HZ = PLL_STRB.default_hz  # power-on default
STRB_MAX_HZ = PLL_STRB.max_hz  # hardware clamp: fastest selectable
STRB_MIN_HZ = PLL_STRB.min_hz  # hardware clamp: slowest selectable

STRB_HALF_MIN = PLL_STRB.half_min
STRB_HALF_MAX = PLL_STRB.half_max
assert PLL_STRB.field_bits == 8 * STRB_BYTES, "knob field width must match the payload bytes"

# STATUS byte bit positions (mirror pll_command_api.sv).
STATUS_LOCK_BIT = 0  # 1 = PLL locked


# ---------------------------------------------------------------------------
# Configuration field layout (pll_cfg_pkg::pll_cfg_t / pack_pll_cfg).
# Each field: name, lsb position in the 47-bit word, bit width, reset default.
# ---------------------------------------------------------------------------
Field = namedtuple("Field", ["name", "lsb", "width", "default", "desc"])


FIELDS = [
    Field("fb_clk_oen", 0, 1, 0, "Feedback clock output enable"),
    Field("pll_clk_o_en", 1, 1, 0, "PLL clock output enable"),
    Field("clk_div_val", 2, 10, 0x3FF, "Output clock division value"),
    Field("clk_div_en", 12, 1, 0, "Clock division enable"),
    Field("pdown_PD", 13, 1, 1, "Power down phase detector (active high)"),
    Field("pdown_VCO", 14, 1, 1, "Power down VCO (active high)"),
    Field("set_current", 15, 3, 0b100, "Charge pump current level"),
    Field("set_c1", 18, 3, 0b100, "Loop filter C1"),
    Field("set_c2", 21, 3, 0b100, "Loop filter C2"),
    Field("set_r1", 24, 3, 0b100, "Loop filter Rp"),
    Field("vco_tune_coarse", 27, 4, 0b1000, "Oscillator inverter chain length"),
    Field("vco_current_min", 31, 4, 0b1000, "VCO minimum current"),
    Field("vco_current_max", 35, 4, 0b1000, "VCO maximum current"),
    Field("set_v_ctrl", 39, 2, 0b10, "VCO control voltage source"),
    Field("set_clk_out", 41, 1, 0, "Output clock source (0:PLL, 1:CLK_EXT)"),
    Field("set_div_freq", 42, 3, 0b100, "Frequency division ratio"),
    Field("set_fb_mux", 45, 2, 0b00, "Feedback clock source"),
]


def pack_pll_cfg(**overrides) -> int:
    """Build the 47-bit config word from per-field values (defaults otherwise).

    Mirrors pll_cfg_pkg::pack_pll_cfg. Unknown field names raise KeyError; values
    are masked to each field's width.

        word = pack_pll_cfg(pdown_PD=0, pdown_VCO=0, vco_tune_coarse=0xA)
    """
    word = 0
    for f in FIELDS:
        val = overrides.pop(f.name, f.default) & ((1 << f.width) - 1)
        word |= val << f.lsb
    if overrides:
        raise KeyError(f"unknown PLL config field(s): {sorted(overrides)}")
    return word & ((1 << CFG_BITS) - 1)


def unpack_pll_cfg(word: int) -> Dict[str, int]:
    """Inverse of pack_pll_cfg: split a 47-bit word into named fields."""
    return {f.name: (word >> f.lsb) & ((1 << f.width) - 1) for f in FIELDS}


def rst_pll_cfg() -> int:
    """The reset-default config word (mirrors pll_cfg_pkg::rst_pll_cfg)."""
    return pack_pll_cfg()


# Default *operating* configuration: a known-good, PLL-enabled config. Taken
# field-for-field from the chip reference testbench tb_lagd_clk_gen.sv
# (pll_cfg_pkg test_cfg); it packs to 0x02971616A9011. The driver loads this by
# default (load_default / bring_up). It is DISTINCT from the per-field reset
# defaults in FIELDS, which mirror the silicon power-on state (PLL powered down,
# pdown_*=1) and must stay in sync with pomelo_pll_wrap_cfg.yml.
DEFAULT_CFG = {
    "fb_clk_oen": 0b1,  # ?
    "pll_clk_o_en": 0b0,  # clk_o comes from the divider outside the PLL
    "clk_div_val": 4,  # divider outside IP, divides frequency by 4+1
    "clk_div_en": 0b1,  # enabled divider outside the PLL
    "pdown_PD": 0b0,  # PLL enabled
    "pdown_VCO": 0b0,  # PLL enabled
    "set_current": 0b011,  # Icp = pll_iref_i (check)
    "set_c1": 0b011,  # C1 = 20 pF (check)
    "set_c2": 0b011,  # C2 = 500 fF (check)
    "set_r1": 0b011,  # R1 = 5 kOhm (check)
    "vco_tune_coarse": 0b1010,
    "vco_current_min": 0b1100,
    "vco_current_max": 0b1101,
    "set_v_ctrl": 0b10,  # Debug mode, 00 for default and 11 for out pad
    "set_clk_out": 0b0,  # PLL loop closed, 1 for CLK_EXT
    "set_div_freq": 0b010,  # Ndiv = 4
    "set_fb_mux": 0b00,  # Loop closed, 01 for loop broken and F_FB used,
    # 10 for clock buffered to F_FB and loop closed
}


def default_cfg_word(**overrides) -> int:
    """Packed 47-bit default operating config (DEFAULT_CFG), with optional overrides."""
    cfg = dict(DEFAULT_CFG)
    cfg.update(overrides)
    return pack_pll_cfg(**cfg)


def cfg_word(cfg, **overrides) -> int:
    """Packed 47-bit config word from a dictionary of field values."""
    cfg = dict(cfg)
    cfg.update(overrides)
    return pack_pll_cfg(**cfg)


def calculate_div_factor(cfg) -> tuple:
    """Calculation of total division factor given a configuration"""
    chip_div_factor = 2 ** (cfg["set_div_freq"])
    total_div_factor = chip_div_factor
    if cfg["pll_clk_o_en"] == 0b0:
        if cfg["clk_div_en"] == 0b0:
            raise KeyError("Invalid configuration: divider path chosen but divider not enabled")
        else:
            total_div_factor = total_div_factor * 2 * (cfg["clk_div_val"] + 1)
    return chip_div_factor, total_div_factor


# ---------------------------------------------------------------------------
# Frame builders. Each returns a list[int] of bytes ready for the 8-bit stream.
# ---------------------------------------------------------------------------
def header(opcode: int) -> int:
    """The 1-byte command header for an opcode: (0xF << 4) | opcode."""
    return ((CMD_MARKER & 0xF) << 4) | (opcode & 0xF)


def split_le(word: int) -> List[int]:
    """Split a 47-bit config word into 6 little-endian bytes (byte0 = bits[7:0])."""
    return [(word >> (8 * k)) & 0xFF for k in range(CFG_BYTES)]


def join_le(payload: List[int]) -> int:
    """Reassemble a 47-bit word from 6 little-endian payload bytes."""
    word = 0
    for k, b in enumerate(payload):
        word |= (b & 0xFF) << (8 * k)
    return word & ((1 << CFG_BITS) - 1)


def cmd_load(word: int) -> List[int]:
    """Frame for LOAD: header + 6 little-endian payload bytes (shift + commit)."""
    return [header(OP_LOAD)] + split_le(word)


def cmd_load_loopback(word: int) -> List[int]:
    """Frame for LOAD_LOOPBACK: LOAD that also echoes the 6 payload bytes back."""
    return [header(OP_LOAD_LOOPBACK)] + split_le(word)


def cmd_clk_sel(sel: int) -> List[int]:
    """Frame for CLK_SEL: header + 1 byte (bit0 = clk_sel; 0=PLL, 1=reference)."""
    return [header(OP_CLK_SEL), sel & 0x01]


def cmd_reset() -> List[int]:
    """Frame for RESET: header only (pulses both strobes -> reset PLL registers)."""
    return [header(OP_RESET)]


def cmd_readback() -> List[int]:
    """Frame for READBACK: header only; the controller returns 6 little-endian bytes."""
    return [header(OP_READBACK)]


def cmd_status() -> List[int]:
    """Frame for STATUS: header only; the controller returns 1 byte (bit0 = lock)."""
    return [header(OP_STATUS)]


def cmd_writeback() -> List[int]:
    """Frame for WRITEBACK: header only (echoes 0xFF back; controller liveness)."""
    return [header(OP_WRITEBACK)]


def strb_half_for(strb_hz, bus_clk_hz=BUS_CLK_HZ):
    """Half-period in bus-clock cycles for a requested strobe rate, and what
    you'll get.

    Returns (half, actual_hz), clamped to the same window the hardware enforces.
    The divider is integer, so the achieved rate is bus_clk_hz / (2*half) and
    generally differs from the request.
    """
    if bus_clk_hz != BUS_CLK_HZ:
        raise ValueError("bus_clk_hz is fixed by the bitstream; see clock_api")
    return PLL_STRB.half_for(strb_hz)


def cmd_config_strb(strb_half: int) -> List[int]:
    """Frame for CONFIG_STRB: header + 3 little-endian bytes of half-period.

    Takes effect on the next command. Out-of-range values are clamped by the
    hardware, so the rate saturates rather than hanging the strobe engine.
    """
    PLL_STRB.check_half(strb_half)
    return [header(OP_CONFIG_STRB)] + [(strb_half >> (8 * k)) & 0xFF for k in range(STRB_BYTES)]

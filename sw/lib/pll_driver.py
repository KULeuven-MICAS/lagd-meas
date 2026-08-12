# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Command-layer driver for the PLL serial-configuration ports.
#
# Exposes the pll_controller command set (see fpga/src/verilog/pll_command_api.sv)
# as methods on top of the shared PortDriver. Unlike the chip / periphery drivers
# (32-bit words), the PLL uses the 8-bit Xillybus stream, so this driver sends and
# receives raw bytes (sendByte / readByte) rather than 32-bit words.
#
# IMPORTANT bring-up note: clk_sel selects the SoC clock (0 = PLL, 1 = reference).
# The PLL powers up disabled (pdown_PD=pdown_VCO=1) and the bitstream defaults
# clk_sel=1, so the RISC-V boots on the reference clock. To run on the PLL:
#   1. configure the PLL with pdown_PD=0 / pdown_VCO=0 (+ VCO/loop settings),
#   2. wait for it to lock -- pll_lock_o is wired back (pll_lock_i), so poll it via
#      read_lock()/wait_lock() (the STATUS command),
#   3. switch clk_sel=0 (select_pll). The clock mux is not glitchless, so do this
#      with the core held in reset / quiesced.
# bring_up() does 1-3 (waiting for lock, only switching once locked).

import logging
import time
from typing import Dict, List, Optional

from sw.lib.port_driver import PortDriver
from sw.lib.clock_api import PLL_STRB, set_clock
from sw.lib.pll_command_api import (
    CFG_BITS,
    CFG_BYTES,
    STATUS_LOCK_BIT,
    STRB_HZ,
    DEFAULT_CFG,
    cmd_load,
    cmd_load_loopback,
    cmd_clk_sel,
    cmd_reset,
    cmd_readback,
    cmd_status,
    cmd_writeback,
    cmd_config_strb,
    strb_half_for,
    pack_pll_cfg,
    unpack_pll_cfg,
    rst_pll_cfg,
    join_le,
)

logger = logging.getLogger(__name__)

# clk_sel encodings (mirror the clk mux in lagd_clk_gen.sv).
CLK_SEL_PLL       = 0   # I0 = pll_clk_o
CLK_SEL_REFERENCE = 1   # I1 = clk_i (reference / bypass)


def default_timeout(bits, strb_hz):
    """Read timeout for a command that shifts `bits` bits at `strb_hz`.

    The strobe is runtime-configurable down to 50 Hz, where a 47-bit scan takes
    nearly a second -- a fixed timeout would report a phantom failure. The 3x
    factor covers host-side poll overhead; the constant covers the rest.
    """
    return bits / float(strb_hz) * 3.0 + 0.1


class PllDriver(PortDriver):
    """Drives the pll_controller command set over the 8-bit write/read ports.

    Usable directly, or as a context manager that opens/closes both ports:

        with PllDriver(WRITE_DEV, READ_DEV) as pll:
            assert pll.writeback() == 0xFF          # controller alive
            word = pll.load_cfg(pdown_PD=0, pdown_VCO=0)
            assert pll.verify_load(word) == word    # config path verified
            pll.select_pll()                        # switch SoC onto the PLL

    pll_lock_o is not wired back to the FPGA (scope-only), so the driver keeps a
    host-side cache of the last config word written and the last clk_sel set.
    """

    def __init__(self, write_dev: str, read_dev: str) -> None:
        super().__init__(write_dev, read_dev, width=8)
        self._cfg: Optional[int] = None         # last config word written
        self._clk_sel: Optional[int] = None     # last clk_sel set
        # Strobe rate the controller is currently running at. It powers up at
        # STRB_HZ and changes only through set_strb_hz.
        self.strb_hz = float(STRB_HZ)

    def set_strb_hz(self, strb_hz: float) -> float:
        """Set the PLL serial-config strobe rate; return the rate achieved.

        The divider is integer and the hardware clamps to STRB_MIN_HZ..STRB_MAX_HZ,
        so the achieved rate can differ from the request. Applies to the next
        command. Both strobes are gated clocks into the PLL over FMC wiring, so
        raise this only as far as that path is known to be reliable.
        """
        self.strb_hz = set_clock(
            PLL_STRB, strb_hz,
            lambda half: self._send_bytes(cmd_config_strb(half)), logger)
        return self.strb_hz

    # ---- byte-level transport helpers ----
    def _send_bytes(self, data: List[int]) -> None:
        for b in data:
            self.wp.sendByte(b & 0xFF)

    def _flush_read(self) -> None:
        """Drain any stale bytes from the read port."""
        while self.rp.readByte() is not None:
            pass

    def read_byte(self, timeout: float = 0.1) -> Optional[int]:
        """Poll the non-blocking read port until one byte arrives (or timeout)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            b = self.rp.readByte()
            if b is not None:
                return b
            time.sleep(0.001)
        return None

    def read_bytes(self, n: int, timeout: float = 0.2) -> Optional[List[int]]:
        """Collect exactly n bytes; None if they don't all arrive within timeout."""
        out: List[int] = []
        deadline = time.time() + timeout
        while len(out) < n and time.time() < deadline:
            b = self.rp.readByte()
            if b is None:
                time.sleep(0.001)
                continue
            out.append(b)
        return out if len(out) == n else None

    # ---- raw command set (see pll_command_api.sv) ----
    def load(self, word: int) -> None:
        """LOAD a 47-bit config word: shift it in MSB-first and commit (no echo)."""
        self._send_bytes(cmd_load(word))
        self._cfg = word & ((1 << 47) - 1)

    def load_cfg(self, **fields) -> int:
        """LOAD a config built from named fields, with the per-field *reset* defaults
        (FIELDS) for anything unspecified. Returns the packed 47-bit word."""
        word = pack_pll_cfg(**fields)
        self.load(word)
        return word

    def load_default(self, **overrides) -> int:
        """LOAD the default *operating* config (DEFAULT_CFG, PLL enabled), with
        optional per-field overrides. Returns the packed 47-bit word.

        Unlike load_cfg(), unspecified fields take their DEFAULT_CFG value (a
        known-good running config), not the powered-down reset default."""
        cfg = dict(DEFAULT_CFG)
        cfg.update(overrides)
        return self.load_cfg(**cfg)

    def verify_load(self, word: int) -> Optional[int]:
        """LOAD_LOOPBACK: commit the config AND read the 6 echoed payload bytes.

        Returns the word reconstructed from the echo (should equal `word`), or
        None if the 6 bytes did not all come back. Confirms the command path -- the
        controller assembled exactly these 47 bits -- independent of PLL behaviour.
        """
        self._flush_read()
        self._send_bytes(cmd_load_loopback(word))
        payload = self.read_bytes(CFG_BYTES, default_timeout(CFG_BITS + 1, self.strb_hz))
        self._cfg = word & ((1 << 47) - 1)
        return None if payload is None else join_le(payload)

    def verify_load_cfg(self, **fields) -> bool:
        """LOAD_LOOPBACK a field-built config and check the echo matches."""
        word = pack_pll_cfg(**fields)
        return self.verify_load(word) == word

    def reset(self) -> None:
        """RESET: pulse both strobes to reset the PLL registers to their defaults."""
        self._send_bytes(cmd_reset())
        self._cfg = rst_pll_cfg()

    def readback(self) -> Optional[int]:
        """READBACK: scan the shallow register out of the PLL's data_o and return it.

        The controller shifts the 47-bit shallow register out through data_o,
        recirculating each bit (so the register is preserved), and returns its
        content as 6 little-endian bytes. Returns the reassembled 47-bit word, or
        None if the 6 bytes did not all arrive.

        Unlike verify_load() -- which echoes what the *FPGA* assembled -- this reads
        what the *PLL silicon* actually captured. It observes the shallow register
        (cfg_data_raw_n), not the hidden one, so it verifies the shift chain and the
        loaded value (the source of the last commit), not the hidden latches.
        """
        self._flush_read()
        self._send_bytes(cmd_readback())
        payload = self.read_bytes(CFG_BYTES, default_timeout(CFG_BITS + 1, self.strb_hz))
        return None if payload is None else join_le(payload)

    def verify(self, word: int) -> bool:
        """LOAD `word`, then READBACK and confirm the silicon captured it.

            assert pll.verify(pll_cfg)   # strongest available digital check
        """
        self.load(word)
        return self.readback() == (word & ((1 << 47) - 1))

    def verify_cfg(self, **fields) -> bool:
        """LOAD a field-built config, then READBACK and confirm it matches."""
        return self.verify(pack_pll_cfg(**fields))

    def read_status(self) -> Optional[int]:
        """STATUS: return the 1-byte status (bit0 = PLL lock), or None on timeout."""
        self._flush_read()
        self._send_bytes(cmd_status())
        return self.read_byte()

    def read_lock(self) -> Optional[int]:
        """Return the PLL lock bit (1 = locked, 0 = not), or None on timeout."""
        status = self.read_status()
        return None if status is None else ((status >> STATUS_LOCK_BIT) & 1)

    def is_locked(self) -> bool:
        """True iff the PLL reports lock (a None/timeout reads as not locked)."""
        return self.read_lock() == 1

    def wait_lock(self, timeout: float = 1.0, poll: float = 0.01) -> bool:
        """Poll STATUS until the PLL reports lock or `timeout` (seconds) elapses.

        Returns True if lock was observed, False on timeout. Lock is genuinely
        readable now (pll_lock_i wired back), so this replaces blind settle delays.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.read_lock() == 1:
                return True
            time.sleep(poll)
        return False

    def clk_sel(self, sel: int) -> None:
        """Set the SoC clock source (0 = PLL, 1 = reference). See class docstring."""
        self._send_bytes(cmd_clk_sel(sel))
        self._clk_sel = sel & 0x01

    def writeback(self) -> Optional[int]:
        """WRITEBACK liveness check: returns the echoed header byte (0xFF) or None."""
        self._flush_read()
        self._send_bytes(cmd_writeback())
        return self.read_byte()

    # ---- conveniences ----
    def select_pll(self) -> None:
        """Route the SoC clock to the PLL output (clk_sel=0)."""
        self.clk_sel(CLK_SEL_PLL)

    def select_reference(self) -> None:
        """Route the SoC clock to the reference/bypass clock (clk_sel=1)."""
        self.clk_sel(CLK_SEL_REFERENCE)

    def bring_up(self, lock_timeout: float = 1.0, switch: bool = True,
                 require_lock: bool = True, **overrides) -> bool:
        """Configure the PLL, wait for lock, and (optionally) switch the SoC onto it.

        Loads the default operating config (DEFAULT_CFG, PLL enabled) with any
        per-field `overrides`, then polls STATUS until the PLL locks (up to
        `lock_timeout` seconds) -- lock is readable via pll_lock_i, so this is a real
        wait, not a blind delay. If `switch`, selects the PLL as the SoC clock once
        locked (or anyway, if require_lock=False). Returns True iff lock was observed.

        Hold the core in reset across the switch (the clock mux is not glitchless),
        and leave require_lock=True so the SoC is never switched onto an unlocked
        clock.
        """
        self.load_default(**overrides)
        locked = self.wait_lock(timeout=lock_timeout)
        if switch and (locked or not require_lock):
            self.select_pll()
        return locked

    def get_cfg(self) -> Optional[int]:
        """Last config word written (host-side cache; None if never written)."""
        return self._cfg

    def get_cfg_fields(self) -> Optional[Dict[str, int]]:
        """Last config as named fields (host-side cache; None if never written)."""
        return None if self._cfg is None else unpack_pll_cfg(self._cfg)

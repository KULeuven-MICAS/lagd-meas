# Copyright 2025 KU Leuven.
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
#   2. wait for it to lock -- pll_lock_o is observed on the scope, NOT wired back
#      to the FPGA, so software cannot poll it; use a fixed settle delay,
#   3. switch clk_sel=0 (select_pll). The clock mux is not glitchless, so do this
#      with the core held in reset / quiesced.

import time
from typing import Dict, List, Optional

from lib.port_driver import PortDriver
from lib.pll_command_api import (
    CFG_BYTES,
    cmd_load,
    cmd_load_loopback,
    cmd_clk_sel,
    cmd_reset,
    cmd_writeback,
    pack_pll_cfg,
    unpack_pll_cfg,
    rst_pll_cfg,
    join_le,
)

# clk_sel encodings (mirror the clk mux in lagd_clk_gen.sv).
CLK_SEL_PLL       = 0   # I0 = pll_clk_o
CLK_SEL_REFERENCE = 1   # I1 = clk_i (reference / bypass)


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
        """LOAD a config built from named fields (defaults otherwise). Returns the
        packed 47-bit word. See pll_command_api.FIELDS for the field names."""
        word = pack_pll_cfg(**fields)
        self.load(word)
        return word

    def verify_load(self, word: int) -> Optional[int]:
        """LOAD_LOOPBACK: commit the config AND read the 6 echoed payload bytes.

        Returns the word reconstructed from the echo (should equal `word`), or
        None if the 6 bytes did not all come back. Confirms the command path -- the
        controller assembled exactly these 47 bits -- independent of PLL behaviour.
        """
        self._flush_read()
        self._send_bytes(cmd_load_loopback(word))
        payload = self.read_bytes(CFG_BYTES)
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

    def bring_up(self, settle_s: float = 0.01, switch: bool = True, **fields) -> int:
        """Configure the PLL and (optionally) switch the SoC onto it.

        Loads a config with the PLL enabled (pdown_PD=0, pdown_VCO=0 unless
        overridden), waits `settle_s` for it to lock (lock is scope-observed, not
        readable here), then -- if `switch` -- selects the PLL as the SoC clock.
        Returns the config word written. Hold the core in reset across the switch
        (the clock mux is not glitchless).
        """
        fields.setdefault("pdown_PD", 0)
        fields.setdefault("pdown_VCO", 0)
        word = self.load_cfg(**fields)
        time.sleep(settle_s)
        if switch:
            self.select_pll()
        return word

    def get_cfg(self) -> Optional[int]:
        """Last config word written (host-side cache; None if never written)."""
        return self._cfg

    def get_cfg_fields(self) -> Optional[Dict[str, int]]:
        """Last config as named fields (host-side cache; None if never written)."""
        return None if self._cfg is None else unpack_pll_cfg(self._cfg)

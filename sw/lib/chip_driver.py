# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Command-layer driver for the chip write/read ports (cwp/crp).
#
# Exposes the chip_controller command set (see fpga/src/verilog/chip_command_api.sv)
# as methods on top of the shared PortDriver, so other scripts can reuse the chip
# command layer without copy-pasting it or relying on globals.

import time
from typing import List, Optional, Union

from sw.lib.port_driver import PortDriver
from sw.lib.chip_command_api import (
    WRITEBACK_FIFO,
    make_command,
    cmd_config_spi_slave,
    cmd_config_clk_rst,
    cmd_write,
    cmd_write_loopback,
    cmd_read,
)

# Depth of the FPGA-to-xillinux readback FIFO (fifo_dualport_32x512). A loopback
# write echoes one word per data word; since verify_write_mem sends the whole
# burst before draining, the burst must fit in this FIFO or the controller stalls
# mid-burst waiting for software to drain it. Chunk longer data into <= this.
READBACK_FIFO_DEPTH = 512


class ChipDriver(PortDriver):
    """Drives the chip_controller command set over a WritePort + ReadPort.

    Usable directly, or as a context manager that opens/closes both ports:

        with ChipDriver(WRITE_DEV, READ_DEV) as chip:
            chip.init_spi()
            chip.write_mem(0x0, [0xDEAD, 0xBEEF])
            print(chip.read_mem(0x0, length=2))
    """

    # ---- chip command set (see chip_command_api.sv) ----
    def init_spi(self) -> None:
        """Enable Quad-SPI mode on the chip's SPI slave (write reg0 = 0x01)."""
        self._send_words(cmd_config_spi_slave())

    def config_clk_rst(self, chip_clk_en: int, chip_rstn: int) -> None:
        """Drive the chip clock enable (bit 1) and reset-n (bit 0)."""
        self._send_words(cmd_config_clk_rst(chip_clk_en, chip_rstn))

    def reset_chip(self, hold: float = 0.001, chip_clk_en: int = 1) -> None:
        """Pulse the chip's active-low reset: assert reset_n=0, hold, then release.

        Restarts the core over the reset signal without reloading the bitstream.
        The clock is left enabled (chip_clk_en=1) across the pulse so the core
        clocks out of reset on release; `hold` is the assert time in seconds.
        """
        self.config_clk_rst(chip_clk_en=chip_clk_en, chip_rstn=0)
        time.sleep(hold)
        self.config_clk_rst(chip_clk_en=chip_clk_en, chip_rstn=1)

    def write_mem(self, addr: int, data_words: Union[int, List[int]]) -> None:
        """Single or burst memory write. data_words: int or list of ints.

        Burst writes go to consecutive word addresses (addr, addr+4, ...).
        """
        self._send_words(cmd_write(addr, data_words))

    def read_mem(self, addr: int, length: int = 1, timeout: float = 0.5) -> List[int]:
        """Single or burst memory read.

        Returns a list of up to `length` ints (fewer if the read times out).
        Burst reads come from consecutive word addresses (addr, addr+4, ...).
        """
        self.rp.flushBuffer()
        self._send_words(cmd_read(addr, length))

        out = []  # type: List[int]
        deadline = time.time() + timeout
        while len(out) < length and time.time() < deadline:
            word = self.rp.readInt()
            if word is not None:
                out.append(word)
            else:
                time.sleep(0.001)
        return out

    def verify_write_mem(self, addr: int, data_words: Union[int, List[int]],
                         timeout: float = 0.5) -> List[int]:
        """Loopback write: write a burst AND read back the controller's echo.

        Sends a DATA_WRITE_LOOPBACK frame (a real SPI write) and drains the data
        words the controller mirrors into the read FIFO. The returned list should
        equal the words written, letting software confirm exactly what was
        streamed onto the Quad-SPI bus:

            sent = [0xDEAD, 0xBEEF]
            assert chip.verify_write_mem(0x0, sent) == sent

        Returns up to len(data_words) ints (fewer if the read times out). Because
        the whole burst is sent before draining, it must fit in the readback FIFO
        (READBACK_FIFO_DEPTH); longer bursts would stall the controller mid-burst.
        """
        if isinstance(data_words, int):
            data_words = [data_words]
        n = len(data_words)
        if n > READBACK_FIFO_DEPTH:
            raise ValueError(
                f"verify_write_mem burst {n} exceeds readback FIFO depth "
                f"{READBACK_FIFO_DEPTH}; split into smaller chunks"
            )

        self.rp.flushBuffer()
        self._send_words(cmd_write_loopback(addr, data_words))

        out = []  # type: List[int]
        deadline = time.time() + timeout
        while len(out) < n and time.time() < deadline:
            word = self.read_word(timeout)
            if word is not None:
                out.append(word)
            else:
                time.sleep(0.001)
        return out

    def writeback(self, payload: int = 0xADBEE) -> Optional[int]:
        """Send one WRITEBACK_FIFO command; return the echoed word (or None).

        The chip_controller loops the exact command word back into the read
        FIFO, so the returned value should equal the command that was sent. The
        marker + opcode occupy the top 12 bits, so the echoable payload is the
        low 20 bits ([19:0]).
        """
        return self._loopback(make_command(WRITEBACK_FIFO, payload))

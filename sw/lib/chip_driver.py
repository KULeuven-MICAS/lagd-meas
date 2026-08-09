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
import logging
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
    cmd_config_sck,
    sck_half_for,
)

# Depth of the FPGA-to-xillinux readback FIFO (fifo_dualport_32x512). A loopback
# write echoes one word per data word; since verify_write_mem sends the whole
# burst before draining, the burst must fit in this FIFO or the controller stalls
# mid-burst waiting for software to drain it. Chunk longer data into <= this.
READBACK_FIFO_DEPTH = 512

logger = logging.getLogger(__name__)

## Parameters for the SPI clock that are used to derive timeouts.
# xillydemo.v instantiates chip_controller with CHIP_SCK_HZ, and Quad-SPI moves
# 4 bits per SCK, so one 32-bit word costs 8 SCK periods. A read frame
# additionally pays 2 SCK of command, 8 of address and 33 dummy cycles.
#
# This is the POWER-ON default only - it must match CHIP_SCK_HZ in
# fpga/src/verilog/xillydemo.v. Software can retune at runtime with
# ChipDriver.set_sck_hz(), which updates the instance's self.sck_hz; all
# timeouts derive from that, not from this constant.
SCK_HZ = 5_000_000
SCK_PERIOD = 1.0 / SCK_HZ
SCK_PER_WORD = 8
READ_FRAME_OVERHEAD_SCK = 2 + 8 + 33  # command + address + dummy cycles
WRITE_FRAME_OVERHEAD_SCK = 2 + 8  # command + address (no dummy cycles on a write)


def read_frame_seconds(length: int, sck_hz: float = SCK_HZ) -> float:
    """Ideal wire time for an `length`-word burst read at `sck_hz`."""
    return (READ_FRAME_OVERHEAD_SCK + SCK_PER_WORD * length) / sck_hz


def write_frame_seconds(length: int, sck_hz: float = SCK_HZ) -> float:
    """Ideal wire time for an `length`-word burst write / loopback frame."""
    return (WRITE_FRAME_OVERHEAD_SCK + SCK_PER_WORD * length) / sck_hz


def default_read_timeout(length: int, sck_hz: float = SCK_HZ) -> float:
    """Timeout that actually covers the transfer, with margin.

    A fixed timeout is a trap: it silently truncates long bursts, and the
    caller then compares a short list against the full expected data and sees
    what looks like corruption. Scale with the burst instead.

    3x, not 1.5x: the host poll loop sleeps 1 ms whenever no word is ready, so
    at low SCK polling roughly DOUBLES the wall-clock time over the wire time
    (measured 17.4 ms/word against an 8.0 ms wire rate at 1 kHz). A 1.5x
    multiplier timed out two words short and desynchronised the stream.
    """
    return read_frame_seconds(length, sck_hz) * 3.0 + 0.5


def default_loopback_timeout(length: int, sck_hz: float = SCK_HZ) -> float:
    """Timeout covering a DATA_WRITE_LOOPBACK frame's echo, with margin.

    Same polling-overhead reasoning as default_read_timeout.
    """
    return write_frame_seconds(length, sck_hz) * 3.0 + 0.5


class ChipDriver(PortDriver):
    """Drives the chip_controller command set over a WritePort + ReadPort.

    Usable directly, or as a context manager that opens/closes both ports:

        with ChipDriver(WRITE_DEV, READ_DEV) as chip:
            chip.init_spi()
            chip.write_mem(0x0, [0xDEAD, 0xBEEF])
            print(chip.read_mem(0x0, length=2))
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Set SPI clock
        self.sck_hz = float(SCK_HZ)

    # ---- chip command set (see chip_command_api.sv) ----
    def set_sck_hz(self, sck_hz: float) -> float:
        """Retune the SPI clock at runtime. Returns the frequency achieved.

        SCK is an integer divide of the FPGA bus clock, so the achieved rate is
        BUS_CLK_HZ/(2*N). Takes effect on
        the NEXT SPI transaction, and the hardware clamps to SCK_MAX_HZ.
        """
        half, actual = sck_half_for(sck_hz)
        self._send_words(cmd_config_sck(half))
        self.sck_hz = actual
        logger.info("SCK set to %.3f kHz (half-period %d bus cycles; requested %.3f kHz)",
                    actual / 1e3, half, sck_hz / 1e3)
        return actual

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

    def _drain_quiet(self, quiet: float = 0.05, max_wait: float = 5.0) -> int:
        """Read and discard until the readback stream has been idle for `quiet`.

        Needed after a short/timed-out read: the FPGA keeps streaming the rest
        of the frame into the readback FIFO regardless of whether software is
        still listening. A plain flushBuffer() only clears what has ALREADY
        arrived, so words still in flight land afterwards and shift every
        subsequent read. Waiting for genuine quiet is what actually resyncs.

        Returns the number of stale words discarded.
        """
        dropped = 0
        deadline = time.time() + max_wait
        last_rx = time.time()
        while time.time() < deadline:
            word = self.rp.readInt()
            if word is not None:
                dropped += 1
                last_rx = time.time()
            else:
                if time.time() - last_rx >= quiet:
                    break
                time.sleep(0.001)
        return dropped

    def read_mem(self, addr: int, length: int = 1,
                 timeout: Optional[float] = None) -> List[int]:
        """Single or burst memory read.

        Returns a list of up to `length` ints (fewer if the read times out).
        Burst reads come from consecutive word addresses (addr, addr+4, ...).

        `timeout` defaults to a value derived from the burst length and the
        current SCK (see default_read_timeout). Passing a fixed value is almost
        always a mistake.
        """
        if timeout is None:
            timeout = default_read_timeout(length, self.sck_hz)

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

        if len(out) < length:
            # Drain to a quiet bus before returning.
            stale = self._drain_quiet()
            logger.warning(
                "read_mem: TIMEOUT at 0x%08X - got %d/%d words in %.2f s "
                "(the frame needs ~%.2f s at %d Hz SCK). This is a timeout, "
                "NOT data corruption; pass a larger timeout.",
                addr, len(out), length, timeout, read_frame_seconds(length, self.sck_hz), self.sck_hz)
            if stale:
                logger.warning("read_mem: drained %d stale word(s) to resynchronise "
                               "the readback stream", stale)
        return out

    def write_mem_verified(self, addr: int, data_words: Union[int, List[int]],
                           chunk: int = 16, retries: int = 8,
                           timeout: float = 0.0) -> int:
        """Write the chip, read back, compare, and retry until the data really landed.

        This is the ONLY write primitive that proves anything about the chip.
        write_mem() is fire-and-forget, and verify_write_mem() only echoes what
        the FPGA streamed onto the wire.

        Writes in small chunks and verifies each one.
        Returns the total number of retries used. Raises IOError if any chunk
        could not be written within `retries` attempts.
        """
        if isinstance(data_words, int):
            data_words = [data_words]

        total_retries = 0
        for off in range(0, len(data_words), chunk):
            piece = data_words[off:off + chunk]
            piece_addr = addr + 4 * off
            tmo = timeout or default_read_timeout(len(piece), self.sck_hz)

            for attempt in range(retries):
                self.write_mem(piece_addr, piece)
                got = self.read_mem(piece_addr, length=len(piece), timeout=tmo)
                if got == piece:
                    break
                total_retries += 1
                good = 0
                for g, e in zip(got, piece):
                    if g != e:
                        break
                    good += 1
                logger.warning(
                    "write_mem_verified: 0x%08X chunk of %d words failed "
                    "(attempt %d/%d, %d words landed) - retrying",
                    piece_addr, len(piece), attempt + 1, retries, good)
            else:
                raise IOError(
                    "write_mem_verified: gave up on 0x%08X after %d attempts; "
                    "the SPI link is too unreliable to write memory"
                    % (piece_addr, retries))

        return total_retries

    def verify_write_mem(self, addr: int, data_words: Union[int, List[int]],
                         timeout: Optional[float] = None) -> List[int]:
        """Loopback write: write a burst AND read back the controller's echo.

        WARNING: this does NOT verify the chip received anything. The echo is
        produced by the FPGA's own chip_controller mirroring the words it put on
        the wire. Use write_mem_verified() for a real end-to-end check.

        Sends a DATA_WRITE_LOOPBACK frame (a real SPI write) and drains the data
        words the controller mirrors into the read FIFO. The returned list should
        equal the words written, letting software confirm exactly what was
        streamed onto the Quad-SPI bus:

            sent = [0xDEAD, 0xBEEF]
            assert chip.verify_write_mem(0x0, sent) == sent

        Returns up to len(data_words) ints (fewer if the read times out). Because
        the whole burst is sent before draining, it must fit in the readback FIFO
        (READBACK_FIFO_DEPTH); longer bursts would stall the controller mid-burst.

        `timeout` defaults to a value derived from the burst length and the
        current SCK.
        """
        if isinstance(data_words, int):
            data_words = [data_words]
        n = len(data_words)
        if n > READBACK_FIFO_DEPTH:
            raise ValueError(
                f"verify_write_mem burst {n} exceeds readback FIFO depth "
                f"{READBACK_FIFO_DEPTH}; split into smaller chunks"
            )
        if timeout is None:
            timeout = default_loopback_timeout(n, self.sck_hz)

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

        if len(out) < n:
            logger.warning(
                "verify_write_mem: TIMEOUT at 0x%08X - got %d/%d echoed words in "
                "%.2f s (the frame needs ~%.2f s at %d Hz SCK). This is a timeout, "
                "NOT a link fault.",
                addr, len(out), n, timeout, write_frame_seconds(n, self.sck_hz), self.sck_hz)
        return out

    def writeback(self, payload: int = 0xADBEE) -> Optional[int]:
        """Send one WRITEBACK_FIFO command; return the echoed word (or None).

        The chip_controller loops the exact command word back into the read
        FIFO, so the returned value should equal the command that was sent. The
        marker + opcode occupy the top 12 bits, so the echoable payload is the
        low 20 bits ([19:0]).
        """
        return self._loopback(make_command(WRITEBACK_FIFO, payload))

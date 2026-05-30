# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Shared base for the command-layer drivers (chip and periphery).
#
# Owns a WritePort + ReadPort and provides the parts common to both subsystems:
# port lifecycle (open/close/context manager), word sending, read polling, and
# the writeback-loopback primitive. Subsystem-specific drivers (ChipDriver,
# PeripDriver) subclass this and add their own command methods.

import time
from typing import List, Optional, TypeVar

from lib.write_port import WritePort
from lib.read_port import ReadPort

# Bound to the concrete subclass so `with ChipDriver(...) as c` types `c` as a
# ChipDriver (not the PortDriver base).
_DriverT = TypeVar("_DriverT", bound="PortDriver")


class PortDriver:
    """Owns a WritePort + ReadPort; base for the chip / periphery drivers.

    Usable directly, or as a context manager that opens and closes both ports.
    """

    def __init__(self, write_dev: str, read_dev: str, width: int = 32) -> None:
        self.wp = WritePort(write_dev, width)
        self.rp = ReadPort(read_dev, width)

    # ---- lifecycle ----
    def open(self) -> None:
        """Open both the write and read ports."""
        self.wp.openPort()
        self.rp.openPort()

    def close(self) -> None:
        """Close both the write and read ports."""
        self.wp.closePort()
        self.rp.closePort()

    def __enter__(self: _DriverT) -> _DriverT:
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    # ---- low-level helpers ----
    def _send_words(self, words: List[int]) -> None:
        """Send a list of 32-bit words to the write port."""
        for word in words:
            self.wp.sendInt(word)

    def read_word(self, timeout: float = 0.02) -> Optional[int]:
        """Poll the (non-blocking) read port until one 32-bit word arrives.

        Returns the word as an int, or None if nothing came back within timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            word = self.rp.readInt()
            if word is not None:
                return word
            time.sleep(0.001)
        return None

    def _loopback(self, command_word: int, timeout: float = 0.02) -> Optional[int]:
        """Send one writeback command word and return the echoed word (or None).

        The controller loops the exact command word straight back into the read
        FIFO, so the returned value should equal `command_word`.
        """
        self.rp.flushBuffer()
        self.wp.sendInt(command_word)
        return self.read_word(timeout)

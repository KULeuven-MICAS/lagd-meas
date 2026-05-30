# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Command-layer driver for the periphery (DAC) write/read ports.
#
# Exposes the perip_controller command set (see fpga/src/verilog/perip_command_api.sv)
# as methods on top of the shared PortDriver.

from typing import Optional

from lib.port_driver import PortDriver
from lib.perip_command_api import (
    OP_WRITEBACK,
    make_command,
    cmd_dac_write,
    cmd_dac_reset,
)


class PeripDriver(PortDriver):
    """Drives the perip_controller (DAC) command set over a WritePort + ReadPort.

    Usable directly, or as a context manager that opens/closes both ports:

        with PeripDriver(WRITE_DEV, READ_DEV) as dac:
            dac.dac_write(addr=0x1, data=0x80)   # write 0x80 to DAC register 0x1
    """

    # ---- periphery command set (see perip_command_api.sv) ----
    def dac_write(self, addr: int, data: int, rstn: int = 1, shdn: int = 1) -> None:
        """Write one DAC register: a 12-bit {addr, data} load (Mode-3 SPI).

        rstn / shdn are the active-low control bits (default 1 = normal).
        """
        self._send_words(cmd_dac_write(addr, data, rstn, shdn))

    def dac_reset(self, shdn: int = 1) -> None:
        """Hold the DAC in reset (drives dac_rstn low); performs no SPI transfer."""
        self._send_words(cmd_dac_reset(shdn))

    def writeback(self, payload: int = 0xADBEE) -> Optional[int]:
        """Send one writeback command (opcode 0xFF); return the echoed word.

        The perip_controller loops the exact command word back into the read
        FIFO, so the returned value should equal the command that was sent. The
        marker + opcode occupy the top 12 bits, so the echoable payload is the
        low 20 bits ([19:0]).
        """
        return self._loopback(make_command(OP_WRITEBACK, payload))

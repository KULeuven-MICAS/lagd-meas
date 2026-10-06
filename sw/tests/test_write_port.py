# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>
#
# Hardware-free tests for packed Xillybus writes.

import struct
import unittest
from unittest import mock

from sw.lib.port_driver import PortDriver
from sw.lib.write_port import WritePort


class TestWritePort(unittest.TestCase):

    def setUp(self):
        self.port = WritePort("unused", 32)
        self.port.portId = 123

    @mock.patch("sw.lib.write_port.os.write")
    def test_send_int_array_is_unsigned_little_endian(self, write):
        write.side_effect = lambda _fd, data: len(data)

        self.port.sendIntArray([0x01234567, 0x80000000, 0xFFFFFFFF])

        write.assert_called_once()
        self.assertEqual(
            bytes(write.call_args[0][1]),
            struct.pack("<III", 0x01234567, 0x80000000, 0xFFFFFFFF),
        )

    @mock.patch("sw.lib.write_port.os.write")
    def test_short_writes_send_the_complete_buffer(self, write):
        received = bytearray()

        def short_write(_fd, data):
            count = min(3, len(data))
            received.extend(bytes(data[:count]))
            return count

        write.side_effect = short_write
        self.port.sendIntArray([0x11223344, 0xAABBCCDD])

        self.assertGreater(write.call_count, 1)
        self.assertEqual(bytes(received), struct.pack("<II", 0x11223344, 0xAABBCCDD))
        self.assertEqual(self.port.getBytesLost(), 0)

    @mock.patch("sw.lib.write_port.os.write")
    def test_interrupted_write_is_retried(self, write):
        expected = struct.pack("<I", 0xCAFEF00D)
        calls = {"count": 0}

        def interrupted_once(_fd, data):
            calls["count"] += 1
            if calls["count"] == 1:
                raise InterruptedError()
            self.assertEqual(bytes(data), expected)
            return len(data)

        write.side_effect = interrupted_once
        self.port.sendInt(0xCAFEF00D)
        self.assertEqual(write.call_count, 2)

    @mock.patch("sw.lib.write_port.os.write", return_value=0)
    def test_zero_length_progress_is_an_error(self, _write):
        with self.assertRaises(OSError):
            self.port.sendInt(1)


class TestPortDriverBatching(unittest.TestCase):

    def test_send_words_uses_one_array_operation(self):
        driver = PortDriver.__new__(PortDriver)
        driver.wp = mock.Mock()
        words = [0xF0200002, 0x80000000, 0xDEADBEEF, 0xFFFFFFFF]

        driver._send_words(words)

        driver.wp.sendIntArray.assert_called_once_with(words)
        driver.wp.sendInt.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

import unittest
from unittest import mock

from sw.uart import send_uart


class RunElfWithFdTest(unittest.TestCase):
    @mock.patch("sw.uart.send_uart.wait_for_eoc", return_value=0)
    @mock.patch("sw.uart.send_uart.cmd_exec")
    @mock.patch("sw.uart.send_uart.cmd_read")
    @mock.patch("sw.uart.send_uart.cmd_write")
    @mock.patch("sw.uart.send_uart.handshake")
    @mock.patch("sw.uart.send_uart.parse_elf")
    def test_reuses_caller_owned_fd_for_complete_load(
        self,
        parse_elf,
        handshake,
        cmd_write,
        cmd_read,
        cmd_exec,
        wait_for_eoc,
    ):
        parse_elf.return_value = (
            0x80000000,
            [(0x80000000, b"abcdef")],
        )
        cmd_read.return_value = b"abcdef"

        result = send_uart.run_elf_with_fd(
            123,
            "program.elf",
            chunk_size=4,
            verify=True,
            timeout=3.0,
            run_timeout=7.0,
            connect_timeout=2.0,
        )

        self.assertEqual(result, 0)
        handshake.assert_called_once_with(123, 2.0)
        self.assertEqual(
            cmd_write.call_args_list,
            [
                mock.call(123, 0x80000000, b"abcd", 3.0),
                mock.call(123, 0x80000004, b"ef", 3.0),
            ],
        )
        cmd_read.assert_called_once_with(123, 0x80000000, 6, 3.0)
        cmd_exec.assert_called_once_with(123, 0x80000000, 3.0)
        wait_for_eoc.assert_called_once_with(123, 7.0)

    @mock.patch("sw.uart.send_uart.wait_for_eoc", return_value=3)
    @mock.patch("sw.uart.send_uart.cmd_exec")
    @mock.patch("sw.uart.send_uart.cmd_write")
    @mock.patch("sw.uart.send_uart.handshake")
    @mock.patch(
        "sw.uart.send_uart.parse_elf",
        return_value=(0x80000000, [(0x80000000, b"data")]),
    )
    def test_returns_application_eoc_code(
        self,
        parse_elf,
        handshake,
        cmd_write,
        cmd_exec,
        wait_for_eoc,
    ):
        result = send_uart.run_elf_with_fd(123, "program.elf")

        self.assertEqual(result, 3)


if __name__ == "__main__":
    unittest.main()

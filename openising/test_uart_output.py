import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from openising import uart_output


class UartOutputTest(unittest.TestCase):
    def test_print_uart_data_prefixes_complete_and_partial_lines(self):
        line = bytearray()
        output = io.StringIO()

        with redirect_stdout(output):
            uart_output._print_uart_data(b"Hello ", line)
            uart_output._print_uart_data(b"World!\r\nnext", line)

        self.assertEqual(output.getvalue(), "[chip] Hello World!\n")
        self.assertEqual(line, bytearray(b"next"))

    @mock.patch("openising.uart_output.time.monotonic", side_effect=[10.0, 10.3])
    @mock.patch(
        "openising.uart_output.select.select",
        side_effect=[([123], [], []), ([], [], [])],
    )
    @mock.patch("openising.uart_output.os.read", return_value=b"Hello World!\r\n")
    def test_stream_uart_drains_after_loader_exit(self, read, select, monotonic):
        process = mock.Mock()
        process.poll.side_effect = [None, 0, 0]
        process.wait.return_value = 0
        output = io.StringIO()

        with redirect_stdout(output):
            result = uart_output._stream_uart_while_loader_runs(123, process)

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "[chip] Hello World!\n")
        read.assert_called_once_with(123, 4096)
        process.wait.assert_called_once_with()

    @mock.patch("openising.uart_output._stream_uart_while_loader_runs", return_value=0)
    @mock.patch("openising.uart_output.subprocess.Popen")
    @mock.patch("openising.uart_output.open_port", return_value=123)
    @mock.patch("openising.uart_output.os.close")
    def test_spi_is_passive_uart_console(
        self,
        close,
        open_port,
        popen,
        stream_uart,
    ):
        process = popen.return_value

        result = uart_output.main([
            "--device", "/dev/test-uart",
            "--baud", "115200",
            "--timeout", "5",
            "-interface", "spi",
            "-elf", "program.elf",
        ])

        self.assertEqual(result, 0)
        open_port.assert_called_once_with("/dev/test-uart", 115200, False)
        popen.assert_called_once_with(
            [
                sys.executable,
                str(uart_output.TOP_MEAS / "sw/tests/chip_load_spi.py"),
                "program.elf",
                "--run-timeout",
                "5.0",
                "--sck",
                "12500000",
            ],
            stderr=subprocess.STDOUT,
        )
        stream_uart.assert_called_once_with(123, process)
        close.assert_called_once_with(123)

    @mock.patch("openising.uart_output.subprocess.Popen")
    @mock.patch("openising.uart_output._run_spi_batch", return_value=0)
    @mock.patch("openising.uart_output.open_port", return_value=123)
    @mock.patch("openising.uart_output.os.close")
    def test_spi_batch_reuses_one_remote_python(
        self,
        close,
        open_port,
        run_spi_batch,
        popen,
    ):
        result = uart_output.main([
            "--batch",
            "--device", "/dev/test-uart",
            "--baud", "115200",
            "--timeout", "5",
            "-interface", "spi",
            "-elf", "run_0.elf",
            "-elf", "run_1.elf",
        ])

        self.assertEqual(result, 0)
        open_port.assert_called_once_with("/dev/test-uart", 115200, False)
        run_spi_batch.assert_called_once_with(
            123,
            ["run_0.elf", "run_1.elf"],
            5.0,
        )
        popen.assert_not_called()
        close.assert_called_once_with(123)

    @mock.patch("sw.tests.chip_load_spi.run_elf_with_chip")
    @mock.patch("sw.tests.chip_load_spi.ChipDriver")
    @mock.patch("openising.uart_output._stream_uart_while_loader_runs", return_value=0)
    @mock.patch("openising.uart_output._ThreadProcess")
    def test_spi_batch_keeps_one_chip_driver_open(
        self,
        thread_process,
        stream_uart,
        chip_driver,
        run_elf_with_chip,
    ):
        chip = chip_driver.return_value.__enter__.return_value
        processes = [mock.Mock(), mock.Mock()]
        thread_process.side_effect = processes

        output = io.StringIO()
        with redirect_stdout(output):
            result = uart_output._run_spi_batch(
                123,
                ["run_0.elf", "run_1.elf"],
                5.0,
            )

        self.assertEqual(result, 0)
        chip_driver.assert_called_once()
        self.assertEqual(thread_process.call_count, 2)
        self.assertIs(thread_process.call_args_list[0].args[0], run_elf_with_chip)
        self.assertEqual(
            thread_process.call_args_list[0].kwargs["args"],
            (chip, "run_0.elf"),
        )
        self.assertEqual(
            thread_process.call_args_list[0].kwargs["kwargs"],
            {"sck_hz": 12_500_000, "run_timeout": 5.0},
        )
        self.assertEqual(
            thread_process.call_args_list[1].kwargs["kwargs"],
            {"sck_hz": None, "run_timeout": 5.0},
        )
        self.assertEqual(
            stream_uart.call_args_list,
            [mock.call(123, processes[0]), mock.call(123, processes[1])],
        )
        self.assertIn("[batch] RUN_START 0 run_0.elf", output.getvalue())
        self.assertIn("[batch] RUN_END 1 run_1.elf 0", output.getvalue())

    @mock.patch("sw.uart.send_uart.run_elf_with_fd", side_effect=[0, 0])
    @mock.patch("sw.lib.chip_driver.ChipDriver")
    def test_uart_batch_keeps_one_uart_and_chip_driver_open(
        self,
        chip_driver,
        run_elf_with_fd,
    ):
        chip = chip_driver.return_value.__enter__.return_value

        output = io.StringIO()
        with redirect_stdout(output):
            result = uart_output._run_uart_batch(
                123,
                ["run_0.elf", "run_1.elf"],
                5.0,
            )

        self.assertEqual(result, 0)
        chip_driver.assert_called_once_with(
            "/dev/xillybus_write_32",
            "/dev/xillybus_read_32",
        )
        self.assertEqual(
            chip.reset_chip.call_args_list,
            [
                mock.call(hold=0.01, chip_clk_en=1),
                mock.call(hold=0.01, chip_clk_en=1),
            ],
        )
        self.assertEqual(
            run_elf_with_fd.call_args_list,
            [
                mock.call(123, "run_0.elf", timeout=5.0),
                mock.call(123, "run_1.elf", timeout=5.0),
            ],
        )
        self.assertIn("[batch] RUN_START 0 run_0.elf", output.getvalue())
        self.assertIn("[batch] RUN_END 1 run_1.elf 0", output.getvalue())

    @mock.patch("openising.uart_output.Path.unlink")
    @mock.patch("openising.uart_output._stream_uart_while_loader_runs", return_value=0)
    @mock.patch("openising.uart_output.subprocess.Popen")
    @mock.patch("openising.uart_output.tempfile.NamedTemporaryFile")
    def test_jtag_batch_starts_openocd_once(
        self,
        named_temporary_file,
        popen,
        stream_uart,
        unlink,
    ):
        manifest = io.StringIO()
        manifest.name = "/tmp/jtag-manifest"
        named_temporary_file.return_value.__enter__.return_value = manifest
        process = popen.return_value

        result = uart_output._run_jtag_batch(
            123,
            ["run_0.elf", "run_1.elf"],
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            manifest.getvalue(),
            str(Path("run_0.elf").resolve()) + "\n"
            + str(Path("run_1.elf").resolve()) + "\n",
        )
        popen.assert_called_once_with(
            [
                "openocd",
                "-c",
                "set ELF_LIST_FILE /tmp/jtag-manifest",
                "-c",
                "set ADAPTER_KHZ 20000",
                "-f",
                str(uart_output.TOP_MEAS / "sw/jtag/openocd.run_batch.tcl"),
            ],
            stderr=subprocess.STDOUT,
        )
        stream_uart.assert_called_once_with(123, process)
        unlink.assert_called_once_with()

    @mock.patch("openising.uart_output._run_uart_batch", return_value=0)
    @mock.patch("openising.uart_output.open_port", return_value=123)
    @mock.patch("openising.uart_output.os.close")
    def test_main_routes_uart_batch(self, close, open_port, run_uart_batch):
        result = uart_output.main([
            "--batch",
            "-interface", "uart",
            "-elf", "run_0.elf",
            "-elf", "run_1.elf",
        ])

        self.assertEqual(result, 0)
        run_uart_batch.assert_called_once_with(
            123,
            ["run_0.elf", "run_1.elf"],
            uart_output.default_uart_timeout,
        )
        close.assert_called_once_with(123)

    @mock.patch("openising.uart_output._run_jtag_batch", return_value=0)
    @mock.patch("openising.uart_output.open_port", return_value=123)
    @mock.patch("openising.uart_output.os.close")
    def test_main_routes_jtag_batch(self, close, open_port, run_jtag_batch):
        result = uart_output.main([
            "--batch",
            "-interface", "jtag",
            "-elf", "run_0.elf",
            "-elf", "run_1.elf",
        ])

        self.assertEqual(result, 0)
        run_jtag_batch.assert_called_once_with(
            123,
            ["run_0.elf", "run_1.elf"],
        )
        close.assert_called_once_with(123)

    @mock.patch("openising.uart_output._stream_uart_while_loader_runs", return_value=0)
    @mock.patch("openising.uart_output.subprocess.Popen")
    @mock.patch("openising.uart_output.open_port", return_value=123)
    @mock.patch("openising.uart_output.os.close")
    def test_jtag_is_passive_uart_console(self, close, open_port, popen, stream_uart):
        process = popen.return_value

        result = uart_output.main([
            "--device", "/dev/test-uart",
            "--baud", "115200",
            "--timeout", "5",
            "-interface", "jtag",
            "-elf", "program.elf",
        ])

        self.assertEqual(result, 0)
        open_port.assert_called_once_with("/dev/test-uart", 115200, False)
        popen.assert_called_once_with(
            [
                str(uart_output.TOP_MEAS / "sw/jtag/run_elf.sh"),
                "program.elf",
                "-c",
                "set ADAPTER_KHZ 20000",
            ],
            stderr=subprocess.STDOUT,
        )
        stream_uart.assert_called_once_with(123, process)
        close.assert_called_once_with(123)

    @mock.patch("openising.uart_output._stream_uart_while_loader_runs", return_value=7)
    @mock.patch("openising.uart_output.subprocess.Popen")
    @mock.patch("openising.uart_output.open_port", return_value=123)
    @mock.patch("openising.uart_output.os.close")
    def test_loader_failure_is_propagated(self, close, open_port, popen, stream_uart):
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            uart_output.main(["-interface", "spi", "-elf", "program.elf"])

        self.assertEqual(raised.exception.returncode, 7)
        close.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()

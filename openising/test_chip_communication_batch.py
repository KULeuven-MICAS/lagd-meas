import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_communication


class ChipCommunicationBatchTest(unittest.TestCase):
    @mock.patch("chip_communication.subprocess.Popen")
    def test_batch_command_uses_one_ssh_and_repeated_elf_arguments(self, popen):
        batch_output = (
            "[batch] RUN_START 0 run_0.elf\n"
            "[chip] first\n"
            "[batch] RUN_END 0 run_0.elf 0 0.2\n"
            "[batch] RUN_START 1 run_1.elf\n"
            "[chip] second\n"
            "[batch] RUN_END 1 run_1.elf 0 0.3\n"
        )
        process = popen.return_value
        process.stdout = io.StringIO(batch_output)
        process.wait.return_value = 0
        batch_log = io.StringIO()
        terminal = io.StringIO()

        with redirect_stdout(terminal):
            chip_communication._stream_uart_output_batch(
                batch_log,
                "/dev/ttyUSB2",
                115200,
                5.0,
                ["run_0.elf", "run_1.elf"],
                rtscts=True,
                reset_chip=False,
            )

        command = popen.call_args.args[0]
        self.assertEqual(command.count("ssh"), 1)
        self.assertIn("-T", command)
        self.assertNotIn("-t", command)
        self.assertNotIn("python sw/tests/chip_test.py &&", command)
        self.assertNotIn(" &&", command)
        self.assertEqual(command.count("-elf"), 2)
        self.assertIn("--batch", command)
        self.assertEqual(command[-4:], ["-elf", "run_0.elf", "-elf", "run_1.elf"])
        self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.STDOUT)
        self.assertTrue(popen.call_args.kwargs["text"])
        self.assertEqual(batch_log.getvalue(), batch_output)
        self.assertIn("SPI batch", terminal.getvalue())
        self.assertIn("2/2", terminal.getvalue())
        self.assertNotIn("[####################]", terminal.getvalue())

    @mock.patch("chip_communication.subprocess.Popen")
    def test_batch_command_passes_selected_interface(self, popen):
        process = popen.return_value
        process.stdout = io.StringIO("")
        process.wait.return_value = 0
        for interface in ("spi", "uart", "jtag"):
            with self.subTest(interface=interface):
                with redirect_stdout(io.StringIO()):
                    chip_communication._stream_uart_output_batch(
                        io.StringIO(),
                        "/dev/ttyUSB2",
                        115200,
                        5.0,
                        ["program.elf"],
                        interface=interface,
                    )
                command = popen.call_args.args[0]
                interface_index = command.index("-interface")
                self.assertEqual(command[interface_index + 1], interface)

    @mock.patch("chip_communication.subprocess.Popen")
    def test_batch_failure_is_propagated_after_log_is_preserved(self, popen):
        process = popen.return_value
        process.stdout = io.StringIO(
            "[batch] RUN_START 0 run_0.elf\n"
            "loader failed\n"
            "[batch] RUN_ERROR 0 run_0.elf 1 0.1\n"
        )
        process.wait.return_value = 7
        batch_log = io.StringIO()

        with redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                chip_communication._stream_uart_output_batch(
                    batch_log,
                    "/dev/ttyUSB2",
                    115200,
                    5.0,
                    ["run_0.elf"],
                )

        self.assertEqual(raised.exception.returncode, 7)
        self.assertIn("loader failed", batch_log.getvalue())

    def test_split_batch_output_keeps_runs_separate(self):
        contents = """startup line
[batch] RUN_START 0 run_0.elf
loader zero
[chip] Energy FIFO data 0 for core 1: 0xffffffe3
[batch] RUN_END 0 run_0.elf 0
[batch] RUN_START 1 run_1.elf
loader one
[chip] Energy FIFO data 1 for core 1: 0xffffffe3
[batch] RUN_END 1 run_1.elf 0
"""
        with tempfile.TemporaryDirectory() as directory:
            batch_log = Path(directory) / "top_batch.log"
            batch_log.write_text(contents)
            runs = chip_communication._split_batch_output(batch_log, 2)

        self.assertEqual(
            runs,
            [
                ["loader zero\n", "[chip] Energy FIFO data 0 for core 1: 0xffffffe3\n"],
                ["loader one\n", "[chip] Energy FIFO data 1 for core 1: 0xffffffe3\n"],
            ],
        )

    def test_split_batch_output_rejects_incomplete_run(self):
        with tempfile.TemporaryDirectory() as directory:
            batch_log = Path(directory) / "top_batch.log"
            batch_log.write_text("[batch] RUN_START 0 run_0.elf\n")
            with self.assertRaisesRegex(RuntimeError, "before run 0 completed"):
                chip_communication._split_batch_output(batch_log, 1)

    @mock.patch("chip_communication.retrieve_data_from_output")
    @mock.patch("chip_communication._stream_uart_output_batch")
    @mock.patch("chip_communication.load_ans")
    def test_send_chip_uses_one_batch_for_all_run_folders(
        self,
        load_ans,
        stream_batch,
        retrieve_data,
    ):
        ans = mock.Mock()
        ans.config.problem_type = "Maxcut"
        ans.config.nb_flipping = 1
        ans.config.nb_runs = 4
        ans.ising_model.num_variables = 100
        load_ans.return_value = ans

        def write_batch(stdout, *args, **kwargs):
            stdout.write(
                "[batch] RUN_START 0 experiment/run_0/program.elf\n"
                "[chip] first run\n"
                "[batch] RUN_END 0 experiment/run_0/program.elf 0\n"
                "[batch] RUN_START 1 experiment/run_1/program.elf\n"
                "[chip] second run\n"
                "[batch] RUN_END 1 experiment/run_1/program.elf 0\n"
            )

        stream_batch.side_effect = write_batch

        with tempfile.TemporaryDirectory() as directory:
            top = Path(directory)
            data_folder = top / "experiment"
            (data_folder / "run_0").mkdir(parents=True)
            (data_folder / "run_1").mkdir()
            with mock.patch.object(chip_communication, "TOP_MEAS", top):
                terminal = io.StringIO()
                with redirect_stdout(terminal):
                    result = chip_communication.send_chip(
                        data_folder=data_folder,
                        interface="spi",
                        host="unused",
                        uart_device="/dev/ttyUSB2",
                        uart_baud=115200,
                        uart_timeout=5.0,
                        rtscts=True,
                        remote_dir="unused",
                        chip=2,
                        core=1,
                        smu_config_file=top / "smu.yaml",
                        nb_cores=1,
                        clock_speed=512e6,
                        delta_h_calculation=True,
                        reset_chip=False,
                    )
                final_log = (top / "top.log").read_text()

        self.assertEqual(result, 0)
        stream_batch.assert_called_once()
        elf_files = stream_batch.call_args.args[4]
        self.assertEqual(
            elf_files,
            [
                "experiment/run_0/lagd_commands_deltah.elf",
                "experiment/run_1/lagd_commands_deltah.elf",
            ],
        )
        self.assertEqual(retrieve_data.call_count, 2)
        self.assertEqual(final_log, "[chip] second run\n")
        self.assertNotIn("Run: ", terminal.getvalue())


if __name__ == "__main__":
    unittest.main()

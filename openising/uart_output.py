import argparse
import os
import sys
import subprocess

from sw.uart.send_uart import open_port, wait_for_eoc, ProtoError, handshake, parse_elf, cmd_exec
from openising import default_device, default_uart_baud, default_uart_timeout

def build_parser():
    parser = argparse.ArgumentParser(
            description="Open the UART port and wait for data to print out")
    parser.add_argument("-interface", help="Other interface with which to send all the data.", type=str)
    parser.add_argument("-elf", help="Elf file to send to chip", type=str)
    parser.add_argument(
            "--device", default=default_device,
            help=f"UART device on the measurement host (default: {default_device})",
        )
    parser.add_argument("-b", "--baud", type=int, default=default_uart_baud,
                        help=f"baud rate (default: {default_uart_baud} -- must match the chip)")
    parser.add_argument(
            "--rtscts", action="store_true",
            help="keep hardware flow control (by default --no-rtscts is passed to send_uart)",
        )
    parser.add_argument("--timeout", type=float, default=default_uart_timeout,
                        help=f"per-command response timeout in seconds (default: {default_uart_timeout})")
    return parser

def main(argv=None):
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    timeout = args.timeout
    fd = open_port(args.device, args.baud, args.rtscts)
    interface = args.interface
    elf_file = args.elf
    entry, _ = parse_elf(elf_file)
    try:
        handshake(fd, args.timeout)
        if interface == "jtag":
            subprocess.run(
                [ "sw/jtag/run_elf.sh",
                    f"{elf_file}",
                    "-c",
                    "set ADAPTER_KHZ 4000",
                ],
                stderr=subprocess.STDOUT,
                check=True,
            )
        elif interface == "spi":
            subprocess.run(
                ["python", "sw/tools/spi_program_loader.py", f"{elf_file}"],
                stderr=subprocess.STDOUT,
                check=True,
            )
        else:
            raise ValueError(f"interface {interface} is not supported.")
        cmd_exec(fd, entry, timeout)
        ret = wait_for_eoc(fd, timeout)
        print(f"[chip] EOC      : return code {ret}")
    except ProtoError as err:
        print(f"[chip] ERROR    : {err}")
        raise
    finally:
        os.close(fd)

if __name__ == "__main__":
    sys.exit(main())

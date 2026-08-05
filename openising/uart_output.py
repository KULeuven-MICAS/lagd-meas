import argparse
import os
import sys

from sw.uart.send_uart import open_port, wait_for_eoc, ProtoError
from target.zcu102.top import DEFAULT_DEVICE

def build_parser():
    parser = argparse.ArgumentParser(
            description="Open the UART port and wait for data to print out")
    parser.add_argument(
            "--device", default=DEFAULT_DEVICE,
            help=f"UART device on the measurement host (default: {DEFAULT_DEVICE})",
        )
    parser.add_argument("-b", "--baud", type=int, default=115200,
                        help="baud rate (default: 115200 -- must match the chip)")
    parser.add_argument(
            "--rtscts", action="store_true",
            help="keep hardware flow control (by default --no-rtscts is passed to send_uart)",
        )
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="per-command response timeout in seconds (default: 5)")
    return parser

def main(argv=None):
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    timeout = args.timeout
    fd = open_port(args.device, args.baud, args.rtscts)
    try:
        ret = wait_for_eoc(fd, timeout)
        print(f"[chip] EOC      : return code {ret}")
    except ProtoError as err:
        print(f"[chip] ERROR    : {err}")
        raise
    finally:
        os.close(fd)

if __name__ == "__main__":
    sys.exit(main())

import os
from pathlib import Path
from target.zcu102.top import DEFAULT_REMOTE_DIR, DEFAULT_HOST, DEFAULT_DEVICE

TOP_MEAS = Path(os.environ["TOP_MEAS"])
TOP_ISING = Path(os.environ["TOP_ISING"])
TOP_LAGD_IM = Path(os.environ["TOP_LAGD_IM"])
os.environ["TOP"] = str(TOP_ISING)

default_remote_dir = DEFAULT_REMOTE_DIR
default_host = DEFAULT_HOST
default_device = DEFAULT_DEVICE
default_uart_baud = 115200
default_uart_timeout = 5.0


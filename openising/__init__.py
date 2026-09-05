import os
from pathlib import Path
import lab_config

TOP_MEAS = Path(os.environ["TOP_MEAS"])
TOP_ISING = Path(os.environ["TOP_ISING"])
TOP_LAGD_IM = Path(os.environ["TOP_LAGD_IM"])
os.environ["TOP"] = str(TOP_ISING)

default_remote_dir = lab_config.get("measurement-host", "remote_dir")
default_host = lab_config.get("measurement-host", "host")
default_device = lab_config.get("measurement-host", "device")
remote_python = lab_config.get("measurement-host", "python")
default_uart_baud = 115200
default_uart_timeout = 5.0
connect_to_host_commands = ["ssh", "-t", default_host, f"cd {default_remote_dir} &&", "source env.sh &&"]

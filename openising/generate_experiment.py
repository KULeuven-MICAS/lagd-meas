import argparse
import yaml
import logging

from __init__ import TOP_ISING, TOP_MEAS
from submodules.openising.ising.api import get_hamiltonian_energy
from openising.save_model import store_run
from openising.mppi_experiment import mppi_experiment
from chip_communication import compile_data, send_chip
from submodules.openising.ising.stages.simulation_stage import Ans
from openising import default_remote_dir, default_host, default_device, default_uart_baud, default_uart_timeout

parser = argparse.ArgumentParser()
parser.add_argument(
    "-config-file",
    help="directory to yaml file for experiment.",
    type=str,
    default="openising/Maxcut_experiment/model_0",
)
parser.add_argument("--logging-level", help="level of logging. Defaults to INFO", default=logging.INFO)
parser.add_argument(
    "--simulate",
    help="whether to simulate the data and compile or not simulate and send to chip",
    action=argparse.BooleanOptionalAction,
)
parser.add_argument("--nb-cores", help="The amount of cores to use on chip", type=int, default=1)
parser.add_argument("--interface", help="The interface to send the data with", type=str, default="uart")
parser.add_argument(
    "-host",
    "--host",
    default=default_host,
    help=f"measurement host, user@ip (default: {default_host})",
)
parser.add_argument(
    "-b",
    "--baud",
    help=f"baud rate to send/receive data. Must match the chip (default {default_uart_baud} baud)",
    default=default_uart_baud,
)
parser.add_argument("-d", "--device", default=default_device, help=f"serial device (default: {default_device})")
parser.add_argument(
    "--remote-dir",
    default=default_remote_dir,
    help=f"repo directory on the measurement host (default: {default_remote_dir})",
)
parser.add_argument(
    "--timeout",
    type=float,
    default=default_uart_timeout,
    help=f"per-command response timeout in seconds (default: {default_uart_timeout})",
)
args = parser.parse_args()

# Load base and experiment config files and store them in the correct folder in openising
base_config_dir = TOP_MEAS / "openising/base_experiment.yaml"
experiment_config_dir = TOP_MEAS / args.config_file / "config_experiment.yaml"

with base_config_dir.open("r") as f:
    base_config = yaml.safe_load(f)
with experiment_config_dir.open("r") as f:
    experiment_config = yaml.safe_load(f)

experiment_config.update(base_config)
experiment_config["benchmark"] = str(TOP_MEAS / args.config_file / "benchmark.yaml")
save_folder = TOP_MEAS / args.config_file
# ensure the amount of runs is even
if experiment_config["nb_runs"] % 2 != 0:
    experiment_config["nb_runs"] *= 2
config_path = "./ising/inputs/config/config_experiment.yaml"
openising_config = TOP_ISING / config_path

with openising_config.open("w") as f:
    yaml.safe_dump(experiment_config, f)
problem_type = experiment_config["problem_type"]
# Start openising run
if problem_type != "MPPI":
    if args.simulate:
        if not (save_folder / "ans.pkl").exists():
            ans, _ = get_hamiltonian_energy(problem_type, config_path, args.logging_level)
            # Store everything
            ans.save(save_folder / "ans.pkl")
        else:
            ans = Ans()
            ans.load(save_folder / "ans.pkl")
        data_folders = store_run(ans, save_folder, problem_type)
        # compile everything
        compile_data(data_folders, args.nb_cores)
    else:
        send_chip(
            data_folder=save_folder,
            nb_cores=args.nb_cores,
            interface=args.interface,
            host=args.host,
            uart_device=args.device,
            uart_baud=args.baud,
            uart_timeout=args.timeout,
            remote_dir=args.remote_dir,
        )
else:
    mppi_experiment(config_path, save_folder, args.interface, args.host)

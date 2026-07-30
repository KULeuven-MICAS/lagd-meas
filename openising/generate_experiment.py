import argparse
import yaml
import logging
from __init__ import toppath, current_dir

from ising.api import get_hamiltonian_energy
from save_model import store_run
from mppi_experiment import mppi_experiment
from chip_communication import compile_data, send_chip
from ising.stages.simulation_stage import Ans

DEFAULT_HOST = "root@10.88.18.26"

parser = argparse.ArgumentParser()
parser.add_argument(
    "-config-file", help="directory to yaml file for experiment.", type=str, default="Maxcut_experiment/model_0"
)
parser.add_argument("--logging-level", help="level of logging. Defaults to INFO", default=logging.INFO)
parser.add_argument(
    "--simulate",
    help="whether to simulate the data and compile or not simulate and send to chip",
    action=argparse.BooleanOptionalAction
)
parser.add_argument("--nb-cores", help="The amount of cores to use on chip", type=int, default=1)
parser.add_argument("--interface", help="The interface to send the data with", type=str, default="uart")
parser.add_argument("--send-to-chip", default=False, type=bool)
parser.add_argument("-host", "--host", default=DEFAULT_HOST,
        help=f"measurement host, user@ip (default: {DEFAULT_HOST})",)
args = parser.parse_args()

# Load base and experiment config files and store them in the correct folder in openising
base_config_dir = current_dir / "base_experiment.yaml"
experiment_config_dir = current_dir / args.config_file / "config_experiment.yaml"

with base_config_dir.open("r") as f:
    base_config = yaml.safe_load(f)
with experiment_config_dir.open("r") as f:
    experiment_config = yaml.safe_load(f)

experiment_config.update(base_config)
experiment_config["benchmark"] = str(current_dir / args.config_file / "benchmark.yaml")
save_folder = current_dir / args.config_file
# ensure the amount of runs is even
if experiment_config["nb_runs"] % 2 != 0:
    experiment_config["nb_runs"] *= 2
config_path = "./ising/inputs/config/config_experiment.yaml"
openising_config = toppath / config_path

with openising_config.open("w") as f:
    yaml.safe_dump(experiment_config, f)
problem_type = experiment_config["problem_type"]
# Start openising run
if problem_type != "MPPI":
    if args.simulate:
        if not (save_folder/"ans.pkl").exists():
            ans, _ = get_hamiltonian_energy(problem_type, config_path, args.logging_level)
            # Store everything
            ans.save(save_folder / "ans.pkl")
        else:
            ans = Ans()
            ans.load(save_folder/"ans.pkl")
        data_folders = store_run(ans, save_folder, problem_type)
        # compile everything
        compile_data(data_folders, args.nb_cores)
    else:
        send_chip(save_folder, args.nb_cores, args.interface, args.send_to_chip, args.host)
else:
    mppi_experiment(config_path, save_folder, args.interface, args.send_to_chip, args.host)

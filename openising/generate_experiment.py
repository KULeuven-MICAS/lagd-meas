import argparse
import yaml
import logging
from __init__ import toppath, current_dir

from ising.api import get_hamiltonian_energy
from save_model import store_run
from mppi_experiment import mppi_experiment
from send_chip import compile_data

parser = argparse.ArgumentParser()
parser.add_argument(
    "-config_file", help="directory to yaml file for experiment.", type=str, default="MIMO_experiment/model_0"
)
parser.add_argument("--logging_level", help="level of logging. Defaults to INFO", default=logging.INFO)

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
if experiment_config["nb_runs"] % 2!=0:
    experiment_config["nb_runs"] *= 2
config_path = "./ising/inputs/config/config_experiment.yaml"
openising_config = toppath / config_path

with openising_config.open("w") as f:
    yaml.safe_dump(experiment_config, f)
problem_type = experiment_config["problem_type"]
# Start openising run
if problem_type != "MPPI":
    ans, _ = get_hamiltonian_energy(problem_type, config_path, args.logging_level)
    # Store everything
    ans.save(save_folder / "ans.pkl")
    data_folders = store_run(ans, save_folder, problem_type)
    # compile everything
    compile_data(data_folders, 2)
else:
    mppi_experiment(config_path, save_folder)

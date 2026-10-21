# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

import argparse
import yaml
import logging
from pathlib import Path

from openising import (
    TOP_ISING,
    TOP_MEAS,
    default_remote_dir,
    default_host,
    default_device,
    default_uart_baud,
    default_uart_timeout,
)
from copy import deepcopy
from openising.Annealing_experiments.annealing_comparison import annealing_comparison
from openising.save_model import store_run
from openising.chip_communication import compile_data, send_chip

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
parser.add_argument("--core", help="which core to use on chip", type=int, default=1)
parser.add_argument("--interface", help="The interface to send the data with", type=str, default="uart")
parser.add_argument("--plot-sw", help="Plot software simulation of the MPC run", action=argparse.BooleanOptionalAction)
parser.add_argument("-chip", help="which chip we are using to send the data to", default=1, type=int)
parser.add_argument(
    "--no-rtscts",
    action=argparse.BooleanOptionalAction,
)
parser.add_argument(
    "--smu-config", help="config file for the smu", default="sw/lib/lab_instruments/config/meas_setup.yaml"
)
parser.add_argument("--test", action=argparse.BooleanOptionalAction, default=False)
parser.add_argument("--clock-speed", help="The speed of the clock", type=float, default=512e6)
parser.add_argument("--no_delta_h_calculation", action=argparse.BooleanOptionalAction, default=False)
args = parser.parse_args()

# Load base and experiment config files and store them in the correct folder in openising
base_config_dir = TOP_MEAS / "openising/base_experiment.yaml"
experiment_config_dir = TOP_MEAS / args.config_file / "config_experiment.yaml"

with base_config_dir.open("r") as f:
    base_config = yaml.safe_load(f)
with experiment_config_dir.open("r") as f:
    experiment_config = yaml.safe_load(f)

experiment_config.update(base_config)
problem_type = experiment_config["problem_type"]
if problem_type == "MPPI":
    experiment_config["benchmark"] = str(TOP_MEAS / args.config_file / "benchmark.yaml")
save_folder = TOP_MEAS / args.config_file
# ensure the amount of runs is even
if experiment_config["nb_runs"] % 2 != 0:
    experiment_config["nb_runs"] *= 2
config_path = "./ising/inputs/config/config_experiment.yaml"
openising_config = TOP_ISING / config_path

# Start openising run
benchmarks: list[str] = experiment_config["benchmark"]
for benchmark in benchmarks:
    benchmark_name = benchmark.split("/")[-1].split(".")[0]
    benchmark_folder: Path = save_folder / benchmark_name
    if not benchmark_folder.exists():
        benchmark_folder.mkdir(parents=True, exist_ok=True)

if args.simulate:
    exponents = experiment_config["exponent"]
    annealing_config = deepcopy(experiment_config)
    galena_config = deepcopy(experiment_config)
    galena_path = TOP_ISING / "./ising/inputs/config/config_galena.yaml"
    annealing_path = TOP_ISING / "./ising/inputs/config/config_annealing.yaml"
    for exponent in exponents:
        annealing_config["exponent"] = exponent
        galena_config["exponent"] = exponent
        galena_runs, annealing_runs = annealing_comparison(
            benchmarks,
            experiment_config,
            galena_path,
            galena_config,
            annealing_path,
            annealing_config,
            experiment_config["bestx"],
            save_folder,
        )
        for ans, folder in galena_runs.values():
            data_folders = store_run(ans, folder, problem_type)
            # compile everything

            compile_data(
                data_folders, args.nb_cores, core=args.core, delta_h_calculation=not args.no_delta_h_calculation
            )
        for runs in annealing_runs.values():
            for ans, folder in runs.values():
                data_folders = store_run(ans, folder, problem_type)
                compile_data(
                    data_folders, args.nb_cores, core=args.core, delta_h_calculation=not args.no_delta_h_calculation
                )

else:
    for benchmark in benchmarks:
        benchmark_folder = save_folder / benchmark.split("/")[-1].split["."][0]
        for child in benchmark_folder.iterdir():
            send_chip(
                data_folder=child,
                interface=args.interface,
                host=default_host,
                uart_device=default_device,
                uart_baud=default_uart_baud,
                uart_timeout=default_uart_timeout,
                rtscts=(not args.no_rtscts),
                remote_dir=default_remote_dir,
                chip=args.chip,
                core=args.core,
                smu_config_file=TOP_MEAS / args.smu_config,
                nb_cores=args.nb_cores,
                clock_speed=args.clock_speed,
                delta_h_calculation=not args.no_delta_h_calculation,
            )

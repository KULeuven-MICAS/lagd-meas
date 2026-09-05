# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

import argparse
import yaml
import logging

from __init__ import (
    TOP_ISING,
    TOP_MEAS,
    default_remote_dir,
    default_host,
    default_device,
    default_uart_baud,
    default_uart_timeout,
)
from openising.tests import run_test
from submodules.openising.ising.api import get_hamiltonian_energy
from openising.save_model import store_run
from openising.mppi_experiment import mppi_experiment
from chip_communication import compile_data, send_chip, compile_data_convergence, send_chip_convergence
from submodules.openising.ising.stages.simulation_stage import Ans

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
parser.add_argument(
    "--convergence-mode",
    help="compile the runs, such that the iteration count increases by one iteration each time",
    action=argparse.BooleanOptionalAction,
)
parser.add_argument("-chip", help="which chip we are using to send the data to", default=1, type=int)
parser.add_argument(
    "--no-rtscts",
    action=argparse.BooleanOptionalAction,
)
parser.add_argument(
    "--smu-config", help="config file for the smu", default="sw/lib/lab_instruments/config/meas_setup.yaml"
)
parser.add_argument("--test", action=argparse.BooleanOptionalAction, default=False)
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

with openising_config.open("w") as f:
    yaml.safe_dump(experiment_config, f)

# Start openising run
if problem_type != "MPPI":
    if args.simulate:
        if not (save_folder / "ans.pkl").exists():
            if not args.test:
                ans, _ = get_hamiltonian_energy(problem_type, config_path, args.logging_level)
            else:
                ans, _ = run_test(config_path)
            # Store everything
            ans.save(save_folder / "ans.pkl")
        else:
            if args.test:
                ans, _ = run_test(config_path)
                ans.save(save_folder / "ans.pkl")
            else:
                ans = Ans()
                ans.load(save_folder / "ans.pkl")
        data_folders = store_run(ans, save_folder, problem_type)
        # compile everything
        if args.convergence_mode:
            compile_data_convergence(data_folders=data_folders, nb_iteration=ans.config.nb_flipping, core=args.core)
        else:
            compile_data(data_folders, args.nb_cores, core=args.core)
    else:
        if args.convergence_mode:
            send_chip_convergence(
                save_folder,
                args.interface,
                default_host,
                default_device,
                default_uart_baud,
                default_uart_timeout,
                default_remote_dir,
                args.chip,
                core=args.core,
                smu_config_file=TOP_MEAS/args.smu_config,
                rtscts=(not args.no_rtscts),
            )
        else:
            send_chip(
                data_folder=save_folder,
                interface=args.interface,
                host=default_host,
                uart_device=default_device,
                uart_baud=default_uart_baud,
                uart_timeout=default_uart_timeout,
                rtscts=(not args.no_rtscts),
                remote_dir=default_remote_dir,
                chip=args.chip,
                core=args.core,
                smu_config_file=TOP_MEAS/args.smu_config,
                nb_cores=args.nb_cores,
            )
else:
    mppi_experiment(
        config_path,
        save_folder,
        args.interface,
        args.host,
        args.device,
        args.baud,
        args.timeout,
        args.remote_dir,
        args.plot_sw,
    )

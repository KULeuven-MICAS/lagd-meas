# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

"""Galena (best of x single-iteration runs) versus annealing (x flipping iterations) on chip.

The experiment folder holds a config_experiment.yaml. Optionally, one annealing parameter is swept by setting
`sweep_parameter` (e.g. exponent or init_cluster_size) and `sweep_values`. The data is stored as:
    <experiment>/<benchmark>/galena/run_<i>
    <experiment>/<benchmark>/[<sweep_parameter>_<value>/]annealing_<x>/run_<i>
"""

import argparse
import logging

from openising import (
    TOP_ISING,
    TOP_MEAS,
    default_remote_dir,
    default_host,
    default_device,
    default_uart_baud,
    default_uart_timeout,
)
from openising.Annealing_experiments.annealing_comparison import (
    annealing_config,
    annealing_folder,
    galena_config,
    galena_folder,
    is_compiled,
    is_measured,
    load_experiment_config,
    simulate_run,
    sweep_points,
)
from openising.save_model import store_run
from openising.chip_communication import compile_data, send_chip

parser = argparse.ArgumentParser()
parser.add_argument(
    "-config-file",
    help="directory to yaml file for experiment.",
    type=str,
    default="openising/Annealing_experiments/Maxcut",
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
parser.add_argument("-chip", help="which chip we are using to send the data to", default=1, type=int)
parser.add_argument(
    "--no-rtscts",
    action=argparse.BooleanOptionalAction,
)
parser.add_argument(
    "--smu-config", help="config file for the smu", default="sw/lib/lab_instruments/config/meas_setup.yaml"
)
parser.add_argument("--clock-speed", help="The speed of the clock", type=float, default=512e6)
parser.add_argument("--no_delta_h_calculation", action=argparse.BooleanOptionalAction, default=False)
args = parser.parse_args()
logging.basicConfig(level=args.logging_level)
delta_h_calculation = not args.no_delta_h_calculation

config, save_folder = load_experiment_config(args.config_file)
problem_type = config["problem_type"]
benchmarks: list[str] = config["benchmark"]
bestx: list[int] = config["bestx"]
sweep_parameter = config.get("sweep_parameter")

discrimination = ""
if "exponent" in args.config_file:
    discrimination = "exponent_"
elif "size" in args.config_file:
    discrimination = "size_"

galena_path = TOP_ISING / f"./ising/inputs/config/config_galena_{discrimination}{problem_type}.yaml"
annealing_path = TOP_ISING / f"./ising/inputs/config/config_annealing_{discrimination}{problem_type}.yaml"

# Every (benchmark, sweep value, x) combination with its run config, Galena once per benchmark.
experiments = []
for benchmark in benchmarks:
    experiments.append(
        (galena_config(config, benchmark), galena_path, galena_folder(save_folder, benchmark))
    )
    for sweep_value in sweep_points(config):
        for x in bestx:
            experiments.append(
                (
                    annealing_config(config, benchmark, x, sweep_parameter, sweep_value),
                    annealing_path,
                    annealing_folder(save_folder, benchmark, x, sweep_parameter, sweep_value),
                )
            )

for run_config, config_path, folder in experiments:
    if args.simulate:
        ans = simulate_run(run_config, config_path, folder, problem_type, args.logging_level)
        if is_compiled(folder, run_config["nb_runs"], delta_h_calculation):
            logging.info(f"{folder.relative_to(TOP_MEAS)} is already compiled, skipping.")
            continue
        data_folders = store_run(ans, folder, problem_type)
        compile_data(data_folders, args.nb_cores, core=args.core, delta_h_calculation=delta_h_calculation)
    else:
        if is_measured(folder, run_config["nb_runs"], delta_h_calculation):
            logging.info(f"{folder.relative_to(TOP_MEAS)} is already measured, skipping.")
            continue
        send_chip(
            data_folder=folder,
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
            delta_h_calculation=delta_h_calculation,
        )

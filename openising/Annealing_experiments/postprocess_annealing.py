# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

"""Plot the measured Galena versus annealing comparison. The figures and summaries are stored in
<experiment>/figures."""

import argparse
import logging

from openising.Annealing_experiments.annealing_comparison import (
    annealing_folder,
    galena_folder,
    load_experiment_config,
    sweep_points,
)
from openising.Annealing_experiments.plotter import plot_comparison, write_summary

parser = argparse.ArgumentParser()
parser.add_argument(
    "-config-file",
    help="directory to yaml file for experiment.",
    type=str,
    default="openising/Annealing_experiments/Maxcut",
)
parser.add_argument("--no_delta_h_calculation", action=argparse.BooleanOptionalAction, default=False)
args = parser.parse_args()
logging.basicConfig(level=logging.INFO)

config, save_folder = load_experiment_config(args.config_file)
delta_h_calculation = not args.no_delta_h_calculation
benchmarks: list[str] = config["benchmark"]
bestx: list[int] = config["bestx"]
sweep_parameter = config.get("sweep_parameter")
figtop = save_folder / "figures"
figtop.mkdir(parents=True, exist_ok=True)

galena_runs = {
    index: (benchmark, galena_folder(save_folder, benchmark)) for index, benchmark in enumerate(benchmarks)
}
for sweep_value in sweep_points(config):
    annealing_runs = {
        index: {
            x: (benchmark, annealing_folder(save_folder, benchmark, x, sweep_parameter, sweep_value)) for x in bestx
        }
        for index, benchmark in enumerate(benchmarks)
    }
    sweep_str = "" if sweep_parameter is None else f"_{sweep_parameter}_{sweep_value}"
    plot_comparison(
        galena_runs,
        annealing_runs,
        bestx,
        figtop,
        f"galena_vs_annealing{sweep_str}",
        delta_h_calculation=delta_h_calculation,
    )
    write_summary(
        galena_runs,
        annealing_runs,
        bestx,
        figtop / f"summary_comparison{sweep_str}.csv",
        relative=True,
        delta_h_calculation=delta_h_calculation,
    )

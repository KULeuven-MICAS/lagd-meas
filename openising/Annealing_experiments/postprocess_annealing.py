# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

"""Plot the measured Galena versus annealing comparison, next to the software simulation of the same quantized
models. The figures and summaries are stored in <experiment>/figures."""

import argparse
import logging
from pathlib import Path

import numpy as np

from openising.Annealing_experiments.annealing_comparison import (
    annealing_folder,
    galena_folder,
    load_experiment_config,
    sweep_points,
)
from openising.Annealing_experiments.plotter import plot_comparison, write_summary
from openising.postprocessing import load_ans
from submodules.openising.ising.stages.simulation_stage import Ans

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


def hw_run(folder: Path, solvers: list[str], delta_h_calculation: bool) -> Ans:
    """Evaluate the measured final states on the original model, like the software simulation does."""
    ans = load_ans(folder)
    delta_h_str = "_deltah" * int(delta_h_calculation)
    energies = []
    for run in range(ans.config.nb_runs // 2):
        for i in range(2):
            state = np.loadtxt(folder / f"run_{run}" / f"hw_final_state_{i + 1}{delta_h_str}")
            energies.append(ans.ising_model.evaluate(state.astype(np.float32)))
    return Ans(energies={solver: energies for solver in solvers}, best_found=ans.best_found, benchmark=ans.benchmark)


config, save_folder = load_experiment_config(args.config_file)
delta_h_calculation = not args.no_delta_h_calculation
benchmarks: list[str] = config["benchmark"]
bestx: list[int] = config["bestx"]
solvers: list[str] = config["solvers"]
sweep_parameter = config.get("sweep_parameter")
figtop = save_folder / "figures"
figtop.mkdir(parents=True, exist_ok=True)

hw_galena = {
    benchmark: hw_run(galena_folder(save_folder, benchmark), solvers, delta_h_calculation) for benchmark in benchmarks
}
sw_galena = {benchmark: load_ans(galena_folder(save_folder, benchmark)) for benchmark in benchmarks}
for sweep_value in sweep_points(config):
    folders = {
        benchmark: {x: annealing_folder(save_folder, benchmark, x, sweep_parameter, sweep_value) for x in bestx}
        for benchmark in benchmarks
    }
    hw_annealing = {
        benchmark: {x: hw_run(folder, solvers, delta_h_calculation) for x, folder in runs.items()}
        for benchmark, runs in folders.items()
    }
    sw_annealing = {
        benchmark: {x: load_ans(folder) for x, folder in runs.items()} for benchmark, runs in folders.items()
    }
    sweep_str = "" if sweep_parameter is None else f"{sweep_parameter}_{sweep_value}_"
    for source, galena_runs, annealing_runs in (("hw", hw_galena, hw_annealing), ("sw", sw_galena, sw_annealing)):
        for solver in solvers:
            plot_comparison(
                galena_runs, annealing_runs, bestx, solver, figtop, f"{source}_galena_vs_annealing_{sweep_str}"
            )
            write_summary(
                galena_runs,
                annealing_runs,
                bestx,
                figtop / f"{source}_summary_comparison_{sweep_str}{solver}.csv",
                [solver],
                True,
            )

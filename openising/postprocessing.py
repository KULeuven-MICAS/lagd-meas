# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from submodules.openising.ising.stages.model.MPPI.environment import create_environment, plot_environment
from submodules.openising.ising.stages.model import IsingModel
from submodules.openising.ising.stages.simulation_stage import Ans
from submodules.openising.ising.utils.HDF5Logger import return_data
from submodules.openising.ising.postprocessing.summarize_energies import relative_to_best_found


def plot_convergence_run(data_folder: Path, add_sw: bool = True, figname: str = "energy_convergence"):
    """Plots the convergence of one run folder.

    @type data_folder: Path
    @param data_folder: the folder where the run is stored
    @type add_sw: bool, optional
    @param add_sw: Whether to add the software simulation to the plot. Defaults to True.
    @type figname: str, optional
    @param figname: What to call the figure. Defaults to "energy_convergence".
    """
    ans = load_ans(data_folder.parent)
    is_MIMO = ans.config.problem_type == "MIMO"
    model: IsingModel = ans.ising_model
    nb_runs = 2
    for run in range(nb_runs):
        energy_hw = np.loadtxt(data_folder / f"hw_best_energy_{run + 1}", dtype=float)
        energy_hw += model.c

        plt.figure()
        plt.plot(energy_hw, label=f"Chip: best={energy_hw[-1]}")
        if add_sw:
            actual_run = str(data_folder).split("/")[-1][-1]
            if is_MIMO:
                logfile = ans.MIMO[actual_run].logfiles[run]
            else:
                logfile = ans.logfiles[actual_run + run]
            energy_sw = return_data(logfile, "energy_best")[1:]
            plt.plot(energy_sw, label=f"Simulation: best={energy_sw[-1]}")
        plt.xlabel("Iteration")
        plt.ylabel("Hamiltonian energy")
        plt.legend()
        plt.savefig(data_folder / f"{figname}_run{run + 1}.pdf")
        plt.close()


def plot_BER(data_folders: list[Path], figname: str = "ber_curve", add_sw: bool = True):
    """Plots the BER curve comprised of many model folders.

    @type data_folders: list[Path]
    @param data_folders: a list of all the model folders with each model a different SNR value.
    @type figname: str, optional
    @param figname: The name of the figure. Defaults to "ber_curve".
    @type add_sw: bool, optional
    @param add_sw: Whether to add the software simulation or not. Defaults to True.
    """
    snr_ber_points = dict()
    snr_ber_points_zf = dict()
    snr_ber_points_sw = dict()
    for model_folder in data_folders:
        ans = load_ans(model_folder)
        if snr_ber_points.get(ans.SNR) is None:
            snr_ber_points[ans.SNR] = []
        N = np.shape(ans.x_tilde)[0]
        if ans.config.dummy_qam == 2:
            r = 1
        else:
            if ans.config.is_hamming_encoding:  # with hamming encoding
                r = int(np.sqrt(ans.config.dummy_qam) - 1)
            else:  # with binary encoding
                r = int(np.ceil(np.log2(np.sqrt(ans.config.dummy_qam))))
        if ans.config.is_hamming_encoding:  # with hamming encoding
            T = np.block([[np.eye(N) for _ in range(r)]])
        else:  # with binary encoding
            T = np.block([[2 ** (r - i) * np.eye(N) for i in range(1, r + 1)]])
        nb_trials = len(ans.MIMO)
        differences = np.zeros((N, nb_trials))
        for trial in range(nb_trials):
            lowest_id = 0
            lowest_en = np.inf
            for run in range(2):
                en = np.loadtxt(data_folders / f"run_{trial}/hw_best_energy_{run + 1}")[-1]
                if en < lowest_en:
                    lowest_id = run
                    lowest_en = en
            state = np.loadtxt(data_folders / f"run_{trial}/hw_final_state_{lowest_id + 1}")
            differences[:, trial] = compute_difference(state, T, r, ans.x_tilde[trial, :], ans.config.dummy_qam, N)
        array_mid = differences.shape[0] // 2
        diff_real_half = differences[0:array_mid, :]
        diff_imag_half = differences[array_mid:, :]
        diff_of_users = np.hstack((diff_real_half, diff_imag_half))
        snr_ber_points[ans.SNR].append(
            np.mean(np.sum(np.abs(diff_of_users) / 2, axis=1) / (np.log2(ans.config.dummy_qam) * nb_trials))
        )
        snr_ber_points_zf[ans.SNR] = ans.BER["ZF"]
        if add_sw:
            snr_ber_points_sw[ans.SNR] = ans.BER["Multiplicative"]

    snr_values = list(snr_ber_points.keys())
    plt.figure()
    plt.semilogy(snr_values, list(snr_ber_points.values()), label="Chip Measurements")
    plt.semilogy(snr_values, list(snr_ber_points_zf.values()), color="k", linestyle="--", label="Zero Forcing")
    if add_sw:
        plt.semilogy(snr_values, list(snr_ber_points_sw.values()), label="Simulation")
    plt.legend()
    plt.grid(which="major", axis="y", linestyle="--", color="grey")
    plt.xlabel("SNR [dB]")
    plt.ylabel("BER")
    plt.savefig(data_folders[0].parent / f"{figname}.pdf", bbox_inches="tight")
    plt.close()


def plot_convergence_multi(data_folder: Path, add_sw: bool = True, figname: str = "energy_convergence_all"):
    ans = load_ans(data_folder)
    is_MIMO = ans.config.problem_type == "MIMO"
    if is_MIMO:
        nb_runs = ans.config.dummy_case_num
    else:
        nb_runs = int(ans.config.nb_runs / 2)
    num_iterations = ans.config.nb_flipping
    energies = np.zeros((2 * nb_runs, num_iterations))
    energies_sw = np.zeros_like(energies)
    for run in range(nb_runs):
        run_folder = data_folder / f"run_{run}"
        if is_MIMO:
            model = ans.MIMO[run].ising_model
        else:
            model = ans.ising_model
        energy_hw1 = np.loadtxt(run_folder / f"hw_best_energy_{run + 1}", dtype=float)
        energy_hw2 = np.loadtxt(run_folder / f"hw_best_energy_{run + 2}", dtype=float)
        energies[2 * run, :] = energy_hw1
        energies[2 * run + 1, :] = energy_hw2
        energies[2 * run : 2 * run + 2, :] += model.c
        if add_sw:
            if is_MIMO:
                logfile1 = ans.MIMO[run].logfiles[0]
                logfile2 = ans.MIMO[run].logfiles[1]
            else:
                logfile1 = ans.logfiles[2 * run]
                logfile2 = ans.logfiles[2 * run + 1]
            energies_sw[2 * run, :] = return_data(logfile1, "energy_best")[1:]
            energies_sw[2 * run + 1, :] = return_data(logfile2, "energy_best")[1:]
    energies_mean = np.mean(energies, axis=0)
    energies_std = np.std(energies, axis=0)
    plt.figure()
    plt.plot(energies_mean, label=f"Chip measurement: best= {energies_mean[-1]}")
    plt.fill_between(list(range(num_iterations)), energies_mean - energies_std, energies_mean + energies_std, alpha=0.2)
    if add_sw:
        energies_mean = np.mean(energies_sw, axis=0)
        energies_std = np.std(energies_sw, axis=0)
        plt.plot(energies_mean, linestyle="--", label=f"Simulation: best = {energies_mean[-1]}")
        plt.fill_between(
            list(range(num_iterations)), energies_mean - energies_std, energies_mean + energies_std, alpha=0.2
        )
    plt.xlabel("Iteration")
    plt.ylabel("Hamiltonian Energy")
    plt.savefig(data_folder / f"{figname}.pdf", bbox_inches="tight")
    plt.close()


def boxplot(data_folders: list[Path], add_sw: bool = True, figname: str = "boxplot"):
    """Makes a boxplot for every model folder in the data_folders list.

    Args:
        data_folders (list[Path]): _description_
        add_sw (bool, optional): _description_. Defaults to True.
        figname (str, optional): _description_. Defaults to "boxplot".
    """
    # TODO
    final_energies = list()

    for model_folder in data_folders:
        ans = load_ans(model_folder)
        if ans.config.problem_type == "MIMO":
            print("MIMO is not supported. Skipping this folder ...")
            break
        model: IsingModel = ans.ising_model
        nb_runs = ans.config.nb_runs
        energies = []
        for run in range(int(nb_runs / 2)):
            run_folder = model_folder / f"run_{run}"
            for i in range(2):
                final_state = np.loadtxt(run_folder / f"hw_final_state_{i}")
                energies.append(relative_to_best_found(model.evaluate(final_state), ans.best_found))
        final_energies.append(
            pd.DataFrame(
                {
                    "relative Hamiltonian energy": energies,
                    "simulation type": "Hardware",
                    "benchmark": ans.benchmark_name,
                }
            )
        )
        if add_sw:
            final_energies.append(
                pd.DataFrame(
                    {
                        "relative Hamiltonian energy": relative_to_best_found(
                            ans.energies["Multiplicative"], ans.best_found
                        ),
                        "simulation type": "software simulation",
                        "benchmark": ans.benchmark_name,
                    }
                )
            )
    final_energies = pd.concat(final_energies)

    plt.figure()
    sns.boxplot(data=final_energies, x="benchmark", y="relative Hamiltonian energy", hue="simulation type")
    plt.yscale("log")
    plt.xlabel("Benchmark")
    plt.ylabel("Relative Ising Energy")
    plt.savefig(data_folders[0] / figname)
    plt.close()


def plot_mppi(data_folder, add_sw: bool = True, figname: str = "mppi_results"):
    ans = load_ans(data_folder)
    env, _, _ = create_environment(ans.scene)
    x_ref = ans.reference_trajectory
    predicted_traj_hw = ans.predicted_trajectory_hw
    executed_traj_hw = ans.executed_trajectory_hw

    # Plot environment
    try:
        fig, ax = plot_environment(env, figsize=(16, 10))
    except Exception as _:
        fig, ax = plt.subplots(figsize=(16, 10))
        if getattr(env, "control_points", None):
            cx = [c[0] for c in env.control_points]
            cy = [c[1] for c in env.control_points]
            ax.plot(cx, cy, "ko", markersize=6, alpha=0.6, label="control points")
        if getattr(env, "start", None) is not None:
            ax.plot([env.start[0]], [env.start[1]], "ro", label="start")
        if getattr(env, "goal_region", None):
            try:
                gx = [g[0] for g in env.goal_region]
                gy = [g[1] for g in env.goal_region]
                ax.plot(gx + [gx[0]], gy + [gy[0]], "g--", alpha=0.6, label="goal")
            except Exception:
                pass
    xs, ys = x_ref[:, 0], x_ref[:, 1]
    ax.plot(xs, ys, "-o", alpha=0.8, markersize=3, color="blue")
    plot_trajectory(ax, executed_traj_hw, predicted_traj_hw, "HW predicted trajectory", "r")
    if add_sw:
        plot_trajectory(
            ax, ans.executed_trajectory_sw, ans.predicted_trajectory_sw, "Simulated predicted trajectory", "g"
        )
    plt.title("Optimized Trajectory vs Reference Path")
    plt.xlabel("X Coordinate")
    plt.ylabel("Y Coordinate")
    plt.legend()
    plt.savefig(data_folder / f"{figname}.pdf", dpi=300)


# ==== UTIL FUNCTIONS ====


def plot_trajectory(
    ax: plt.axes, executed_traj: np.ndarray, predicted_traj: np.ndarray, label_name: str, linecolor: str
):
    ax.plot(
        [x[0] for x in executed_traj],
        [x[1] for x in executed_traj],
        color=linecolor,
        marker="s",
        alpha=0.5,
        label=label_name,
        markersize=3,
        linewidth=0.7,
    )
    for coords in predicted_traj:
        coords = coords[:, :2]
        ax.plot([x[0] for x in coords], [x[1] for x in coords], color=linecolor, alpha=0.2)


def compute_difference(state: np.ndarray, T: np.ndarray, r: int, x_tilde: np.ndarray, M: int, N: int) -> float:
    if M == 2:
        # BPSK scheme
        x_optim1 = T @ (state + np.ones((r * N,))) - np.ones((N,))
    else:
        # QAM scheme
        x_optim1 = T @ (state + np.ones((r * N,))) - (np.sqrt(M) - 1) * np.ones((N,))

    return x_tilde - x_optim1


def load_ans(folder: Path) -> Ans:
    ans = Ans()
    ans.load(folder / "ans.pkl")
    return ans

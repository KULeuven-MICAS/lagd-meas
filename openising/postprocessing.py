# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import numpy as np
import pandas as pd
import seaborn as sns

from openising import TOP_MEAS
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
    data = {}
    cases = {
        "delta_h": ("With delta h calculation", "^", "#87aadeff"),
        "no_delta_h": ("Without delta h calculation", "o", "#000000"),
        "galena": ("Analog macro only", "*", "#2ca02cff"),
    }
    for case, (case_name, _, _) in cases.items():
        energy = np.loadtxt(data_folder / f"hw_best_energy_{case}", dtype=float)
        time = np.loadtxt(data_folder / f"hw_final_time_{case}", dtype=float)
        cycles = np.loadtxt(data_folder / f"hw_cycles_it_{case}", dtype=float)
        if case != "galena":
            for i, time_i in enumerate(time):
                if time_i == 0.0:
                    time_i = np.mean(time[[i-1, i+1]])
                    time[i] = time_i
            for i, energy_i in enumerate(energy):
                if energy_i == 0.0:
                    energy[i] = energy[i-1]
        data[case_name] = {"time": time, "energy": energy, "cycles": cycles}

    plt.figure()
    for case_name, marker, color in cases.values():
        en = data[case_name]["energy"][-1] if case_name != "Analog macro only" else data[case_name]["energy"]
        time = data[case_name]["time"][-1] if case_name != "Analog macro only" else data[case_name]["time"]
        plt.plot(
            data[case_name]["time"],
            data[case_name]["energy"],
            marker=marker,
            color=color,
            fillstyle='none',
            label=f"{case_name}: best={en}, time:{time}",
            linewidth=0.3
        )
    plt.xlabel("Time [s]")
    # plt.xscale("log")
    plt.ylabel("Hamiltonian energy")
    plt.legend()
    plt.savefig(data_folder / f"{figname}.svg")
    plt.close()
    plt.figure()
    for case_name, marker, color in cases.values():
        if case_name != "Analog macro only":
            x_points = np.array(list(range(len(data[case_name]["cycles"]))))
            y_points = data[case_name]["cycles"]
            zero_points = np.where(y_points == 0)[0]
            x_points = np.delete(x_points, zero_points)
            y_points = np.delete(y_points, zero_points)
            mean = np.mean(y_points)
            plt.scatter(
                x_points,
                y_points,
                marker=marker,
                # edgecolor=color,
                facecolor=color,
                label=f"{case_name}: Avg={mean}"
            )
    plt.xlabel("Iteration")
    plt.ylabel("Cycles/iteration")
    plt.legend()
    plt.savefig(data_folder / f"{figname}_cycles.svg")


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
            snr_ber_points_sw[ans.SNR] = []
            snr_ber_points_zf[ans.SNR] = []
        snr_ber_points.append(compute_BER(ans, model_folder))
        snr_ber_points_zf[ans.SNR].append(ans.BER["ZF"])
        if add_sw:
            snr_ber_points_sw[ans.SNR].append(ans.BER["Multiplicative"])

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


def boxplot(data_folders: list[Path], add_sw: bool = True, figname: str = "boxplot", delta_h_calculation: bool = True):
    """Makes a boxplot for every model folder in the data_folders list, and add the TTS as another data point.

    Args:
        data_folders (list[Path]): _description_
        add_sw (bool, optional): _description_. Defaults to True.
        figname (str, optional): _description_. Defaults to "boxplot".
    """
    final_energies = dict()
    delta_h_str = int(delta_h_calculation) * "_deltah"
    for model_folder in data_folders:
        ans = load_ans(model_folder)
        # print(np.mean(np.array(ans.energies["Multiplicative"])/ans.best_found))
        if ans.config.problem_type == "MIMO":
            print("MIMO is not supported. Skipping this folder ...")
            break
        model: IsingModel = ans.ising_model
        nb_runs = ans.config.nb_runs
        energies = []
        for run in range(int(nb_runs / 2)):
            run_folder = model_folder / f"run_{run}"
            for i in range(2):
                final_state = np.loadtxt(run_folder / f"hw_final_state_{i + 1}{delta_h_str}")
                energies.append(np.abs(model.evaluate(final_state) / ans.best_found) * 100)

        final_energies[ans.benchmark] = energies
        print(f"Max {ans.benchmark}: {np.max(energies)}, Min: {np.min(energies)}, Avg: {np.mean(energies)}")

    fig, ax = plt.subplots()
    data  = []
    xticks = []
    for benchmark, energy in final_energies.items():
        data.append(energy)
        print(f"{benchmark}: min {np.min(energy)}, avg {np.mean(energy)}, max {np.max(energy)}")
        xticks.append(benchmark)
    fig, ax = plt.subplots()
    bplot = ax.boxplot(data, patch_artist=True, tick_labels=xticks)
    for patch in bplot['boxes']:
        patch.set_facecolor("#739cd9")
    for median in bplot['medians']:
        median.set_color('black')
    ax.set_ybound(60, 105)
    fig.savefig(data_folders[0] / f"{figname}.svg")
    plt.close()


def plot_mppi(data_folder, add_sw: bool = True, figname: str = "mppi_results"):
    ans = Ans()
    ans.load(data_folder / "ans_result.pkl")
    env, _, _ = create_environment(ans.scene)
    x_ref = ans.reference_trajectory
    predicted_traj_hw = ans.predicted_trajectory_hw
    executed_traj_hw = ans.executed_trajectory_hw

    error = executed_traj_hw - x_ref
    rmse = np.sqrt(error**2).mean()
    r_2 = 1 - (error**2 / np.maximum((error**2).mean(), 10e-4)).mean()
    # Plot environment
    try:
        fig, ax = plot_environment(env, figsize=(16, 10))
    except Exception as _:
        fig, ax = plt.subplots(figsize=(16, 10))
        if getattr(env, "control_points", None):
            cx = [c[0] for c in env.control_points]
            cy = [c[1] for c in env.control_points]
            ax.plot(cx, cy, "ko", markersize=12, alpha=0.6, label="control points")
        if getattr(env, "start", None) is not None:
            ax.plot([env.start[0]], [env.start[1]], "ro", label="start", markersize=12)
        if getattr(env, "goal_region", None):
            try:
                gx = [g[0] for g in env.goal_region]
                gy = [g[1] for g in env.goal_region]
                ax.plot(gx + [gx[0]], gy + [gy[0]], "g--", alpha=0.6, label="goal")
            except Exception:
                pass
    xs, ys = x_ref[:, 0], x_ref[:, 1]
    ax.plot(xs, ys, "-o", alpha=0.8, markersize=5, color="blue")
    plot_trajectory(
        ax, executed_traj_hw, predicted_traj_hw, f"HW predicted trajectory: RMSE={rmse}, R^2={r_2}", "#338000"
    )
    if add_sw:
        plot_trajectory(
            ax, ans.executed_trajectory_sw, ans.predicted_trajectory_sw, "Simulated predicted trajectory", "g"
        )
    plt.title("Optimized Trajectory vs Reference Path")
    plt.xlabel("X Coordinate")
    plt.ylabel("Y Coordinate")
    plt.legend()
    plt.savefig(data_folder / f"{figname}.svg", dpi=300)


# ==== UTIL FUNCTIONS ====


def plot_trajectory(
    ax: plt.axes, executed_traj: np.ndarray, predicted_traj: np.ndarray, label_name: str, linecolor: str
):
    ax.plot(
        [x[0] for x in executed_traj],
        [x[1] for x in executed_traj],
        color=linecolor,
        marker="s",
        label=label_name,
        markersize=5,
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


def compute_BER(ans: Ans, data_folder: Path, delta_h_calculation: bool):
    N = np.shape(ans.x_tilde)[0]
    if ans.config.dummy_qam == 2:
        r = 1
        is_bpsk = True
    else:
        if ans.config.is_hamming_encoding:  # with hamming encoding
            r = int(np.sqrt(ans.config.dummy_qam) - 1)
        else:  # with binary encoding
            r = int(np.ceil(np.log2(np.sqrt(ans.config.dummy_qam))))
        is_bpsk = False
    if ans.config.is_hamming_encoding:  # with hamming encoding
        T = np.block([[np.eye(N) for _ in range(r)]])
    else:  # with binary encoding
        T = np.block([[2 ** (r - i) * np.eye(N) for i in range(1, r + 1)]])
    nb_trials = len(ans.MIMO)
    differences = np.zeros((N, nb_trials))
    delta_h_str = "_deltah" if delta_h_calculation else ""
    for trial in range(nb_trials):
        lowest_id = 0
        lowest_en = np.inf
        for run in range(2):
            en = np.loadtxt(data_folder / f"run_{trial}/hw_best_energy_{run + 1}{delta_h_str}")
            if len(en.shape) == 1:
                en = en[-1]
            if en < lowest_en:
                lowest_id = run
                lowest_en = en
        if is_bpsk:
            xtilde = ans.x[:, trial]
        else:
            xtilde = np.block([np.real(ans.x[:, trial]), np.imag(ans.x[:, trial])])
        state = np.loadtxt(data_folder / f"run_{trial}/hw_final_state_{lowest_id + 1}{delta_h_str}")
        differences[:, trial] = compute_difference(state, T, r, xtilde, ans.config.dummy_qam, N)
    if is_bpsk:
        ber = np.mean(np.sum(np.abs(differences) / 2, axis=1) / (np.log2(ans.config.dummy_qam) * nb_trials))
    else:
        array_mid = differences.shape[0] // 2
        diff_real_half = differences[0:array_mid, :]
        diff_imag_half = differences[array_mid:, :]
        diff_of_users = np.hstack((diff_real_half, diff_imag_half))
        ber = np.mean(np.sum(np.abs(diff_of_users) / 2, axis=1) / (np.log2(ans.config.dummy_qam) * nb_trials))
    return ber


if __name__ == "__main__":
    boxplot(
        [
            TOP_MEAS / "openising/Maxcut_experiment/pm1d_100",
            TOP_MEAS / "openising/Maxcut_experiment/pm1s_100",
            TOP_MEAS / "openising/Maxcut_experiment/pm1d_80",
            TOP_MEAS / "openising/Maxcut_experiment/pm1s_80",
        ],
        False,
    )
    # boxplot(
    #     [
    #         TOP_MEAS / "openising/Maxcut_experiment/pm1d_100_1it",
    #         TOP_MEAS / "openising/Maxcut_experiment/pm1s_100_1it",
    #         TOP_MEAS / "openising/Maxcut_experiment/pm1d_80_1it",
    #         TOP_MEAS / "openising/Maxcut_experiment/pm1s_80_1it",
    #     ],
    #     False,
    #     "boxplot_1it"
    # )
    plot_mppi(TOP_MEAS / "openising/MPPI_experiment/model_0", False)
    BPSK_folder = TOP_MEAS / "openising/MIMO_experiment/model_6"
    ans_MIMO_BPSK = load_ans(BPSK_folder)
    print("BER sw:" + str(ans_MIMO_BPSK.BER["Multiplicative"]))
    BER = compute_BER(ans_MIMO_BPSK, BPSK_folder, True)
    print("BER:" + str(BER))
    plot_convergence_run(TOP_MEAS / "openising/convergence_run/run_0", False)

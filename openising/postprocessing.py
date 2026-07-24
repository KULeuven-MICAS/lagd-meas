# TODO
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from ising.stages.model import IsingModel
from ising.stages.simulation_stage import Ans
from ising.utils.HDF5Logger import return_data


def plot_convergence_run(
    data_folder: Path, add_sw: bool = True, best_found: None | float = None, figname: str = "energy_convergence"
):
    """Plots the convergence of one run folder

    Args:
        data_folder (Path): _description_
        add_sw (bool, optional): _description_. Defaults to True.
        best_found (None | float, optional): _description_. Defaults to None.
        figname (str, optional): _description_. Defaults to "energy_convergence".
    """
    ans = Ans()
    ans.load(data_folder.parent / "ans.pkl")
    is_MIMO = ans.problem_type == "MIMO"
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
        if best_found is not None:
            plt.axhline(best_found, linestyle="--", color="k", label=f"Optimum: {best_found}")
        plt.xlabel("Iteration")
        plt.ylabel("Hamiltonian energy")
        plt.legend()
        plt.savefig(data_folder / f"{figname}_run{run + 1}.png")
        plt.close()


def plot_BER(data_folders: list[Path], figname: str = "ber_curve", add_sw: bool = True):
    snr_ber_points = dict()

    for model_folder in data_folders:
        ans = Ans()
        ans.load(model_folder / "ans.pkl")
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
        snr_ber_points[ans.SNR] = np.mean(
            np.sum(np.abs(diff_of_users) / 2, axis=1) / (np.log2(ans.config.dummy_qam) * nb_trials)
        )


def plot_convergence_multi():
    pass


# ==== UTIL FUNCTIONS ====
def compute_difference(state: np.ndarray, T: np.ndarray, r: int, x_tilde: np.ndarray, M: int, N: int) -> float:
    if M == 2:
        # BPSK scheme
        x_optim1 = T @ (state + np.ones((r * N,))) - np.ones((N,))
    else:
        # QAM scheme
        x_optim1 = T @ (state + np.ones((r * N,))) - (np.sqrt(M) - 1) * np.ones((N,))

    return x_tilde - x_optim1

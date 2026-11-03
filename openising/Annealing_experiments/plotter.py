# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Sofie De Weer <sofie.deweer@kuleuven.be>

from matplotlib.patches import Patch
import numpy as np
from functools import lru_cache
from pathlib import Path
import logging
import matplotlib.pyplot as plt
import csv

from openising.postprocessing import load_ans


def best_of_groups(energies: np.ndarray, group_size: int) -> np.ndarray:
    """Take the minimum energy in consecutive, non-overlapping full groups.

    @type energies: np.ndarray
    @param energies: energy values of the galena run
    @type group_size: int
    @param group_size: the amount of energy points to group together.
    @rtype: np.ndarray
    @return: the best energy of every group
    """
    energies = np.asarray(energies, dtype=float)
    nb_groups = energies.size // group_size
    if nb_groups == 0:
        raise ValueError(f"Need at least {group_size} Galena trials.")
    # Discard the remainder, matching annealing's floor(nb_runs / group_size).
    return energies[: nb_groups * group_size].reshape(nb_groups, group_size).min(axis=1)


@lru_cache(maxsize=None)
def measured_energies(folder: Path, delta_h_calculation: bool = True) -> np.ndarray:
    """Evaluate the model at the measured final state of every run in folder.

    @type folder: Path
    @param folder: folder holding ans.pkl and the run_<i> folders with the chip output.
    @type delta_h_calculation: bool
    @param delta_h_calculation: whether the measurement was done with the delta h calculation.
    @rtype: np.ndarray
    @return: the energy of every measured run.
    """
    ans = load_ans(folder)
    delta_h_str = "_deltah" * int(delta_h_calculation)
    energies = []
    for run in range(ans.config.nb_runs // 2):
        for i in range(2):
            state = np.loadtxt(folder / f"run_{run}" / f"hw_final_state_{i + 1}{delta_h_str}")
            energies.append(ans.ising_model.evaluate(state.astype(np.float32)))
    return np.asarray(energies, dtype=float)


def best_found(folder: Path) -> float:
    """Return the best-known energy stored in the ans.pkl of folder."""
    reference = load_ans(folder).best_found
    if reference is None or not np.isfinite(reference):
        raise ValueError(f"{folder}: need a finite best-known energy for relative values.")
    return reference


def unpack_run(run: tuple[str, Path] | Path) -> tuple[str | None, Path]:
    """A run is either (benchmark name, folder) or only the folder."""
    if isinstance(run, tuple):
        return run
    return None, run


def relative_values(energies: np.ndarray, reference: float) -> np.ndarray:
    """Express the energies as a percentage of the best-known energy."""
    if reference < 0:
        return 100 * energies / reference
    return 100 * reference / energies


def plot_comparison(
    galena_runs: dict[int, tuple[str, Path]],
    annealing_runs: dict[int, dict[int, tuple[str, Path] | Path]],
    bestx: list[int],
    output_dir: Path,
    fig_name: str = "galena_vs_annealing",
    delta_h_calculation: bool = True,
):
    """Plot equal-budget Galena and annealing distributions of the measurements for each benchmark.

    @type galena_runs: dict[int, tuple[str, Path]]
    @param galena_runs: benchmark index -> (benchmark name, galena folder).
    @type annealing_runs: dict[int, dict[int, tuple[str, Path] | Path]]
    @param annealing_runs: benchmark index -> bestx -> ([benchmark name,] annealing_<bestx> folder).
    @type bestx: list[int]
    @param bestx: the amount of Galena trials per group / annealing flipping iterations.
    @type output_dir: Path
    @param output_dir: folder in which the figure is stored.
    @type fig_name: str
    @param fig_name: name of the figure without extension.
    @type delta_h_calculation: bool
    @param delta_h_calculation: whether the measurement was done with the delta h calculation.
    """
    fig, ax = plt.subplots(figsize=(16, 6))
    colors = ("tab:blue", "tab:orange")
    centers, ticks, labels, names = [], [], [], []
    for benchmark_index in sorted(galena_runs):
        benchmark, galena = galena_runs[benchmark_index]
        names.append(benchmark)
        reference = best_found(galena)
        galena_energies = measured_energies(galena, delta_h_calculation)
        center = benchmark_index * (len(bestx) + 1)
        centers.append(center)
        for group_index, group_size in enumerate(bestx):
            position = center + group_index - (len(bestx) - 1) / 2
            ticks.append(position)
            labels.append(str(group_size))
            _, annealing = unpack_run(annealing_runs[benchmark_index][group_size])
            distributions = (
                best_of_groups(galena_energies, group_size),
                measured_energies(annealing, delta_h_calculation),
            )
            for energies, offset, color in zip(distributions, (-0.19, 0.19), colors):
                values = relative_values(energies, reference)
                if values.size == 0 or not np.all(np.isfinite(values)):
                    raise ValueError(f"{benchmark}, x={group_size}: empty or non-finite results.")
                x = position + offset
                # A single/constant result has no density; show its exact value.
                if np.ptp(values) == 0:
                    ax.hlines(values[0], x - 0.16, x + 0.16, color=color, linewidth=2)
                    continue
                parts = ax.violinplot(
                    [values],
                    positions=[x],
                    widths=0.34,
                    showmeans=True,
                    showmedians=False,
                    showextrema=True,
                )
                for body in parts["bodies"]:
                    body.set_facecolor(color)
                    body.set_edgecolor("black")
                    body.set_alpha(0.65)
                for key in ("cmeans", "cmins", "cmaxes", "cbars"):
                    parts[key].set_color("black")
                    parts[key].set_linewidth(1.2)

    ax.axhline(100, color="black", linestyle="--", linewidth=1.3)
    ax.set_ylabel("Ising Energy / best-known Ising Energy (%)")
    ax.set_xticks(ticks, labels)
    ax.set_xlabel("x: Galena trials per group / annealing flipping iterations", labelpad=38)
    for center, benchmark in zip(centers, names):
        ax.text(
            center,
            -0.09,
            Path(benchmark).name.replace(".", "_"),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontweight="bold",
        )
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend(
        handles=[
            Patch(facecolor=color, alpha=0.65, edgecolor="black", label=label)
            for color, label in zip(colors, ("Galena (best of x)", "Annealing (x iterations)"))
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=2,
        frameon=False,
    )
    fig.tight_layout()
    output_path = output_dir / f"{fig_name}.svg"
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    logging.info("Saved comparison figure to %s", output_path)
    return fig


def write_summary(
    galena_runs: dict[int, tuple[str, Path]],
    annealing_runs: dict[int, dict[int, tuple[str, Path] | Path]],
    bestx: list[int],
    output_file: Path,
    relative: bool = False,
    delta_h_calculation: bool = True,
):
    """Write a CSV summary of best/average/worst measured energies at the largest `bestx`.
    CSV columns: benchmark, method, best, average, worst

    @type galena_runs: dict[int, tuple[str, Path]]
    @param galena_runs: benchmark index -> (benchmark name, galena folder).
    @type annealing_runs: dict[int, dict[int, tuple[str, Path] | Path]]
    @param annealing_runs: benchmark index -> bestx -> ([benchmark name,] annealing_<bestx> folder).
    @type bestx: list[int]
    @param bestx: the amount of Galena trials per group / annealing flipping iterations.
    @type output_file: Path
    @param output_file: path to write CSV to
    @type relative: bool
    @param relative: when True, report values as percentage of the best-known energy in the Galena ans.pkl.\
        Defaults to False.
    @type delta_h_calculation: bool
    @param delta_h_caclulation: if the measurement is done with delta h calculation or not. Defaults to true.
    """
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    max_x = int(max(bestx))

    with output_file.open("w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["benchmark", "method", "best", "average", "worst"])

        for benchmark_index in sorted(galena_runs):
            benchmark, galena = galena_runs[benchmark_index]
            _, annealing = unpack_run(annealing_runs[benchmark_index][max_x])
            galena_vals = best_of_groups(measured_energies(galena, delta_h_calculation), max_x)
            ann_vals = measured_energies(annealing, delta_h_calculation)
            for method, vals in (("galena", galena_vals), ("annealing", ann_vals)):
                if relative:
                    vals = relative_values(vals, best_found(galena))
                writer.writerow(
                    [benchmark, method, f"{np.min(vals):.6g}", f"{np.mean(vals):.6g}", f"{np.max(vals):.6g}"]
                )
    logging.info("Wrote summary CSV to %s", output_file)
    return output_file

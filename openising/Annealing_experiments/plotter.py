from matplotlib.patches import Patch
import numpy as np
from pathlib import Path
import logging
import matplotlib.pyplot as plt
import csv


def best_of_groups(energies, group_size):
    """Take the minimum energy in consecutive, non-overlapping full groups."""
    energies = np.asarray(energies, dtype=float)
    nb_groups = energies.size // group_size
    if nb_groups == 0:
        raise ValueError(f"Need at least {group_size} Galena trials.")
    # Discard the remainder, matching annealing's floor(nb_runs / group_size).
    return energies[: nb_groups * group_size].reshape(nb_groups, group_size).min(axis=1)


def plot_comparison(galena_runs, annealing_runs, bestx, solver, output_dir, fig_name="galena_vs_annealing_"):
    """Plot equal-budget Galena and annealing distributions for each benchmark."""
    fig, ax = plt.subplots(figsize=(16, 6))
    colors = ("tab:blue", "tab:orange")
    centers, ticks, labels = [], [], []
    for benchmark_index, (benchmark, galena) in enumerate(galena_runs.items()):
        reference = galena.best_found
        if reference is None or not np.isfinite(reference):
            raise ValueError(f"{benchmark}: need a negative best-known energy for cut percentages.")
        center = benchmark_index * (len(bestx) + 1)
        centers.append(center)
        for group_index, group_size in enumerate(bestx):
            position = center + group_index - (len(bestx) - 1) / 2
            ticks.append(position)
            labels.append(str(group_size))
            distributions = (
                best_of_groups(galena.energies[solver], group_size),
                np.asarray(annealing_runs[benchmark][group_size].energies[solver], dtype=float),
            )
            for energies, offset, color in zip(distributions, (-0.19, 0.19), colors):
                if reference < 0:
                    values = 100 * energies / reference
                else:
                    values = 100 *(reference/energies)
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
    ax.set_ylabel("Cut value / best-known cut (%)")
    ax.set_xticks(ticks, labels)
    ax.set_xlabel("x: Galena trials per group / annealing flipping iterations", labelpad=38)
    for center, benchmark in zip(centers, galena_runs):
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
    for extension in ("png", "pdf"):
        output_path = output_dir / f"{fig_name}{solver}.{extension}"
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        logging.info("Saved comparison figure to %s", output_path)
    return fig


def write_summary(galena_runs, annealing_runs, bestx, output_file, solvers=None, relative=False):
    """Write a CSV summary of best/worst/average energies at the largest `bestx`.

    - `galena_runs`: mapping benchmark -> Ans-like object (has `energies[solver]` and `best_found`)
    - `annealing_runs`: mapping benchmark -> {nb_runs: Ans-like}
    - `bestx`: sequence of ints; the maximum value is used to aggregate Galena groups
    - `output_file`: path to write CSV to
    - `solvers`: optional iterable of solver names; if None, inferred from `galena_runs`
    - `relative`: when True, report values as percentage of `galena.best_found`

    CSV columns: benchmark, method, solver, best, worst, average
    """
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    max_x = int(max(bestx))

    # Infer solvers if not provided
    if solvers is None:
        try:
            first = next(iter(galena_runs.values()))
            solvers = list(first.energies.keys())
        except StopIteration:
            raise ValueError("galena_runs is empty; cannot infer solvers")

    with output_file.open("w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["benchmark", "method", "best", "average", "worst"])

        for benchmark, galena in galena_runs.items():
            # prefer benchmark label embedded in the Ans object when available
            benchmark_label = getattr(galena, "benchmark", None) or benchmark
            reference = getattr(galena, "best_found", None)
            for solver in solvers:
                # Galena: take best-of-groups with group size = max_x
                try:
                    galena_vals = best_of_groups(np.asarray(galena.energies[solver], dtype=float), max_x)
                except Exception:
                    galena_vals = np.array([], dtype=float)

                # Annealing: values at nb_runs == max_x
                try:
                    ann = annealing_runs[benchmark][max_x]
                    ann_vals = np.asarray(ann.energies[solver], dtype=float)
                except Exception:
                    ann_vals = np.array([], dtype=float)

                for method, vals in (("galena", galena_vals), ("annealing", ann_vals)):
                    if vals.size == 0:
                        writer.writerow([benchmark_label, method, solver, "", "", ""])
                        continue
                    if relative:
                        if reference is None or not np.isfinite(reference):
                            raise ValueError(
                                f"{benchmark_label}: need a negative finite best-known reference for relative values"
                            )
                        if reference < 0:
                            vals_to_report = 100.0 * vals / reference
                        else:
                            vals_to_report = 100.0 * reference / vals
                    else:
                        vals_to_report = vals
                    best = float(np.min(vals_to_report))
                    worst = float(np.max(vals_to_report))
                    average = float(np.mean(vals_to_report))
                    writer.writerow(
                        [benchmark_label, method, f"{best:.6g}", f"{average:.6g}", f"{worst:.6g}",]
                    )
    logging.info("Wrote summary CSV to %s", output_file)
    return output_file

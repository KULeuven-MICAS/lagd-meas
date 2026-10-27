import yaml
import logging
from copy import deepcopy
from pathlib import Path

from ising import api
from ising.stages import TOP
from ising.stages.simulation_stage import Ans
from openising import TOP_MEAS


def load_experiment_config(config_file: str) -> tuple[dict, Path]:
    """Load the base and experiment config files. The experiment settings take precedence over the base settings,
    such that problem specific parameters (e.g. the TSP weight constant) match the software experiments.

    @type config_file: str
    @param config_file: folder (relative to TOP_MEAS) holding config_experiment.yaml.
    @rtype: tuple[dict, Path]
    @return: the merged config and the folder in which the experiment is stored.
    """
    save_folder = TOP_MEAS / config_file
    with (TOP_MEAS / "openising/base_experiment.yaml").open("r") as f:
        config = yaml.safe_load(f)
    with (save_folder / "config_experiment.yaml").open("r") as f:
        config.update(yaml.safe_load(f))
    # ensure the amount of runs is even
    if config["nb_runs"] % 2 != 0:
        config["nb_runs"] *= 2
    return config, save_folder


def sweep_points(config: dict) -> list:
    """Return the values of the swept annealing parameter, or [None] when no parameter is swept."""
    if config.get("sweep_parameter") is None:
        return [None]
    return config["sweep_values"]


def benchmark_folder(save_folder: Path, benchmark: str) -> Path:
    return save_folder / benchmark.split("/")[-1].split(".")[0]


def galena_folder(save_folder: Path, benchmark: str) -> Path:
    return benchmark_folder(save_folder, benchmark) / "galena"


def annealing_folder(save_folder: Path, benchmark: str, x: int, sweep_parameter=None, sweep_value=None) -> Path:
    folder = benchmark_folder(save_folder, benchmark)
    if sweep_parameter is not None:
        folder = folder / f"{sweep_parameter}_{sweep_value}"
    return folder / f"annealing_{x}"


def galena_config(config: dict, benchmark: str) -> dict:
    """Galena: every run performs a single flipping iteration. The swept parameter is not changed, like in the
    software experiments, such that one Galena run per benchmark serves all sweep points."""
    galena = deepcopy(config)
    galena["benchmark"] = benchmark
    galena["nb_flipping"] = 1
    galena["logfile_discrimination"] = "galena"
    return galena


def annealing_config(config: dict, benchmark: str, x: int, sweep_parameter=None, sweep_value=None, logfile_discrimination: str="") -> dict:
    """Annealing: x flipping iterations for nb_runs / x runs, such that the total budget equals that of Galena."""
    annealing = deepcopy(config)
    annealing["benchmark"] = benchmark
    annealing["nb_flipping"] = x
    nb_runs = int(config["nb_runs"] / x)
    # every chip run holds two software runs
    annealing["nb_runs"] = nb_runs + nb_runs % 2
    annealing["logfile_discrimination"] = f"annealing_{x}"
    if sweep_parameter is not None:
        annealing[sweep_parameter] = sweep_value
        annealing["logfile_discrimination"] = f"{sweep_parameter}_{sweep_value}_annealing_{x}"
    return annealing


def simulate_run(
    run_config: dict, config_path: Path, folder: Path, problem_type: str, logging_level: int = logging.INFO
) -> Ans:
    """Simulate the given configuration and store the answer in folder. When the folder already holds a simulation,
    it is loaded instead."""
    folder.mkdir(parents=True, exist_ok=True)
    ans = Ans()
    if (folder / "ans.pkl").exists():
        ans.load(folder / "ans.pkl")
        return ans
    with config_path.open("w") as file:
        yaml.safe_dump(run_config, file)
    ans, _ = api.get_hamiltonian_energy(
        problem_type=problem_type,
        config_path=str(config_path.relative_to(TOP)),
        logging_level=logging_level,
    )
    ans.save(folder / "ans.pkl")
    return ans


def is_compiled(folder: Path, nb_runs: int, delta_h_calculation: bool) -> bool:
    elf_file = "lagd_commands" + ("_deltah.elf" if delta_h_calculation else ".elf")
    return (folder / f"run_{nb_runs // 2 - 1}" / elf_file).exists()


def is_measured(folder: Path, nb_runs: int, delta_h_calculation: bool) -> bool:
    delta_h_str = "_deltah" * int(delta_h_calculation)
    return (folder / f"run_{nb_runs // 2 - 1}" / f"hw_final_state_2{delta_h_str}").exists()

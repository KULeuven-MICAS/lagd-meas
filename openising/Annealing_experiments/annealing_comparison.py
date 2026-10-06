import yaml
import logging
from pathlib import Path

from ising import api
from ising.stages import TOP
from ising.stages.simulation_stage import Ans


def annealing_comparison(
    benchmarks: list[str],
    config: dict,
    galena_path: Path,
    galena_config: dict,
    annealing_path: Path,
    annealing_config: dict,
    bestx: list[int],
    config_folder: Path,
    problem_type: str = "Maxcut",
    logging_level: int = logging.INFO,
):
    galena_runs = {benchmark: None for benchmark in benchmarks}
    annealing_runs = {benchmark: {nb_runs: None for nb_runs in bestx} for benchmark in benchmarks}
    for benchmark in benchmarks:
        save_folder = config_folder / benchmark.split("/")[-1].split(".")[0]
        if not save_folder.exists():
            save_folder.mkdir(parents=True, exist_ok=True)
        # Galena run
        galena_folder = save_folder / "galena"
        if not galena_folder.exists():
            galena_folder.mkdir(parents=True, exist_ok=True)
        if (galena_folder / "ans.pkl").exists():
            galena_runs[benchmark] = (Ans(), galena_folder)
            galena_runs[benchmark][0].load(galena_folder / "ans.pkl")
        else:
            galena_config["benchmark"] = benchmark
            galena_config["nb_flipping"] = 1
            galena_config["logfile_discrimination"] = "galena"
            with galena_path.open("w") as file:
                yaml.safe_dump(galena_config, file)
            ans, _ = api.get_hamiltonian_energy(
                problem_type=problem_type,
                config_path=str(galena_path.relative_to(TOP)),
                logging_level=logging_level,
            )
            galena_runs[benchmark] = (ans, galena_folder)
            galena_runs[benchmark][0].save(galena_folder / "ans.pkl")
        # Annealing run
        annealing_config["benchmark"] = benchmark
        for runs in bestx:
            annealing_folder = save_folder / f"annealing_{runs}"
            annealing_config["logfile_discrimination"] = f"annealing_{runs}"
            if not annealing_folder.exists():
                annealing_folder.mkdir(parents=True, exist_ok=True)
            if (annealing_folder / "ans.pkl").exists():
                annealing_runs[benchmark][runs] = (Ans(), annealing_folder)
                annealing_runs[benchmark][runs][0].load(annealing_folder / "ans.pkl")
            else:
                annealing_config["nb_runs"] = int(config["nb_runs"] / runs)
                annealing_config["nb_flipping"] = runs

                with annealing_path.open("w") as file:
                    yaml.safe_dump(annealing_config, file)
                ans, _ = api.get_hamiltonian_energy(
                    problem_type=problem_type,
                    config_path=str(annealing_path.relative_to(TOP)),
                    logging_level=logging_level,
                )
                annealing_runs[benchmark][runs] = (ans, annealing_folder)
                annealing_runs[benchmark][runs][0].save(annealing_folder / "ans.pkl")
    return galena_runs, annealing_runs

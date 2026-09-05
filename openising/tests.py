import numpy as np
import pathlib
import yaml

from argparse import Namespace
from openising import TOP_ISING
from submodules.openising.ising.stages.maxcut_parser_stage import MaxcutParserStage
from submodules.openising.ising.stages.simulation_stage import Ans
from submodules.openising.ising.stages.model.ising import IsingModel
from submodules.openising.ising.solvers.Multiplicative import Multiplicative


def ferromagnetic(nb_zeros: int, nb_ones: int, add_h: bool, h_sign: int = 1, nb_vars: int = 256):
    assert nb_zeros + nb_ones == nb_vars
    initial_state_ones = np.ones(nb_ones)
    initial_state_zeros = -np.ones(nb_zeros)
    initial_state1 = np.append(initial_state_ones, initial_state_zeros)
    initial_state2 = np.append(initial_state_zeros, initial_state_ones)
    initial_states = [initial_state1, initial_state2]
    J = np.ones((nb_vars, nb_vars))
    J = np.triu(J, k=1)
    if add_h:
        h = np.ones(nb_vars) * h_sign
    else:
        h = np.zeros(nb_vars)
    model = IsingModel(J, h)
    return model, initial_states


def anti_ferromagnetic(nb_zeros: int, nb_ones: int, add_h: bool, h_sign: int = 1):
    assert nb_zeros + nb_ones == 256
    initial_state_ones = np.ones(nb_ones)
    initial_state_zeros = -np.ones(nb_zeros)
    initial_state1 = np.append(initial_state_ones, initial_state_zeros)
    initial_state2 = np.append(initial_state_zeros, initial_state_ones)
    initial_states = [initial_state1, initial_state2]
    J = -np.ones((256, 256))
    J = np.triu(J, k=1)
    if add_h:
        h = np.ones(256) * h_sign
    else:
        h = np.zeros(256)
    model = IsingModel(J, h)
    return model, initial_states

def biqmac_pm1d(nb_zeros: int, nb_ones: int, add_h: bool, h_sign: int = 1, nb_runs: int = 2):
    benchmark = TOP_ISING / "ising/benchmarks/biqmac/rudy/pm1d_100.0"
    graph, _ = MaxcutParserStage.G_parser(benchmark)
    model = MaxcutParserStage.generate_maxcut(graph)
    model.J = np.sign(model.J)
    model.c = 0
    initial_states = [-np.ones(model.num_variables) for _ in range(nb_runs)]
    return model, initial_states

def dummy_maxcut_small(nb_zeros: int, nb_ones: int, add_h: bool, h_sign: int = 1, nb_runs: int = 2):
    assert nb_zeros + nb_ones == 256
    initial_states = []
    for _ in range(nb_runs):
        initial_state_ones1 = np.array([-1, -1, 1, 1, -1])
        initial_state_zeros = -np.ones(nb_zeros)
        # initial_state1 = np.append(initial_state_zeros, initial_state_ones1)
        initial_states.append(initial_state_ones1)
    # J = np.zeros((256, 256))
    # J = np.ones((5,5))
    J = np.array([[0, -1, -1, 0, 0],
                 [-1, 0, 0, -1, 0],
                 [-1, 0, 0, -1, -1],
                 [0, -1, -1, 0, -1],
                 [0, 0, -1, -1, 0]])
    # J[2, :] *= -1
    # J[:, 2] *= -1
    J = np.triu(J, k=1)
    h = np.zeros(5)
    # h[-5:] = -2*np.ones(5)
    model = IsingModel(J, h)
    return model, initial_states


def run_test(
    config_file: pathlib.Path,
):
    with (TOP_ISING / config_file).open("r") as f:
        config = yaml.safe_load(f)

    if config["test"] == "ferromagnetic":
        model, initial_states = ferromagnetic(
            config["nb_zeros"], config["nb_ones"], config["add_h"], config["sign_h"], config["nb_vars"]
        )
    elif config["test"] == "anti-ferromagnetic":
        model, initial_states = anti_ferromagnetic(
            config["nb_zeros"], config["nb_ones"], config["add_h"], config["sign_h"]
        )
    elif config["test"] == "dummy_maxcut_small":
        model, initial_states = dummy_maxcut_small(
            config["nb_zeros"],
            config["nb_ones"],
            config["add_h"],
            config["sign_h"],
            config["nb_runs"],
        )
    elif config["test"] == "biqmac_pm1d":
        model, initial_states = biqmac_pm1d(
            config["nb_zeros"],
            config["nb_ones"],
            config["add_h"],
            config["sign_h"],
            config["nb_runs"],
        )
    logfile_top: pathlib.Path = TOP_ISING / "ising/outputs/tests"
    if not logfile_top.exists():
        logfile_top.mkdir(parents=True, exist_ok=True)
    ans = Ans()
    ans.quantized_model = model
    ans.h_scale_factor = 4
    ans.logfiles = []
    ans.benchmark = config["test"]
    ans.ising_model = model
    ans.config = Namespace(**config)
    ans.best_found = 0
    ans.states = {"Multiplicative": []}
    ans.energies = {"Multiplicative": []}
    ans.computation_time = {"Multiplicative": []}
    ans.operation_count = {"Multiplicative": []}
    ans.total_iteration_count = {"Multiplicative": []}
    ans.initialization_states = (initial_states,)
    print("running solver")
    for run in range(config["nb_runs"]):
        logfile = logfile_top / (config["test"] + f"_run{run}.log")
        state, energies, time, ops, it = Multiplicative().solve(
            model,
            initial_states[run],
            config["num_iterations_Multiplicative"],
            config["nb_flipping"],
            config["cluster_threshold"],
            config["init_cluster_size"],
            config["end_cluster_size"],
            cluster_choice=config["cluster_choice"],
            file=logfile,
        )
        ans.logfiles.append(logfile)
        ans.states["Multiplicative"].append(state)
        ans.energies["Multiplicative"].append(energies)
        ans.computation_time["Multiplicative"].append(time)
        ans.operation_count["Multiplicative"].append(ops)
        ans.total_iteration_count["Multiplicative"].append(it)
    print(f"initial energies: {[model.evaluate(initial_state) for initial_state in initial_states]}")
    print("Ising energies: " + str(ans.energies["Multiplicative"]))
    print(ans.states["Multiplicative"])
    print(len(np.where(ans.states["Multiplicative"][0]==1)[0]))
    print(np.where(ans.states["Multiplicative"][0]==1)[0])
    breakpoint()
    return ans, None

import numpy as np
from pathlib import Path

from submodules.openising.ising.stages.model.ising import IsingModel
from submodules.openising.ising.stages.simulation_stage import Ans
from openising import TOP_MEAS
from submodules.openising.ising.solvers.Multiplicative import Multiplicative


def is_local_optima(model: IsingModel, state) -> bool:
    """Return True when every single-spin-flip neighbour has energy >= current state."""
    sample = np.asarray(state)
    current_energy = model.evaluate(sample)

    for index in range(sample.size):
        neighbour = sample.copy()
        neighbour[index] *= -1
        if model.evaluate(neighbour) < current_energy:
            return False

    return True


def calculate_energy(ans_file: Path, state: np.ndarray):
    ans = Ans()
    ans.load(ans_file)
    model = ans.ising_model
    print(model.evaluate(state))
    print(is_local_optima(model, state))


def mimo_check():
    ans = Ans()
    ans.load(Path("openising/MIMO_experiment/model_0/ans.pkl"))
    ans_MIMO = ans.MIMO[29]
    quantized_model = ans_MIMO.quantized_model
    initial_state = ans_MIMO.states["Multiplicative"][0]
    state, en, _, _, _ = Multiplicative().solve(
        quantized_model, initial_state, 10000, 128, 0.3, 0.8, 0.0625, seed=100, sigma_J=1 / 3
    )
    print(f"Energy: {en - quantized_model.c}")
    solver = "Multiplicative"
    print(f"end state: {ans_MIMO.states[solver][0]}")
    state_galena = np.where(ans_MIMO.states["Multiplicative"][0] == -1, 0, 1).reshape((1, 256))
    print(f"End energy {quantized_model.evaluate(ans_MIMO.states[solver][0]) - quantized_model.c}")

    np.savetxt(Path("openising/mimo_state"), state_galena, fmt="%1s")

if __name__ == "__main__":
    # calculate_energy(TOP_MEAS / "openising/tests/dummy_maxcut_small/ans.pkl", np.array([-1, 1, 1, -1, 1]))
    mimo_check()

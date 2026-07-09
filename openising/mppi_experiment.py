import numpy as np
import yaml
from pathlib import Path
from argparse import Namespace
from typing import Any

from save_model import store_run
from ising.stages import TOP
from openising.ising.stages.model import IsingModel
from ising.stages.model.MPPI.environment import generate_random_scene, create_environment, create_reference_trajectory
from ising.stages.simulation_stage import SimulationStage
from ising.stages.quantization_stage import QuantizationStage
from ising.stages.combine_nodes_stage import CombineNodesStage
from ising.benchmarks.MPPI import get_dynamics_model

GITREPO = TOP.parent

def get_trajectory_view(benchmark, trajectory: np.ndarray) -> np.ndarray:
    # Get horizon
    L = benchmark.HORIZON_LENGTH
    # Get horizon view
    view = trajectory[:L, :]
    # If selected reference view is smaller than horizon
    if view.shape[1] < L:
        last_col = view[-1:, :]
        num_pad = L - view.shape[0]
        view = np.vstack((view, np.repeat(last_col, num_pad, axis=0)))
    # Flatten and put T first
    return view.reshape(-1, 1)

def reset_actions(benchmark, prev_actions: np.ndarray|None = None) -> np.ndarray:
    L = benchmark.HORIZON_LENGTH
    action_dim = benchmark.action_dim
    actions = np.zeros((L, action_dim))
    # Set non selected actions as initial state for next iteration
    if prev_actions is not None:
        actions[:-benchmark.action_horizon, :] = prev_actions[benchmark.action_horizon:, :]
    return actions

def build_ising(benchmark,
                x_bar: np.ndarray,
                x_ref: np.ndarray,
                A_seq: np.ndarray,
                B_seq: np.ndarray,
                RR: np.ndarray,
                QQ: np.ndarray,
                EE: np.ndarray
                ) -> IsingModel:
    """Build Ising model.

    Args:
        state: current state (state_dim,)
        x_bar: Nominal trajectory rollout (L + 1, state_dim)
        x_ref: Windowed reference trajectory (L, state_dim)
        A_seq: Sequence of A matrices (L, state_dim, state_dim)
        B_seq: Sequence of B matrices (L, state_dim, action_dim)
        RR: Cost matrix for actions (action_dim, action_dim)
        QQ: Cost matrix for states (state_dim, state_dim)
        EE: Binary encoding matric (state_dim * n_bits, n_bits)

    Returns:
        Ising Model to run
    """
    # Check if approximation is done
    assert benchmark.n_approx_iter is not None
    # Build phi
    phi_fwd, phi_bwd = build_phi(A_seq, benchmark.delta_t, n_approx_iter=benchmark.n_approx_iter)
    phi_fwd_arr, phi_bwd_arr = np.stack(phi_fwd, axis=0), np.stack(phi_bwd, axis=0)
    # Build B
    B_flat, _ = build_B_mat(phi_fwd_arr, phi_bwd_arr, B_seq, benchmark.delta_t)
    # Build J and h
    J, h, c = build_qubo(
        x_bar,
        x_ref,
        B_flat,
        QQ, RR,
        E=EE,
    )
    Q = J + np.diag(h)
    return IsingModel.from_qubo(Q)

def mppi_experiment(config_path, save_folder):
    with Path(TOP/config_path).open(encoding="utf-8") as file:
            config: dict = yaml.safe_load(file)

    config = Namespace(**config)
    benchmark_path = GITREPO / config.benchmark

    with Path(benchmark_path).open(encoding="utf-8") as file:
        benchmark:dict = yaml.safe_load(file)
    benchmark = Namespace(**benchmark)

    # Get dynamics model
    model = get_dynamics_model(benchmark)
    # Get QUBO parameters
    qubo = QUBOController(benchmark)
    # Unpack QUBO controller parameters
    rr ,qq, ee = qubo.RR, qubo.QQ, qubo.EE

    scene, x_ref = parse_benchmark_trajectory(benchmark) # Reference benchmark trajectory
    executed_trajectory = [x_ref[0, :]] # Initial state (Can be benchmark.x_init)
    predicted_trajectory = [] # List of all rollouts
    u_bar = None # Initial actions (Can be benchmark.u_init)

    # Iterate over reference points
    for point in np.arange(start=1, stop=x_ref.shape[0], step=benchmark.action_horizon):
        # Most recently visited state
        state = executed_trajectory[-1]
        # Get horizon view
        x_ref_view = get_trajectory_view(benchmark, x_ref[point:, :])
        # Set initial actions to zero
        u_bar = reset_actions(benchmark, u_bar)
        # Amount of MPPI iterations is defined in benchmark config
        for _ in range(benchmark.n_mppi_iterations):
            # Empty variation holder for vjp
            dx, du = state[None, ...], u_bar[None, ...]
            # Do model rollout
            x_bar, _, A_seq, B_seq, _ = model.rollout(state, u_bar, dx, du)
            # Build ising model
            ising_model = build_ising(benchmark,
                x_bar, x_ref_view, A_seq, B_seq, rr, qq, ee
            )
            # Necessary kwargs for next stages
            kwargs = dict()
            kwargs["config"] = config
            kwargs["ising_model"] = ising_model
            # Get sub stages --> See workflow
            list_of_callables = [CombineNodesStage, SimulationStage]
            sub_stage = QuantizationStage(list_of_callables, **kwargs)
            # Store answers
            ans, _ = next(sub_stage.run()) # This runs the ising model
            store_run(ans, save_folder, "MPPI")
            # TODO: run chip and get results
        break
            # actions = 0
            # # Apply actions in continuous space
            # u_bar = u_bar + (actions @ ee.T).reshape(-1, benchmark.action_dim)

        # Execute actions
        for a in range(benchmark.action_horizon):
            new_u = u_bar[a, :]
            state, force = model.discrete_step(state.squeeze(), new_u.squeeze())
            # Add new state to list
            executed_trajectory.append(state)

        # Full predicted trajectory at point
        predicted_trajectory.append(
            x_bar.reshape(-1, benchmark.state_dim)
        )
    # Add final result to answer (and some stuff for result plotting)
    ans.executed_trajectory = executed_trajectory
    ans.predicted_trajectory = predicted_trajectory
    ans.reference_trajectory = x_ref
    ans.scene = scene
    ans.delta_t = benchmark.delta_t

def parse_benchmark_trajectory(benchmark):
    scene = generate_random_scene(seed=benchmark.seed)
    env, control_pts, bc_headings = create_environment(scene)
    x_ref = create_reference_trajectory(env, control_pts, bc_headings,
                                        v=benchmark.velocity, dt=benchmark.delta_t)
    return scene, x_ref.T

def build_phi(A_seq, dt, n_approx_iter: int = 1):
    """
    Build forward and backward rollout sequences.

    Φ_k = Pi_j=0^k I + A_j * dt
    phi_fwd[k] = Φ_k @ Φ_{k-1} @ ... @ Φ_0     (left-product, x_{k+1} = phi_fwd[k] @ x_0)
    phi_bwd[k] ≈ phi_fwd[k]^{-1}                (approximate inverse)

    First-order approx (n_approx_iter=1):  Φ_k^{-1} ≈ I - A_k·dt   (error O(dt²))
    Higher-order (n_approx_iter=m):        adds terms up to (-A·dt)^m (error O(dt^{m+1}))
    """
    T, nx, _ = A_seq.shape
    I_mat = np.eye(nx)

    def scan_fwd(phi_prev, A_k):
        phi_next = (I_mat + A_k * dt) @ phi_prev  # left-multiply: newer step on left
        return phi_next

    phi_prev = I_mat
    phi_fwd = []
    for A in A_seq:
        phi_next = scan_fwd(phi_prev, A)
        phi_fwd.append(phi_next)
        phi_prev = phi_next

    def inv_factor(A_k):
        """(I + A_k·dt)^{-1} to order n_approx_iter in dt."""
        # Geometric series: (I + X)^{-1} = I - X + X² - ...  where X = A_k·dt
        X = A_k * dt
        result = I_mat - X
        if n_approx_iter > 1:
            Xpow = X
            for _ in range(n_approx_iter - 1):
                Xpow = Xpow @ X
                # alternating sign
                result = result + Xpow if (_ % 2 == 0) else result - Xpow
        return result

    def scan_bwd(phi_bwd_prev, A_k):
        # phi_bwd[k] = phi_bwd[k-1] @ Φ_k^{-1}  (right-multiply: older inverse on right)
        # This gives phi_fwd[k]^{-1} = Φ_0^{-1} @ ... @ Φ_k^{-1}
        phi_bwd_next = phi_bwd_prev @ inv_factor(A_k)
        return phi_bwd_next

    phi_prev = I_mat
    phi_bwd = []
    for A in A_seq:
        phi_next = scan_bwd(phi_prev, A)
        phi_bwd.append(phi_next)
        phi_prev = phi_next

    return phi_fwd, phi_bwd


def build_B_mat(phi_fwd, phi_bwd, B_seq, dt):
    """
    Build linearized control influence matrix B_mat.
    B_mat[i,j,n,u] = phi_fwd[i] @ phi_bwd[j] @ B_seq[j] * dt   for j <= i
                   = 0                                            for j >  i

    Shapes:
        phi_fwd : (T, nx, nx)
        phi_bwd : (T, nx, nx)
        B_seq   : (T, nx, nu)
        output  : (T, T, nx, nu) → reshape to (T*nx, T*nu)
    """
    # Step 1: phi_bwd[j] @ B_seq[j] * dt  for all j  →  (T, nx, nu)
    # This is the "B column for each time" pre-multiplied by the inverse STM
    phi_bwd_B = np.einsum('jmk,jku->jmu', phi_bwd, B_seq) * dt  # (T, nx, nu)

    # Step 2: outer product over (i,j) pairs
    # B[i,j,n,u] = phi_fwd[i,n,m] * phi_bwd_B[j,m,u]
    B = np.einsum('inm,jmu->ijnu', phi_fwd, phi_bwd_B)  # (T, T, nx, nu)

    # Step 3: causal mask — action j can only affect state i if j <= i
    T = phi_fwd.shape[0]
    causal_mask = np.tril(np.ones((T, T), dtype=phi_fwd.dtype))
    B = B * causal_mask[:, :, None, None]

    # Reshape to (T*nx, T*nu): state dim is outer, action dim is inner
    # B[i,j,n,u] → B_flat[(i*nx + n), (j*nu + u)]
    B_flat = B.transpose(0, 2, 1, 3).reshape(B.shape[0] * B.shape[2],
                                             B.shape[1] * B.shape[3])
    return B_flat, B  # return both for debugging

def build_qubo(
    x_bar,        # (T+1, nx)   nominal trajectory from rollout
    x_ref,        # (T, nx)     reference trajectory (horizon window)
    B_flat,       # (T*nx, T*nu) or (T*nx, n_bits) if pre-multiplied by E
    Q, R,         # (T*nx, T*nx), (T*nu, T*nu) cost matrices
    E=None,       # (T*nu, n_bits) encoding matrix, None for continuous
):
    # --- Residual terms ---
    r = x_bar[1:].reshape(-1) - x_ref.reshape(-1)  # (T*state_dim,)
    # --- binary encoding ---
    BE = B_flat if E is None else B_flat @ E  # (T*state_dim, T*action_dim) or (T*state_dim, n_bits)

    # --- QUBO terms ---
    QBE = Q @ BE  # (T*state_dim, n_cols)
    J_mat = BE.T @ QBE  # (n_cols, n_cols)  quadratic
    J_mat = J_mat + (E.T @ R @ E if E is not None else R)  # + R̃ or E^T R̃ E
    h = 2.0 * (BE.T @ (Q @ r))  # (n_cols,)         linear
    c = r @ (Q @ r)  # scalar            constant

    # --- Symmetrize ---
    J_mat = J_mat.T + J_mat
    return J_mat, h, c

def clip_bounds(arr, bounds, variable_map):
    for variable, bounds in bounds.items():
        # Variable mapping: added complexity for flexibility
        i = variable_map[variable]
        # Clip to bounds
        np.clip(arr[:, i], bounds[0], bounds[1], out=arr[:, i])
    return arr

class QUBOController:
    """QUBO Controller instance"""
    def __init__(self, config: Any):
        """
        Initialise the controller.

        param controller_config: controller config class
        param qubo_config: qubo config class
        """
        self.config = config

        self.EE, self.mapping = continuous_to_binary_mapping(
            config.action_dim,
            config.HORIZON_LENGTH,
            config.K,
            config.N_BITS,
            config.action_scales,
            config.scale_multiplier
        )

        self.Q_slack = config.Q_slack

        self._RR = self.build_R_trajectory(None, None)
        self._QQ = self.build_Q_trajectory(None, None)

    @property
    def RR(self):
        return self._RR

    @property
    def QQ(self):
        return self.Q_slack * self._QQ

    # Clipping functions
    def clip_actions(self, actions: np.ndarray) -> np.ndarray:
        return clip_bounds(actions,
                           self.config.Q_BOUNDS,
                           self.config.variable_to_action_map)

    def clip_states(self, states: np.ndarray) -> np.ndarray:
        return clip_bounds(states,
                           self.config.R_BOUNDS,
                           self.config.variable_to_state_map)

    def build_Q_trajectory(self, x_bar, u_bar):
        if self.config.Q is None:
            if self.config.Q_diag is not None:
                Q = self.Q_slack * np.diag(self.config.Q_diag)
            else:
                Q = self.Q_slack * np.eye(self.config.state_dim)
        else:
            Q = self.config.Q

        # State weights I_N ⊗ Q w. last diagonal term weighted (HORIZON_LENGTH * state_dim, HORIZON_LENGTH * state_dim)
        W = np.eye(self.config.HORIZON_LENGTH)
        W[-1, -1] = self.config.TERMINAL_WEIGHT
        QQ = np.kron(W, Q)
        return QQ

    def build_R_trajectory(self, x_bar, u_bar):
        if self.config.R is None:
            if self.config.R_diag is not None:
                R = np.diag(self.config.R_diag)
            else:
                R = np.eye(self.config.action_dim)
        else:
            R = self.config.R

        # Action weights: I_N ⊗ R (HORIZON_LENGTH * action_dim, HORIZON_LENGTH * action_dim)
        RR = np.kron(np.eye(self.config.HORIZON_LENGTH), R)
        return RR

def continuous_to_binary_mapping(
        m: int,
        HORIZON_LENGTH: int,
        BIT_MULTIPLIER: int,
        N_BITS: int,
        action_scales: list[float] | None = None,
        scale_multiplier: float|None = None,
):
    # Setup default scales
    if action_scales is None:
        action_scales = [20.0, 2.0] if m == 2 else [1.0] * m
    if scale_multiplier is None:
        scale_multiplier = 1./3.

    scales = np.array(action_scales) * np.array(scale_multiplier)  # Shape (m,)

    # Bit vector
    bits = np.arange(N_BITS)
    E_base = BIT_MULTIPLIER * (2.0 ** bits)
    E_base = E_base / E_base.max() / 2.0
    # MSB flip for 2's complement style mapping
    E_base[..., -1] = -E_base[..., -1]

    # Spatial block E (m x m*L)
    # kron(diag(scales), E_base) -> (m, m) ⊗ (1, N_BITS) = (m, m*N_BITS)
    E_block = np.kron(np.diag(scales), E_base[None, :])

    # Block diagonal EE (m*N x m*L*N)
    # kron(I_N, E_block) -> (HORIZON_LENGTH, HORIZON_LENGTH) ⊗ (m, m*N_BITS) = (m*N, m*N_BITS*HORIZON_LENGTH)
    EE = np.kron(np.eye(HORIZON_LENGTH), E_block)
    return EE, {}

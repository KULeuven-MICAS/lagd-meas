#!/usr/bin/env python3
# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Generate an Ising problem for the Galena chip.
#
#   python sw/tools/gen_ising_problem.py            # generate what main() selects
#   python sw/tools/gen_ising_problem.py 01100      # score a state against it, write nothing
#
# HOW TO USE THIS. The problem builders below are ordinary functions taking ordinary parameters.
# main() at the bottom is the only place you edit: call the builder you want with the arguments
# you want, and hand the result to emit() along with the folder name to write it under. Sweeps are
# just loops in main().
#
# Output goes to submodules/lagd-im/sw/tests/ref/data/<folder>/, the single source every scenario
# reads: utils/gen_model_data.py turns it into model_j_data.h, the linker places that in l1_j_spm,
# and both tests/ref/ and tests/galena/perf/ work from those same bytes. The files hold nothing but
# numbers -- no library name, no path -- so nothing about the generation side reaches the lagd-im
# repo, and isinglib is imported at runtime from ISINGLIB_SRC so there is no install dependency.

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LEVELS = 7
REF_SPINS = 256

# Choose if small problem lands at the TOP (or at the bottom)
MIRROR_TO_LOW_SPINS = True

BIQMAC_DIR = REPO_ROOT / "submodules/openising/ising/benchmarks/biqmac/rudy"

# The experiment problem set: one directory per problem, experiments/<name>/
#   model   the 518-line model file (J, h, offset, scaling factor h) -- required
#   info    free-form "key: value" provenance, e.g. a certified optimum -- optional
# `model` is exactly what utils/gen_model_data.py parses, so a problem can be dropped in straight
# from that flow. The directory is the problem's own, so measurements can live alongside it.
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

# --- library bootstrap -------------------------------------------------------
_LIB = Path(os.environ.get("ISINGLIB_SRC", Path.home() / "projects/ising/lib/src"))
if not _LIB.is_dir():
    sys.exit(f"library source not found at {_LIB}; set ISINGLIB_SRC")
sys.path.insert(0, str(_LIB))

import numpy as np  # noqa: E402

from isinglib import (  # noqa: E402,F401
    ExhaustiveSolver,
    GreedySolver,
    Problem,
    SimulatedAnnealingSolver,
    TabuSearchSolver,
)
from isinglib.problems.planted import planted_solution  # noqa: E402
from isinglib.topology import generators  # noqa: E402


# =============================================================================
# PROBLEMS
# =============================================================================
# Each returns an isinglib Problem and nothing else. What the chip STARTS from is a separate
# choice -- see INITIAL STATES below -- so one problem can be run from several starts without
# regenerating it. Add your own freely; nothing registers them, main() just calls one.

def feedback_pulse():
    r"""The 5-spin ring used for bring-up.

        0---1
        |   |
        2---3
         \ /
          4

    Its bring-up start state was [1, 1, 0, 0, 1]; pass that as emit()'s `start` to reproduce it.
    """
    j = np.array([
        [ 0, -1, -1,  0,  0],
        [-1,  0,  0, -1,  0],
        [-1,  0,  0, -1, -1],
        [ 0, -1, -1,  0, -1],
        [ 0,  0, -1, -1,  0],
    ], dtype=float)
    problem = Problem(j=j, h=np.zeros(5), meta={"name": "feedback_pulse"})
    return problem


def ferromagnet(n=192, weight=7, seed=0):   # seed unused: this problem is deterministic
    j = np.full((n, n), float(weight))
    np.fill_diagonal(j, 0.0)
    return Problem(j=j, h=np.zeros(n), meta={"name": f"ferromagnet(n={n})"})


def planted_gauge(n=256, seed=0):
    rng = np.random.default_rng(seed)
    problem = planted_solution(
        generators.complete(n),
        coupling=lambda m: rng.integers(1, LEVELS + 1, m).astype(float),
        bias=0.0,
        rng=seed,
        meta={"name": f"planted_gauge(n={n}, seed={seed})"},
    )
    return problem


def random_maxcut(n=256, degree=None, p=0.1, seed=0):
    rng = np.random.default_rng(seed)
    if degree is not None:
        p = degree / (n - 1)
    topology = generators.erdos_renyi(n, p=p, rng=seed)
    j = topology.fill(lambda m: rng.choice((-1, 1), m))
    meta = {"name": f"random_maxcut(n={n}, {'degree=%g' % degree if degree else 'p=%g' % p})"}
    return Problem(j=j, h=np.zeros(n), meta=meta)


def load_model(name, magnitude=1):
    """A problem from experiments/<name>/model.

    The file is a fixed 256-wide layout, but a problem rarely fills it and need not even occupy a
    contiguous span -- mpc uses 38 spins scattered over logical 11..175. Inactive spins (no
    couplings, no field) are dropped and the rest RELABELLED to 0..n-1, so every problem arrives
    the same shape: a dense n-spin block that emit() then pads to 256, landing at hardware 0..n-1.
    Relabelling is lossless for an Ising problem -- it is a graph, the names do not matter -- and
    meta["compact_map"] records logical i -> original index if you need to map results back.

    `magnitude` scales every weight. The +/-1 BiqMac families give the array the weakest signal it
    can be asked to resolve, and multiplying through does NOT change the problem -- the optimal
    state is identical, only the energy scale moves -- so it is a clean way to ask what the array
    does with more drive. Keep magnitude * max|weight| <= LEVELS or emit() reports clipping, which
    WOULD change the problem: mimo and mpc already reach +/-7 and cannot be scaled.

    offset and scaling factor h ride along in meta and are written back unchanged: the digital
    energy engine applies scaling_h to h (GCFG2_DGT_HSCALING), so losing it changes the problem.
    """
    if magnitude < 1:
        sys.exit(f"magnitude must be >= 1, got {magnitude}")
    path = EXPERIMENTS_DIR / name / "model"
    if not path.is_file():
        have = ", ".join(sorted(q.parent.name for q in EXPERIMENTS_DIR.glob("*/model"))) or "none"
        sys.exit(f"no such problem {name!r} in {EXPERIMENTS_DIR} (have: {have})")

    lines = path.read_text().splitlines()
    if len(lines) != 518:
        sys.exit(f"{path}: expected 518 lines, got {len(lines)}")

    def signed(tok):
        v = int(tok, 2)
        return v - 16 if v & 8 else v

    j = np.array([[signed(t) for t in lines[1 + r].split()] for r in range(REF_SPINS)], dtype=float)
    h = np.array([signed(lines[258 + i].strip()) for i in range(REF_SPINS)], dtype=float)

    active = [i for i in range(REF_SPINS) if h[i] != 0 or np.any(j[i] != 0)]
    if not active:
        sys.exit(f"{path}: no active spins")
    idx = np.array(active)
    j, h = j[np.ix_(idx, idx)] * magnitude, h[idx] * magnitude

    tag = f"{name}, magnitude={magnitude}" if magnitude != 1 else name
    meta = {"name": f"load_model({tag})",
            "magnitude": magnitude,
            "offset": float(lines[515].strip()),
            "scaling_h": int(lines[517].strip())}
    if active != list(range(len(active))):
        meta["compact_map"] = active
        meta["compacted_from"] = (active[0], active[-1])
    info = EXPERIMENTS_DIR / name / "info"
    if info.is_file():
        for line in info.read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta.setdefault(f"info_{k.strip()}", v.strip())

    # A certified MAX-CUT optimum in the info file becomes real ground truth. Cut and total weight
    # are both in weight units, so both scale with magnitude -- and so does their difference, the
    # target energy.
    try:
        meta["maxcut_total_weight"] = float(meta["info_total_weight"]) * magnitude
        meta["maxcut_optimum"] = float(meta["info_optimum_cut"]) * magnitude
    except (KeyError, ValueError):
        pass
    return Problem(j=j, h=h, meta=meta)


def mimo_reduced(bits_per_symbol=8, drop_bit=None, magnitude=1):
    """mimo with one bit dropped from every symbol: 256 spins -> 224 at the defaults.

    mimo fills the array with 256 spins, which at 8 bits per symbol is 32 symbols. Dropping one
    bit from each removes 32 spins. `drop_bit` selects which position goes, defaulting to the last
    one in the symbol.

    NOTE this is a genuinely different problem, not a relabelling: removing a spin is the same as
    deleting its variable, so its couplings vanish from the objective. The `offset` carried over
    from the file no longer reconstructs the original objective either. That is the point -- it is
    a reduced-precision variant -- but it means energies are not comparable with full mimo.

    The bit positions carry no visible significance ordering in the quantised model (mean |J| is
    ~1.0 for every position mod 8), so which index is "last" is a positional convention here
    rather than something the data shows.
    """
    problem = load_model("mimo", magnitude)
    j = np.asarray(problem.j)
    h = np.asarray(problem.h)
    n = j.shape[0]
    if n % bits_per_symbol:
        sys.exit(f"mimo has {n} spins, not a multiple of {bits_per_symbol}")
    if drop_bit is None:
        drop_bit = bits_per_symbol - 1
    if not 0 <= drop_bit < bits_per_symbol:
        sys.exit(f"drop_bit must be 0..{bits_per_symbol - 1}, got {drop_bit}")

    keep = [i for i in range(n) if i % bits_per_symbol != drop_bit]
    idx = np.array(keep)
    meta = dict(problem.meta)
    meta["name"] = (f"mimo_reduced({n}->{len(keep)}, bits_per_symbol={bits_per_symbol}, "
                    f"drop_bit={drop_bit})")
    meta["dropped_spins"] = [i for i in range(n) if i % bits_per_symbol == drop_bit]
    # The certified-optimum keys, if any, describe the full problem and no longer apply.
    for k in ("maxcut_optimum", "maxcut_total_weight"):
        meta.pop(k, None)
    return Problem(j=j[np.ix_(idx, idx)], h=h[idx], meta=meta)


def sk_pm1(n=128, seed=0):
    rng = np.random.default_rng(seed)
    j = np.triu(rng.choice((-1.0, 1.0), size=(n, n)), 1)
    j = j + j.T
    return Problem(j=j, h=np.zeros(n), meta={"name": f"sk_pm1(n={n}, seed={seed})"})


def planted_loops(n=128, alpha=3.0, loop_len=3, seed=0):
    rng = np.random.default_rng(seed)
    target = rng.choice((-1, 1), size=n)

    j = np.zeros((n, n))
    placed = skipped = 0
    for _ in range(int(round(alpha * n))):
        loop = rng.choice(n, size=loop_len, replace=False)
        frustrated = rng.integers(loop_len)

        # Build the loop's contribution first, then take it only if every coupling stays inside
        # +/-LEVELS. A loop is all-or-nothing: adding a complete loop preserves the planted state
        # as a ground state and skipping one entirely is harmless, but CLIPPING a coupling
        # afterwards can destroy the guarantee. This is what lets alpha go high honestly.
        delta = {}
        for k in range(loop_len):
            a, b = int(loop[k]), int(loop[(k + 1) % loop_len])
            if a == b:
                continue
            sign = -1.0 if k == frustrated else 1.0
            delta[(a, b)] = delta.get((a, b), 0.0) + sign * target[a] * target[b]
        if any(abs(j[a, b] + d) > LEVELS for (a, b), d in delta.items()):
            skipped += 1
            continue
        for (a, b), d in delta.items():
            j[a, b] += d
            j[b, a] = j[a, b]
        placed += 1

    if skipped:
        print(f"  note      : {skipped} of {placed + skipped} loops skipped to keep every "
              f"|J| <= {LEVELS} (alpha is saturating; lower it or raise LEVELS)")

    meta = {"name": f"planted_loops(n={n}, alpha={alpha}, loop_len={loop_len}, seed={seed})",
            "planted_spins": target}
    return Problem(j=j, h=np.zeros(n), meta=meta)


def biqmac_instances():
    """Every rudy instance, grouped by family, with its size and largest |weight|.

    Usable families are the ones whose weights fit in +/-LEVELS at magnitude 1: pm1s/pm1d (+/-1)
    and g05 (all 1). The w*/pw* families carry weights up to 10 and would clip, which changes the
    problem -- biqmac() refuses them rather than silently solving something else.
    """
    rows = []
    for path in sorted(BIQMAC_DIR.iterdir()):
        if not path.is_file() or path.suffix == ".md" or path.name.endswith(".txt"):
            continue
        tokens = [ln.split() for ln in path.read_text().splitlines() if ln.strip()]
        n = int(tokens[0][0])
        peak = max(abs(float(t[2])) for t in tokens[1:])
        rows.append((path.name, n, peak, peak <= LEVELS))
    return rows


def biqmac(instance="pm1d_100.0", magnitude=1):
    """One BiqMac rudy MAX-CUT instance as an Ising problem, J = -w.

    `magnitude` scales every weight, spending more of the +/-LEVELS range on the same problem:
    the optimum and every energy scale with it, so a run at magnitude m is compared against
    m * the certified optimum. Anything that would clip is refused.
    """
    path = BIQMAC_DIR / instance
    if not path.is_file():
        have = ", ".join(sorted({p.name.rsplit(".", 1)[0] for p in BIQMAC_DIR.iterdir()
                                 if p.is_file() and not p.suffix in (".md", ".txt")}))
        sys.exit(f"BiqMac instance not found: {path}\n  families: {have}")

    tokens = [ln.split() for ln in path.read_text().splitlines() if ln.strip()]
    n, edges = int(tokens[0][0]), int(tokens[0][1])

    # Refuse rather than clip: a clipped weight is a different problem, and its certified optimum
    # would no longer be ground truth.
    peak = max(abs(float(t[2])) for t in tokens[1:])
    if peak * magnitude > LEVELS:
        top = int(LEVELS // peak)
        sys.exit(f"{instance}: |w| up to {peak:g} at magnitude {magnitude} exceeds +/-{LEVELS} "
                 f"and would clip -- " +
                 (f"use magnitude <= {top}" if top >= 1 else "this family does not fit the array"))

    j = np.zeros((n, n))
    total_weight = 0.0
    for a, b, w in ((int(t[0]), int(t[1]), float(t[2]) * magnitude) for t in tokens[1:]):
        j[a - 1, b - 1] = j[b - 1, a - 1] = -w      # J = -w, see above
        total_weight += w
    seen = int((np.triu(j, 1) != 0).sum())
    if seen != edges:
        print(f"  note      : header claims {edges} edges, {seen} distinct pairs found")

    tag = f"{instance}, magnitude={magnitude}" if magnitude != 1 else instance
    meta = {"name": f"biqmac({tag})", "magnitude": magnitude,
            "maxcut_total_weight": total_weight}
    # Cut and total weight are both in weight units, so the certified cut scales with magnitude.
    table = BIQMAC_DIR / "optimal_energy.txt"
    if table.is_file():
        for line in table.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == instance:
                meta["maxcut_optimum"] = float(parts[1]) * magnitude
                break
    return Problem(j=j, h=np.zeros(n), meta=meta)


def prepare_biqmac(instance="pm1d_100.0", name=None):
    """Write experiments/<name>/{model,info} for a rudy instance, so load_model() can read it.

    This is the one-off step that puts an instance on the same footing as pm1d_100: afterwards
    load_model(name, magnitude=m) is the way to use it, and the plot scripts find the certified
    optimum in the info file. Always written at magnitude 1 -- scaling belongs at load time.
    """
    problem = biqmac(instance)
    name = name or instance.replace(".", "_")
    n = problem.n
    if n > REF_SPINS:
        sys.exit(f"{instance}: {n} spins, the array holds {REF_SPINS}")

    # Same 518-line layout write_ref_folder() emits, but UNMIRRORED and unpadded in meaning:
    # logical spin i is row i, which is what load_model() expects to read back.
    j_pad = _pad_matrix(np.rint(problem.j).astype(int))
    h_pad = _pad_vector(np.rint(problem.h).astype(int))
    model = ["# J matrix"]
    model += [" ".join(_bits(v) for v in row) for row in j_pad]
    model.append("# h vector")
    model += [_bits(v) for v in h_pad]
    model += ["# offset", "0", "# scaling factor h", "1"]
    assert len(model) == 518, f"model must be 518 lines, got {len(model)}"

    meta = problem.meta
    weight = meta["maxcut_total_weight"]
    cut = meta.get("maxcut_optimum")
    info = [f"source: BiqMac rudy/{instance}",
            f"spins: {n}",
            f"edges: {int((np.triu(problem.j, 1) != 0).sum())}",
            f"weights: +/-{int(max(abs(problem.j).max(), 1))}",
            f"total_weight: {weight:g}"]
    if cut is not None:
        info += [f"optimum_cut: {cut:g}", f"optimum_energy: {weight - 2 * cut:g}"]
    info.append("note: MAX-CUT with J = -w; cut = (total_weight - energy) / 2")

    root = EXPERIMENTS_DIR / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "model").write_text("\n".join(model) + "\n")
    (root / "info").write_text("\n".join(info) + "\n")
    print(f"prepared {root}")
    for line in info:
        print(f"  {line}")
    print(f"  use it with: load_model({name!r}, magnitude=...)")
    return name


def prepare_all_biqmac():
    """Prepare every rudy instance that fits the array. One folder each, ~324 kB per model."""
    # These two were prepared by hand before this function existed; keep their short names so
    # existing logs, figures and info files stay valid.
    alias = {"pm1d_100.0": "pm1d_100", "pm1s_100.0": "pm1s_100"}
    done = []
    for instance, _, _, usable in biqmac_instances():
        if not usable:
            continue
        problem = biqmac(instance)
        name = alias.get(instance, instance.replace(".", "_"))
        root = EXPERIMENTS_DIR / name
        if (root / "model").is_file():
            print(f"  {name:<14} exists, left alone")
            continue
        prepare_biqmac(instance, name)
        done.append((name, problem.n))
    print(f"\nprepared {len(done)} instance(s)")
    return done


# =============================================================================
# INITIAL STATES
# =============================================================================

def zeros(n):
    """All spins down. The only start that reliably lands on this die."""
    return np.zeros(n, dtype=int)


def ones(n):
    """All spins up."""
    return np.ones(n, dtype=int)


def alternating(n):
    """0,1,0,1,... -- a start that is neither aligned nor anti-aligned with a ferromagnet."""
    return np.arange(n) % 2


def random_state(n, seed=0):
    """A random state. Pass a seed explicitly: `start=lambda n: random_state(n, seed=3)`."""
    return np.random.default_rng(seed).integers(0, 2, n)


def planted_state(problem):
    """The problem's own planted ground state, for problems that carry one.

    Starting there is a useful control: the array should stay put. If it wanders off, that is the
    array moving away from a known optimum, not a search failing to find one.
    """
    planted = (problem.meta or {}).get("planted_spins")
    if planted is None:
        sys.exit("this problem carries no planted state")
    return (np.asarray(planted) > 0).astype(int)


# =============================================================================
# Machinery -- you should not need to touch anything below.
# =============================================================================

def clamp(values, levels):
    values = np.asarray(values, dtype=float)
    rounded = np.rint(values)
    clipped = int(np.count_nonzero(np.abs(rounded) > levels))
    return np.clip(rounded, -levels, levels).astype(np.int64), clipped


def integer_energy(j_int, h_int, spins01, scaling_h=1):
    # h needs more range than 4 bits, so the model stores it divided down and multiplies it back
    # when the energy is formed. partial_energy_calc.sv:85 and refmodel_energy() do the same.
    s = np.where(np.asarray(spins01) != 0, 1, -1).astype(np.int64)
    return int(-(np.triu(j_int, 1) * np.outer(s, s)).sum() - scaling_h * (h_int * s).sum())


def survey(j_int, h_int, spins, truth=None, cut_total=None, scaling_h=1):
    n = j_int.shape[0]
    # h carries the model's scaling factor in the energy (partial_energy_calc.sv applies it), so
    # the solvers must see it scaled too. Without this they optimise an objective whose h is
    # scaling_h times too weak, and report solutions scored against a different problem -- at
    # scaling_h=16 that is the difference between -4770 and -9904 on mimo.
    quantised = Problem(j=j_int.astype(float), h=(h_int * scaling_h).astype(float))

    solvers = []
    if n <= 20:
        solvers.append(("exhaustive", ExhaustiveSolver()))
    solvers += [
        ("greedy x20", GreedySolver(n_restarts=20, rng=0)),
        ("annealing", SimulatedAnnealingSolver(n_steps=20_000, rng=0)),
        ("tabu", TabuSearchSolver(n_steps=2_000, rng=0)),
    ]

    def gap(e):
        return "" if truth is None else f"{e - truth:>+7}"

    def cut(e):
        return "" if cut_total is None else f"{(cut_total - e) / 2:>9.0f}"

    e0 = integer_energy(j_int, h_int, spins, scaling_h)
    print(f"  {'solver':<12} {'energy':>8} {'gap' if truth is not None else '':>7}"
          f"{'cut' if cut_total is not None else '':>9}   state")
    print(f"  {'start':<12} {e0:>8} {gap(e0)}{cut(e0)}   {''.join(str(int(b)) for b in spins)}")
    for label, solver in solvers:
        solution = solver.solve(quantised)
        state = (np.asarray(solution.spins) > 0).astype(int)
        energy = integer_energy(j_int, h_int, state, scaling_h)
        print(f"  {label:<12} {energy:>8} {gap(energy)}{cut(energy)}   "
              f"{''.join(str(b) for b in state)}   ({solution.time_s * 1e3:.1f} ms)")


def parse_state(text, n):
    bits = [c for c in text.strip() if not c.isspace()]
    if not bits:
        sys.exit("state to score is empty")
    bad = sorted({c for c in bits if c not in "01"})
    if bad:
        sys.exit(f"state contains non-binary characters: {' '.join(bad)}")

    note = ""
    if len(bits) < n:
        note = f"extended from {len(bits)} bits by repeating the last bit ({bits[-1]})"
        bits = bits + [bits[-1]] * (n - len(bits))
    elif len(bits) > n:
        note = f"truncated from {len(bits)} bits to the problem's first {n}"
        bits = bits[:n]
    return np.array([int(c) for c in bits]), note


# --- reference-flow emission ------------------------------------------------
def _bits(value, width=4):
    return format(int(value) & ((1 << width) - 1), f"0{width}b")


def _vec(bits01):
    return "".join("1" if b else "0" for b in bits01)


def _pad_matrix(j_int):
    out = np.zeros((REF_SPINS, REF_SPINS), dtype=np.int64)
    n = j_int.shape[0]
    out[:n, :n] = j_int
    return out


def _pad_vector(vec):
    out = np.zeros(REF_SPINS, dtype=np.int64)
    out[:len(vec)] = vec
    return out


def pack_j_u64(j_pad):
    words = []
    for row in j_pad:
        elems = [int(v) & 0xF for v in row]
        for group in [elems[i:i + 16] for i in range(0, REF_SPINS, 16)][::-1]:
            w = 0
            for e in group:
                w = (w << 4) | e
            words.append(w)
    return words


def j_checksum(j_pad):
    chk = 0
    for w in pack_j_u64(j_pad):
        chk = (chk * 31 + (w & 0xFFFFFFFF)) & 0xFFFFFFFF
        chk = (chk * 31 + (w >> 32)) & 0xFFFFFFFF
    return chk


def write_ref_folder(folder, j_int, h_int, spins, spins2, ref_spins, flips="single",
                     offset=0.0, scaling_h=1):
    root = REPO_ROOT / "submodules/lagd-im/sw/tests/ref/data" / folder
    root.mkdir(parents=True, exist_ok=True)

    j_pad = _pad_matrix(j_int)
    h_pad = _pad_vector(h_int)
    start = _pad_vector(spins)
    start2 = _pad_vector(spins2)
    final = _pad_vector(ref_spins)

    if MIRROR_TO_LOW_SPINS:
        # Reverse both axes of J and every vector, so the downstream NUM_SPIN-1-j reversal undoes
        # it and logical index i lands at hardware index i.
        j_pad = j_pad[::-1, ::-1]
        h_pad = h_pad[::-1]
        start = start[::-1]
        start2 = start2[::-1]
        final = final[::-1]

    # model_N: 518 lines exactly, per gen_model_data.py's documented layout.
    model = ["# J matrix"]
    model += [" ".join(_bits(v) for v in row) for row in j_pad]
    model.append("# h vector")
    model += [_bits(v) for v in h_pad]
    model += ["# offset", f"{offset:g}", "# scaling factor h", str(scaling_h)]
    assert len(model) == 518, f"model must be 518 lines, got {len(model)}"

    # clusters_N: line 1 is a skipped header, then 512 flip-candidate vectors. Single-spin flips
    # -- the standard Metropolis move set, and a sane default when the problem brings no cluster
    # schedule of its own.
    #
    # TWO THINGS THIS HAS TO GET RIGHT, both easy to get wrong:
    #   - the candidates live in the same index space as everything else, so they get the SAME
    #     mirroring as J, h and the states. Without that they walk the array from the far end
    #     while the mirrored problem sits at the near end, and almost every flip lands on padding.
    #   - they cycle over the PROBLEM's spins (k mod n), not over all 256. A flip of a padded spin
    #     changes no energy, so it is a wasted iteration: for a 100-spin problem, cycling mod 256
    #     throws away 61% of the schedule.
    #   - the two cluster files are INTERLEAVED by gen_flip_data.py: icon 2j comes from
    #     clusters_<odd>[j] and icon 2j+1 from clusters_<even>[j]. Writing the same 512 lines to
    #     both makes every candidate get proposed twice in a row, halving the useful schedule.
    #     They are built as the even and odd halves of one 1024-long sequence instead.
    n = j_int.shape[0]

    # `flips` selects the move set:
    #   "single"   one spin per candidate, cycling over the problem's spins (Metropolis default)
    #   "none"     ALL-ZERO icons. The engine still reads its way to icon_finish and the run still
    #              retires, but XOR with zero never changes the state -- so the digital side
    #              proposes nothing and the state stays where it started. A control, not a solver.
    #   callable   flips(g, n) -> the logical spin indices this candidate flips, for cluster moves
    def cluster_line(g):
        bits = np.zeros(REF_SPINS, dtype=np.int64)
        if flips == "single":
            bits[g % n] = 1
        elif callable(flips):
            for idx in flips(g, n):
                bits[int(idx)] = 1
        elif flips not in ("none", "zero", None):
            sys.exit(f"unknown flips {flips!r}: use 'single', 'none', or a callable")
        if MIRROR_TO_LOW_SPINS:
            bits = bits[::-1]
        return _vec(bits)

    label = ("single-spin, over the problem's own spins" if flips == "single"
             else "ALL ZERO -- no candidate flips anything" if flips in ("none", "zero", None)
             else "custom")
    cluster_header = f"# flip candidates ({label})"
    clusters_even = [cluster_header] + [cluster_line(2 * j) for j in range(512)]
    clusters_odd = [cluster_header] + [cluster_line(2 * j + 1) for j in range(512)]

    # states_in_N: gen_spin_data.py reads only the FIRST line (initial state) and the LAST
    # (reference result); the middle is padding it never looks at.
    #
    # THE TWO FILES ARE TWO DIFFERENT STARTING STATES, not a copy. SPIN_DEPTH is 2 and neither
    # GCFG2_CONFIG_SPIN_INITIAL_SKIP bit is set, so the engine loads both and searches from each,
    # keeping the better -- the reference data's two states differ in about half their bits.
    # Writing the same state to both throws away half the machine's search.
    states_in_a = [_vec(start)] * 512 + [_vec(final)]
    states_in_b = [_vec(start2)] * 512 + [_vec(final)]
    # states_out_N: gen_state_out_ref.py skips line 1 and takes the following 512. emit() passes
    # the START state as `ref_spins`, since nothing here solves the problem -- so these files are
    # a placeholder. VERIFICATION_TEST=1 compares the chip's result against them and would always
    # report FAIL; leave it at 0 and read the energies instead.
    states_out = ["# expected states"] + [_vec(final)] * 512

    written = []
    for core in (0, 1):
        idx = core + 1                       # model_1 = core 0, model_2 = core 1
        pair = (2 * core + 1, 2 * core + 2)  # clusters/states are two files per core
        files = {f"model_{idx}": model,
                 f"clusters_{pair[0]}": clusters_even,
                 f"clusters_{pair[1]}": clusters_odd}
        files[f"states_in_{pair[0]}"] = states_in_a
        files[f"states_in_{pair[1]}"] = states_in_b
        for f in pair:
            files[f"states_out_{f}"] = states_out
        for name, lines in files.items():
            (root / name).write_text("\n".join(lines) + "\n")
            written.append(name)

    return root, sorted(written), j_checksum(j_pad)


def resolve_start(start, n):
    """A start state as an n-length 0/1 array. Accepts a callable taking n, an array, or None."""
    if start is None:
        return zeros(n)
    spins = np.asarray(start(n) if callable(start) else start).astype(int)
    if spins.shape != (n,):
        sys.exit(f"start state has shape {spins.shape}; expected ({n},)")
    return spins


def quantise(problem, start):
    j_int, j_clipped = clamp(np.asarray(problem.j), LEVELS)
    np.fill_diagonal(j_int, 0)                       # the diagonal is the AU, never a coupling
    h_int, h_clipped = clamp(problem.h, LEVELS)

    spins = resolve_start(start, j_int.shape[0])
    return j_int, h_int, spins, (j_clipped, h_clipped)


def ground_truth(problem, j_int, h_int, j_clipped, scaling_h=1):
    """The known optimum, if the problem carries one. Returns (energy, cut_total), either None."""
    meta = problem.meta or {}
    cut_total = meta.get("maxcut_total_weight")

    if meta.get("planted_spins") is not None:
        # Recomputed from the QUANTISED matrix rather than taken on trust: clipping can in
        # principle break the planting guarantee.
        truth = integer_energy(j_int, h_int, (np.asarray(meta["planted_spins"]) > 0).astype(int),
                               scaling_h)
        print(f"  ground truth: {truth}   (planted)"
              f"{'  -- may be invalidated by clipping' if j_clipped else ''}")
        return truth, cut_total

    if cut_total is not None and meta.get("maxcut_optimum") is not None:
        # cut = (W - E)/2, so the certified optimum cut C sits at energy W - 2C.
        optimum = meta["maxcut_optimum"]
        truth = int(cut_total - 2 * optimum)
        print(f"  ground truth: {truth}   (certified optimum: cut {optimum:g}, "
              f"total weight {cut_total:g})")
        return truth, cut_total

    return None, cut_total


def emit(problem, folder, start=zeros, start2=None, flips="none"):
    """Quantise the problem, write it to tests/ref/data/<folder>/, and report what went in.

    `flips` is the spin-flip mask written into the cluster files -- "single" for single-spin
    moves, "none" for all-zero masks (nothing ever flips), or a callable for cluster moves.

    `start2` is the SECOND starting state. The hardware holds SPIN_DEPTH=2 initial states and
    searches from both, keeping the better, so leaving this None runs two identical searches and
    wastes half the machine. Pass a different state to use it -- the reference data's two states
    differ in roughly half their bits.
    """
    j_int, h_int, spins, (j_clipped, h_clipped) = quantise(problem, start)
    spins2 = spins if start2 is None else resolve_start(start2, j_int.shape[0])
    n = j_int.shape[0]
    if n > REF_SPINS:
        sys.exit(f"problem has {n} spins; the array holds {REF_SPINS}")

    nonzero = int((np.triu(j_int, 1) != 0).sum())
    meta = problem.meta or {}
    root, files, chk = write_ref_folder(folder, j_int, h_int, spins, spins2, spins, flips,
                                        float(meta.get("offset", 0.0)),
                                        int(meta.get("scaling_h", 1)))

    print(f"wrote {root}")
    print(f"  problem   : {(problem.meta or {}).get('name', '?')}")
    print(f"  size      : {n} spins, {nonzero} non-zero couplings, "
          f"mean degree {2.0 * nonzero / n:.1f}  (zero-padded to {REF_SPINS})")
    print(f"  clipping  : {j_clipped} J and {h_clipped} h values clipped to +/-{LEVELS}")
    scaling_h = int(meta.get("scaling_h", 1))
    same = bool(np.array_equal(spins, spins2))
    print(f"  start 0   : {integer_energy(j_int, h_int, spins, scaling_h):>8}   "
          f"{''.join(str(int(b)) for b in spins)}")
    print(f"  start 1   : {integer_energy(j_int, h_int, spins2, scaling_h):>8}   "
          f"{''.join(str(int(b)) for b in spins2)}"
          f"{'   (same as start 0 -- the two-slot search is running duplicates)' if same else ''}")
    if meta.get("compact_map"):
        lo, hi = meta["compacted_from"]
        print(f"  compacted : {n} active spins relabelled from scattered originals {lo}..{hi}")
    if meta.get("offset") or meta.get("scaling_h", 1) != 1:
        print(f"  offset    : {meta.get('offset', 0.0):g}   scaling factor h: "
              f"{meta.get('scaling_h', 1)}  (carried through unchanged)")
    print(f"  flips     : {flips if not callable(flips) else 'custom'}"
          f"{'   -- all-zero masks: nothing will ever flip' if flips in ('none', 'zero', None) else ''}")
    print(f"  placement : logical spin i at hardware index "
          f"{'i (mirrored, low cells)' if MIRROR_TO_LOW_SPINS else '255-i (raw ref layout)'}")
    print(f"  J checksum: 0x{chk:08x}  (the loader recomputes this from L1 and prints it back)")
    print(f"  files     : {len(files)} -- model, clusters, states_in, states_out, for both cores")
    truth, cut_total = ground_truth(problem, j_int, h_int, j_clipped, scaling_h)

    print()
    print(f"build against it with DATA_FOLDER={folder}")
    print()
    print("what good looks like (solved here, not checked on chip):")
    survey(j_int, h_int, spins, truth, cut_total, scaling_h)


def emit_sweep(problem, prefix, count, seed=0, min_distance=None, flips="none"):
    """Write `count` data folders for one problem, each with a different random start state.

    One folder per ELF: the in-ELF loop over states cannot refresh the capture memory, so a
    sweep is run as `count` separate builds instead. Folder n is `<prefix>_<nnn>` and its start
    is drawn from seed+n, redrawn while it sits closer than `min_distance` spins to the previous
    one (default n/4) so consecutive runs are never near-copies.

    Returns the folder names, in order -- run_sweep.sh consumes the same naming.
    """
    n = problem.n
    min_distance = n // 4 if min_distance is None else min_distance
    folders, previous = [], None
    for k in range(count):
        for attempt in range(64):
            state = random_state(n, seed=seed + k + 1000 * attempt)
            if previous is None or int(np.sum(state != previous)) >= min_distance:
                break
        else:
            print(f"  note      : start {k} never got {min_distance} spins from the previous one")
        folder = f"{prefix}_{k:03d}"
        print(f"\n--- {folder} ---")
        emit(problem, folder, start=state, flips=flips)
        folders.append(folder)
        previous = state
    print(f"\nwrote {len(folders)} folders: {folders[0]} .. {folders[-1]}")
    print(f"build and run them with: sw/tools/run_sweep.sh")
    return folders


def score(problem, text, start=zeros):
    """Report a pasted state's energy under the problem. Writes nothing."""
    j_int, h_int, spins, (j_clipped, _) = quantise(problem, start)
    scaling_h = int((problem.meta or {}).get("scaling_h", 1))
    n = j_int.shape[0]
    state, note = parse_state(text, n)

    print(f"scoring against {(problem.meta or {}).get('name', '?')} ({n} spins) -- nothing written")
    if note:
        print(f"  note      : {note}")
    print(f"  state     : {''.join(str(b) for b in state)}")
    print(f"  energy    : {integer_energy(j_int, h_int, state, scaling_h)}")
    print(f"  start     : {integer_energy(j_int, h_int, spins, scaling_h)}"
          f"  (this problem's start state)")
    truth, cut_total = ground_truth(problem, j_int, h_int, j_clipped, scaling_h)
    print()
    print("for reference, solved here:")
    survey(j_int, h_int, spins, truth, cut_total, scaling_h)
    return 0


# =============================================================================
# EDIT HERE
# =============================================================================

def main() -> int:

    name = "pm1d_80_0"
    problem = load_model(name, magnitude=3)

    # A sweep over start states: one data folder per state, one ELF per folder. Build and run
    # them with sw/tools/run_sweep.sh, whose PREFIX/COUNT must match the two arguments here.
    emit_sweep(problem, name, 10, seed=4)

    # A single run instead: pick the start yourself and write one folder.
    # emit(problem, "generated", start=random_state(problem.n, seed=0))
    # emit(problem, "generated", start=zeros)

    return 0


if __name__ == "__main__":
    sys.exit(main())

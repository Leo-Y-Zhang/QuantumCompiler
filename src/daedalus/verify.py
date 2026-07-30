"""Semantic equivalence checking up to global phase.

Method: simulate both circuits on a deterministic input set (computational
basis states, plus pseudo-random states from a fixed seed), fix a *single*
global phase from the first input, and require elementwise agreement under
that one phase on every input. Allowing a fresh phase per input would wrongly
accept relative-phase differences (e.g. ``z`` vs identity agrees on every
basis state up to a per-state phase); the shared phase plus random inputs
closes that hole.

This is a randomized check, not a formal proof: two inequivalent unitaries
could in principle agree on every sampled input, but for generic errors the
random states catch it with overwhelming probability.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from daedalus.ir import Circuit
from daedalus.sim import MAX_QUBITS, basis_state, random_state, simulate
from daedalus.unitary import PROOF_MAX_QUBITS, prove_circuit_equivalence

DEFAULT_SEED = 20260706
DEFAULT_ATOL = 1e-9


@dataclass(frozen=True)
class EquivalenceResult:
    """Outcome of an equivalence check."""

    equivalent: bool
    max_error: float
    inputs_checked: int
    detail: str = ""


def check_equivalence(
    original: Circuit,
    optimized: Circuit,
    *,
    num_random: int = 4,
    seed: int = DEFAULT_SEED,
    atol: float = DEFAULT_ATOL,
) -> EquivalenceResult:
    """Check that *optimized* equals *original* up to one global phase."""
    if original.num_qubits != optimized.num_qubits:
        return EquivalenceResult(
            equivalent=False,
            max_error=float("inf"),
            inputs_checked=0,
            detail="qubit counts differ",
        )
    inputs = _test_inputs(original.num_qubits, num_random, seed)
    phase: complex | None = None
    max_error = 0.0
    for state in inputs:
        out_original = simulate(original, initial=state)
        out_optimized = simulate(optimized, initial=state)
        if phase is None:
            k = max(range(len(out_original)), key=lambda i: abs(out_original[i]))
            phase = out_optimized[k] / out_original[k]
        error = max(
            abs(b - phase * a) for a, b in zip(out_original, out_optimized, strict=True)
        )
        max_error = max(max_error, error)
    equivalent = max_error <= atol
    return EquivalenceResult(
        equivalent=equivalent,
        max_error=max_error,
        inputs_checked=len(inputs),
        detail="" if equivalent else "outputs differ beyond tolerance",
    )


@dataclass(frozen=True)
class ProofResult:
    """A verification verdict plus the method used to reach it.

    ``method`` is ``"exact-unitary"`` when both circuits were small enough to
    materialize the full unitary (a genuine up-to-global-phase proof) or
    ``"randomized"`` when the sampled oracle was used instead. ``max_error`` is
    the aligned Frobenius difference norm for the exact method, or the maximum
    sampled amplitude error for the randomized one. ``process_fidelity`` is set
    only for the exact method.
    """

    equivalent: bool
    method: str
    max_error: float
    inputs_checked: int
    process_fidelity: float | None = None
    detail: str = ""

    def summary(self) -> str:
        """One-line human-readable verdict for the CLI."""
        verb = "equivalent up to global phase" if self.equivalent else "NOT equivalent"
        if self.method == "exact-unitary":
            fidelity = self.process_fidelity if self.process_fidelity is not None else 0.0
            return (
                f"proof: exact unitary check, {verb} "
                f"(diff norm {self.max_error:.3e}, process fidelity {fidelity:.10f}, "
                f"dimension {self.inputs_checked})"
            )
        return (
            f"proof: randomized check, {verb} "
            f"(max error {self.max_error:.3e}, {self.inputs_checked} inputs; "
            "circuit too large for an exact unitary proof)"
        )


def prove_equivalence(
    original: Circuit,
    optimized: Circuit,
    *,
    num_random: int = 4,
    seed: int = DEFAULT_SEED,
    atol: float = DEFAULT_ATOL,
) -> ProofResult:
    """Prove equivalence exactly when small, else via the randomized oracle.

    Uses the exact unitary engine when both circuits share a qubit count within
    :data:`~daedalus.unitary.PROOF_MAX_QUBITS`; otherwise falls back to
    :func:`check_equivalence`. Either way the verdict is up to global phase.
    """
    if original.num_qubits != optimized.num_qubits:
        return ProofResult(
            equivalent=False,
            method="exact-unitary",
            max_error=float("inf"),
            inputs_checked=0,
            detail="qubit counts differ",
        )
    if original.num_qubits <= PROOF_MAX_QUBITS:
        comparison = prove_circuit_equivalence(original, optimized, atol=atol)
        return ProofResult(
            equivalent=comparison.equivalent,
            method="exact-unitary",
            max_error=comparison.diff_norm,
            inputs_checked=comparison.dimension,
            process_fidelity=comparison.process_fidelity,
            detail="" if comparison.equivalent else "unitaries differ beyond tolerance",
        )
    randomized = check_equivalence(
        original, optimized, num_random=num_random, seed=seed, atol=atol
    )
    return ProofResult(
        equivalent=randomized.equivalent,
        method="randomized",
        max_error=randomized.max_error,
        inputs_checked=randomized.inputs_checked,
        detail=randomized.detail,
    )


def check_routing_equivalence(
    original: Circuit,
    routed: Circuit,
    final_layout: list[int],
    *,
    initial_layout: list[int] | None = None,
    num_random: int = 4,
    seed: int = DEFAULT_SEED,
    atol: float = DEFAULT_ATOL,
) -> EquivalenceResult:
    """Prove *routed* equals *original* up to the qubit permutation it induces.

    The router reports ``final_layout`` with ``final_layout[l]`` = the physical
    qubit that carries logical ``l`` at the end. ``initial_layout`` says where
    each logical qubit *starts*; ``None`` means the trivial layout (logical
    qubit ``l`` on physical qubit ``l``), which is what the greedy router uses —
    the sabre router chooses its own placement and must pass it here. This
    checks, on the standard basis + seeded-random input battery, that routing on
    physical wires reproduces the original logical computation once the inputs
    are placed through ``initial_layout`` and the outputs read back through
    ``final_layout`` (up to one global phase).
    """
    n = original.num_qubits
    m = routed.num_qubits
    if len(final_layout) != n or m < n or sorted(set(final_layout)) != sorted(final_layout):
        return EquivalenceResult(
            equivalent=False,
            max_error=float("inf"),
            inputs_checked=0,
            detail="invalid final layout for the given circuits",
        )
    if initial_layout is not None and (
        len(initial_layout) != n
        or sorted(set(initial_layout)) != sorted(initial_layout)
        or not all(0 <= p < m for p in initial_layout)
    ):
        return EquivalenceResult(
            equivalent=False,
            max_error=float("inf"),
            inputs_checked=0,
            detail="invalid initial layout for the given circuits",
        )
    inputs = _test_inputs(n, num_random, seed)
    phase: complex | None = None
    max_error = 0.0
    for state in inputs:
        out_logical = simulate(original, initial=state)
        if initial_layout is None:
            placed = _embed(state, n, m)
        else:
            placed = _permute_embed(state, n, m, initial_layout)
        out_routed = simulate(routed, initial=placed)
        expected = _permute_embed(out_logical, n, m, final_layout)
        if phase is None:
            k = max(range(len(expected)), key=lambda i: abs(expected[i]))
            phase = out_routed[k] / expected[k] if abs(expected[k]) > 0 else 1.0
        error = max(abs(b - phase * a) for a, b in zip(expected, out_routed, strict=True))
        max_error = max(max_error, error)
    equivalent = max_error <= atol
    return EquivalenceResult(
        equivalent=equivalent,
        max_error=max_error,
        inputs_checked=len(inputs),
        detail="" if equivalent else "routed outputs differ beyond tolerance",
    )


def _embed(state: list[complex], n: int, m: int) -> list[complex]:
    """Embed an ``n``-qubit state into ``m`` physical qubits (identity layout).

    Logical qubit ``l`` starts on physical qubit ``l`` and the extra physical
    qubits start in ``|0>``, so this is a zero-pad to length ``2**m``.
    """
    padded = [0j] * (1 << m)
    padded[: len(state)] = state
    return padded


def _permute_embed(
    state: list[complex], n: int, m: int, final_layout: list[int]
) -> list[complex]:
    """Relabel an ``n``-qubit state onto ``m`` physical wires via *final_layout*.

    Amplitude for logical configuration ``y`` moves to the physical index whose
    bit ``final_layout[l]`` equals bit ``l`` of ``y`` (unused physical qubits 0).
    """
    out = [0j] * (1 << m)
    for y, amp in enumerate(state):
        z = 0
        for logical in range(n):
            if (y >> logical) & 1:
                z |= 1 << final_layout[logical]
        out[z] = amp
    return out


def _test_inputs(num_qubits: int, num_random: int, seed: int) -> list[list[complex]]:
    """Deterministic input battery: basis states plus seeded random states."""
    if num_qubits > MAX_QUBITS:
        raise ValueError(f"equivalence checking supports at most {MAX_QUBITS} qubits")
    dimension = 1 << num_qubits
    if num_qubits <= 3:
        indices: list[int] = list(range(dimension))
    else:
        indices = sorted({0, dimension - 1, *(1 << q for q in range(num_qubits))})
    inputs = [basis_state(num_qubits, i) for i in indices]
    rng = random.Random(seed)
    inputs.extend(random_state(num_qubits, rng) for _ in range(num_random))
    return inputs

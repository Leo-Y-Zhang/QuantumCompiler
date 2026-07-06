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

from qforge.ir import Circuit
from qforge.sim import MAX_QUBITS, basis_state, random_state, simulate

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
            abs(b - phase * a) for a, b in zip(out_original, out_optimized)
        )
        max_error = max(max_error, error)
    equivalent = max_error <= atol
    return EquivalenceResult(
        equivalent=equivalent,
        max_error=max_error,
        inputs_checked=len(inputs),
        detail="" if equivalent else "outputs differ beyond tolerance",
    )


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

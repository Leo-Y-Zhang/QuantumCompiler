"""Exact circuit-unitary construction and up-to-global-phase comparison.

Where :mod:`daedalus.verify` *samples* inputs, this module materializes the
full ``2**n x 2**n`` unitary of a circuit and compares two unitaries exactly.
For circuits small enough to build the matrix (see :data:`PROOF_MAX_QUBITS`)
this is a genuine proof of equivalence up to global phase, not a randomized
check: two inequivalent unitaries always produce a non-zero difference norm.

The ``i``-th column of the unitary is the circuit applied to the ``i``-th
computational basis state, so construction reuses the statevector simulator
directly and inherits its gate semantics — there is no second matrix-algebra
implementation to keep in sync with :mod:`daedalus.sim`.
"""

from __future__ import annotations

from dataclasses import dataclass

from daedalus.ir import Circuit
from daedalus.sim import basis_state, simulate

#: Largest circuit the exact engine will materialize (``2**7 = 128`` columns).
#: Above this the difference norm is still well defined but the memory and time
#: cost grow as ``4**n``; callers fall back to the randomized oracle instead.
PROOF_MAX_QUBITS = 7

#: Default tolerance on the aligned Frobenius difference norm.
DEFAULT_ATOL = 1e-9

Matrix = list[list[complex]]


@dataclass(frozen=True)
class UnitaryComparison:
    """Result of an exact up-to-global-phase unitary comparison."""

    equivalent: bool
    diff_norm: float
    process_fidelity: float
    dimension: int


def circuit_unitary(circuit: Circuit) -> Matrix:
    """Return the exact ``2**n x 2**n`` unitary of *circuit* (row-major).

    Raises :class:`ValueError` if the circuit has more than
    :data:`PROOF_MAX_QUBITS` qubits.
    """
    n = circuit.num_qubits
    if n > PROOF_MAX_QUBITS:
        raise ValueError(
            f"exact unitary supports at most {PROOF_MAX_QUBITS} qubits, got {n}"
        )
    dim = 1 << n
    # Column j is the circuit applied to |j>; assemble into a row-major matrix.
    columns = [simulate(circuit, initial=basis_state(n, j)) for j in range(dim)]
    return [[columns[j][i] for j in range(dim)] for i in range(dim)]


def compare_unitaries(a: Matrix, b: Matrix, *, atol: float = DEFAULT_ATOL) -> UnitaryComparison:
    """Compare *a* and *b* exactly up to a single global phase.

    A shared global phase is fixed from the largest-magnitude entry of *a* (so a
    relative-phase difference cannot be absorbed away), then the Frobenius norm
    of ``b - phase * a`` and the process fidelity ``|Tr(b^dagger a)| / dim`` are
    reported. ``equivalent`` is true when the aligned difference norm is within
    *atol*.
    """
    dim = len(a)
    if len(b) != dim:
        return UnitaryComparison(False, float("inf"), 0.0, dim)

    # Global-phase alignment from the max-magnitude entry of a.
    best = 0.0
    ref_i = ref_j = 0
    for i in range(dim):
        for j in range(dim):
            mag = abs(a[i][j])
            if mag > best:
                best, ref_i, ref_j = mag, i, j
    phase = b[ref_i][ref_j] / a[ref_i][ref_j] if best > 0 else 1.0

    diff_sq = 0.0
    trace = 0j
    for i in range(dim):
        for j in range(dim):
            diff_sq += abs(b[i][j] - phase * a[i][j]) ** 2
            trace += b[i][j].conjugate() * a[i][j]
    diff_norm = diff_sq**0.5
    process_fidelity = abs(trace) / dim if dim else 0.0
    return UnitaryComparison(diff_norm <= atol, diff_norm, process_fidelity, dim)


def prove_circuit_equivalence(
    original: Circuit, optimized: Circuit, *, atol: float = DEFAULT_ATOL
) -> UnitaryComparison:
    """Exact up-to-global-phase equivalence proof for two circuits.

    Returns a non-equivalent verdict (infinite diff norm) if the qubit counts
    differ; raises :class:`ValueError` if either circuit is too large for the
    exact engine.
    """
    if original.num_qubits != optimized.num_qubits:
        return UnitaryComparison(False, float("inf"), 0.0, 1 << original.num_qubits)
    return compare_unitaries(
        circuit_unitary(original), circuit_unitary(optimized), atol=atol
    )

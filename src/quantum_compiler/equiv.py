"""Standalone two-circuit equivalence proving with counterexample shrinking.

``quantum-compiler equiv A B`` needs three things beyond what :mod:`quantum_compiler.verify`
already provides. The *verdict* is pure reuse: the same
:func:`~quantum_compiler.verify.prove_equivalence` oracle that certifies the optimizer
and the router (exact unitary proof when small, randomized battery otherwise).
On a negative verdict this module adds a *witness* — a concrete input on which
the two circuits demonstrably disagree — and a *shrunk form* of the failing
pair: the classic ddmin delta-debugging algorithm (Zeller & Hildebrandt 2002)
applied jointly to both gate lists, so the disagreement is pinned to as few
gates as possible.

Phase convention
----------------
A witness is only meaningful relative to a phase convention, because circuits
are compared up to one global phase. This module uses the oracle's convention:
the phase is fixed once from the first battery input, and every reported error
is ``|B(x) - phase * A(x)|`` under that single shared phase (see
:mod:`quantum_compiler.verify` for why a per-input phase would be unsound). One
refinement for reproducibility: the anchor amplitude is the *lowest* index
whose magnitude is within ``1e-9`` of the first input's peak, so near-ties
(e.g. the two 1/sqrt(2) amplitudes of a GHZ state) do not let platform
rounding pick the anchor. For genuinely equivalent circuits every near-peak
anchor yields the same phase, so this never changes a verdict. For circuits
that *disagree* the anchor ratio need not have magnitude 1 — B can even vanish
where A peaks, making the factor 0; the CLI labels such factors explicitly
instead of presenting a magnitude-0 number as a phase.

Minimality
----------
The shrunk pair is **1-minimal**: removing any single remaining gate from
either circuit makes the pair equivalent again. That is ddmin's termination
guarantee. It is a *minimal explanation* of the disagreement, not necessarily
the globally smallest one, and not necessarily the textual diff of the two
programs — e.g. for ``[h, cx, x]`` vs ``[h, cx]`` a perfectly valid 1-minimal
core is ``[h]`` vs the empty circuit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from quantum_compiler.ir import Circuit
from quantum_compiler.sim import simulate
from quantum_compiler.verify import DEFAULT_ATOL, DEFAULT_SEED, _test_inputs, prove_equivalence

#: One removable unit for the delta debugger: (circuit id, original gate index).
Delta = tuple[str, int]


@dataclass(frozen=True)
class Witness:
    """An input on which two circuits disagree beyond tolerance.

    ``max_error`` is ``max_i |output_b[i] - phase * output_a[i]|`` where
    ``phase`` is the single shared alignment phase fixed on the first battery
    input (the oracle's convention), and ``worst_index`` is an amplitude index
    achieving that maximum.
    """

    input_index: int
    basis_index: int | None
    input_state: list[complex]
    output_a: list[complex]
    output_b: list[complex]
    phase: complex
    max_error: float
    worst_index: int

    def label(self) -> str:
        """Human-readable input name: ``|01>`` (q1=0, q0=1) or a random tag."""
        if self.basis_index is None:
            return f"random input #{self.input_index}"
        num_qubits = len(self.input_state).bit_length() - 1
        return format_basis(self.basis_index, num_qubits)


@dataclass(frozen=True)
class ShrinkResult:
    """A 1-minimal still-disagreeing pair produced by :func:`shrink_counterexample`."""

    circuit_a: Circuit
    circuit_b: Circuit
    gates_before: int
    gates_after: int
    oracle_calls: int


def format_basis(index: int, num_qubits: int) -> str:
    """Format a basis-state index as a ket, most significant qubit first."""
    if num_qubits <= 0:
        return "|0>"
    return f"|{index:0{num_qubits}b}>"


def find_witness(
    a: Circuit,
    b: Circuit,
    *,
    num_random: int = 4,
    seed: int = DEFAULT_SEED,
    atol: float = DEFAULT_ATOL,
) -> Witness | None:
    """Search the oracle's input battery for an input where *a* and *b* disagree.

    Returns the first battery input whose phase-aligned error exceeds *atol* —
    basis states come first in the battery, so witnesses come out as simple as
    possible — or ``None`` when every battery input agrees to within *atol*.
    A ``None`` alongside a negative verdict does not contradict the oracle.
    Above 3 qubits the sampled battery can simply miss the difference; and at
    *any* size the exact engine accumulates a Frobenius norm over the whole
    unitary, which can cross *atol* even though no single amplitude of any one
    input does (only reachable within about a ``2**(n/2)`` factor of *atol*).
    Either way the exact-unitary verdict is the authority on equivalence.
    """
    if a.num_qubits != b.num_qubits:
        return None
    inputs = _test_inputs(a.num_qubits, num_random, seed)
    phase: complex | None = None
    for input_index, state in enumerate(inputs):
        output_a = simulate(a, initial=state)
        output_b = simulate(b, initial=state)
        if phase is None:
            magnitudes = [abs(amp) for amp in output_a]
            peak = max(magnitudes)
            anchor = next(i for i, mag in enumerate(magnitudes) if mag >= peak - 1e-9)
            phase = output_b[anchor] / output_a[anchor]
        errors = [
            abs(bb - phase * aa) for aa, bb in zip(output_a, output_b, strict=True)
        ]
        worst_index = max(range(len(errors)), key=errors.__getitem__)
        if errors[worst_index] > atol:
            return Witness(
                input_index=input_index,
                basis_index=_basis_index(state),
                input_state=state,
                output_a=output_a,
                output_b=output_b,
                phase=phase,
                max_error=errors[worst_index],
                worst_index=worst_index,
            )
    return None


def shrink_counterexample(
    a: Circuit,
    b: Circuit,
    *,
    num_random: int = 4,
    seed: int = DEFAULT_SEED,
    atol: float = DEFAULT_ATOL,
) -> ShrinkResult:
    """Delta-debug the failing pair ``(a, b)`` to a 1-minimal disagreeing pair.

    Runs ddmin over the *union* of both gate lists: each delta is one gate of
    either circuit, and a candidate subset "fails" when the reduced pair is
    still not equivalent according to the same oracle that produced the
    verdict (:func:`~quantum_compiler.verify.prove_equivalence` — exact when small).
    The registers (qubit/bit counts) are never shrunk.

    Raises :class:`ValueError` when the oracle finds the pair equivalent —
    there is nothing to shrink then. ``oracle_calls`` counts distinct oracle
    invocations (repeat candidates are served from a cache).
    """
    if a.num_qubits != b.num_qubits:
        raise ValueError("cannot shrink: the circuits have different qubit counts")
    calls = 0
    cache: dict[frozenset[Delta], bool] = {}

    def still_failing(kept: list[Delta]) -> bool:
        nonlocal calls
        key = frozenset(kept)
        if key not in cache:
            calls += 1
            oracle = prove_equivalence(
                _subsequence(a, "a", key),
                _subsequence(b, "b", key),
                num_random=num_random,
                seed=seed,
                atol=atol,
            )
            cache[key] = not oracle.equivalent
        return cache[key]

    deltas: list[Delta] = [("a", i) for i in range(len(a.gates))]
    deltas += [("b", i) for i in range(len(b.gates))]
    if not still_failing(deltas):
        raise ValueError("cannot shrink: the oracle finds the circuits equivalent")
    kept = _ddmin(deltas, still_failing)
    kept_set = frozenset(kept)
    return ShrinkResult(
        circuit_a=_subsequence(a, "a", kept_set),
        circuit_b=_subsequence(b, "b", kept_set),
        gates_before=len(deltas),
        gates_after=len(kept),
        oracle_calls=calls,
    )


def _basis_index(state: list[complex]) -> int | None:
    """Return ``i`` when *state* is exactly the basis state ``|i>``, else None."""
    nonzero = [i for i, amp in enumerate(state) if abs(amp) > 1e-12]
    if len(nonzero) == 1 and abs(state[nonzero[0]] - 1) < 1e-12:
        return nonzero[0]
    return None


def _subsequence(circuit: Circuit, side: str, kept: frozenset[Delta]) -> Circuit:
    """Keep only the gates of *circuit* whose ``(side, index)`` delta survives."""
    return circuit.replace_gates(
        gate for index, gate in enumerate(circuit.gates) if (side, index) in kept
    )


def _ddmin(deltas: list[Delta], failing: Callable[[list[Delta]], bool]) -> list[Delta]:
    """Classic ddmin: minimize *deltas* while ``failing`` holds.

    Invariants: ``failing(deltas)`` is true on entry and the empty set passes
    (two empty same-register circuits are equivalent). Termination at
    granularity == len(deltas) has tested every single-delta removal, which is
    exactly the 1-minimality guarantee documented on the module.
    """
    granularity = 2
    while len(deltas) >= 2:
        subsets = _partition(deltas, granularity)
        reduced = False
        for subset in subsets:
            if failing(subset):
                deltas, granularity, reduced = subset, 2, True
                break
        if not reduced:
            for subset in subsets:
                exclude = set(subset)
                complement = [d for d in deltas if d not in exclude]
                if failing(complement):
                    deltas = complement
                    granularity = max(granularity - 1, 2)
                    reduced = True
                    break
        if not reduced:
            if granularity >= len(deltas):
                break
            granularity = min(len(deltas), granularity * 2)
    return deltas


def _partition(deltas: list[Delta], count: int) -> list[list[Delta]]:
    """Split *deltas* into *count* contiguous, near-equal, non-empty chunks."""
    size, extra = divmod(len(deltas), count)
    chunks: list[list[Delta]] = []
    start = 0
    for i in range(count):
        end = start + size + (1 if i < extra else 0)
        if end > start:
            chunks.append(deltas[start:end])
        start = end
    return chunks

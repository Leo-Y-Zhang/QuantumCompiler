"""Adjacent inverse-pair cancellation.

Two gates cancel when they are inverses of each other and adjacent on every
wire they touch (no intervening gate on any shared qubit). Implemented with
one per-qubit stack of not-yet-cancelled gates, so nested chains such as
``x y y x`` collapse fully in a single run. ``measure`` and rotations are
pushed as blockers and never matched (rotation pairs belong to the
merge-rotations pass).
"""

from __future__ import annotations

from qforge.ir import Circuit, Gate

_INVERSE = {
    "h": "h",
    "x": "x",
    "y": "y",
    "z": "z",
    "s": "sdg",
    "sdg": "s",
    "t": "tdg",
    "tdg": "t",
    "cx": "cx",
    "cz": "cz",
    "swap": "swap",
}
#: Gates whose operand order does not matter for equality.
_SYMMETRIC = frozenset({"cz", "swap"})


class CancelInverses:
    """Remove adjacent inverse pairs (h h, x x, cx cx, s sdg, t tdg, ...)."""

    name = "cancel-inverses"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with all adjacent inverse pairs removed."""
        gates = circuit.gates
        alive = [True] * len(gates)
        stacks: dict[int, list[int]] = {q: [] for q in range(circuit.num_qubits)}
        for i, gate in enumerate(gates):
            previous = _matching_predecessor(gate, gates, stacks)
            if previous is not None:
                alive[i] = alive[previous] = False
                for q in gate.qubits:
                    stacks[q].pop()
            else:
                for q in gate.qubits:
                    stacks[q].append(i)
        if all(alive):
            return circuit
        return circuit.replace_gates(g for i, g in enumerate(gates) if alive[i])


def _matching_predecessor(
    gate: Gate, gates: list[Gate], stacks: dict[int, list[int]]
) -> int | None:
    """Index of an immediately-preceding inverse of *gate*, or ``None``."""
    inverse_name = _INVERSE.get(gate.name)
    if inverse_name is None:
        return None
    tops = {stacks[q][-1] for q in gate.qubits if stacks[q]}
    if len(tops) != 1:
        return None
    p = tops.pop()
    if not all(stacks[q] and stacks[q][-1] == p for q in gate.qubits):
        return None
    previous = gates[p]
    if previous.name != inverse_name:
        return None
    if gate.name in _SYMMETRIC:
        if set(previous.qubits) != set(gate.qubits):
            return None
    elif previous.qubits != gate.qubits:
        return None
    return p

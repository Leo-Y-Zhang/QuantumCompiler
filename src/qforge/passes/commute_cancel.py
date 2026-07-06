"""Commutation-aware cancellation of z-basis diagonal gates.

Why it is sound: ``cx = P0 (x) I + P1 (x) X`` in the (control, target)
factorization, where ``P0``/``P1`` are computational-basis projectors. Any
gate diagonal in the computational basis on the *control* qubit commutes with
both projectors, hence with the whole cx. ``cz`` is itself diagonal, so
diagonal gates commute through *either* of its qubits.

The pass scans each wire: a diagonal gate may slide forward across such
"transparent" gates; if the first non-transparent gate it meets on the wire
is a matching diagonal partner, the pair cancels (z z, s sdg, t tdg) or
merges (rz rz). Anything else - a cx *target*, h, rx, measure - blocks.
"""

from __future__ import annotations

from dataclasses import replace

from qforge.ir import Circuit, Gate
from qforge.passes.merge_rotations import is_zero_mod_two_pi

_DIAGONAL = frozenset({"z", "s", "sdg", "t", "tdg", "rz"})
_INVERSE_PAIRS = frozenset({("z", "z"), ("s", "sdg"), ("sdg", "s"), ("t", "tdg"), ("tdg", "t")})


def _is_transparent(gate: Gate, q: int) -> bool:
    """True when a diagonal gate on *q* commutes through *gate*."""
    if gate.name == "cx":
        return gate.qubits[0] == q
    return gate.name == "cz" and q in gate.qubits


class CommuteCancel:
    """Cancel/merge diagonal gates separated only by cx controls or cz."""

    name = "commute-cancel"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with commutation-enabled diagonal pairs reduced."""
        gates: list[Gate | None] = list(circuit.gates)
        changed = False
        for q, wire in circuit.qubit_wires().items():
            for position in range(len(wire)):
                first = gates[wire[position]]
                if first is None or first.name not in _DIAGONAL:
                    continue
                if _try_reduce(q, wire, position, gates):
                    changed = True
        if not changed:
            return circuit
        return circuit.replace_gates(g for g in gates if g is not None)


def _try_reduce(q: int, wire: list[int], position: int, gates: list[Gate | None]) -> bool:
    """Slide the diagonal gate at ``wire[position]`` forward; reduce if possible."""
    i = wire[position]
    first = gates[i]
    assert first is not None
    for j in wire[position + 1 :]:
        second = gates[j]
        if second is None:
            continue
        if _is_transparent(second, q):
            continue
        if second.name in _DIAGONAL:
            if first.name == "rz" and second.name == "rz":
                total = (first.angle or 0.0) + (second.angle or 0.0)
                gates[j] = None
                gates[i] = None if is_zero_mod_two_pi(total) else replace(first, angle=total)
                return True
            if (first.name, second.name) in _INVERSE_PAIRS:
                gates[i] = gates[j] = None
                return True
        return False
    return False

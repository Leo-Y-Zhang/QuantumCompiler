"""Adjacent rotation merging: r(a) then r(b) on the same wire -> r(a+b).

A merged rotation whose angle is 0 modulo 2*pi (within EPSILON) is dropped
entirely. Dropping is exact for angle 0 and a global-phase change for angle
2*pi (``r(2*pi) = -I`` for rx/ry/rz), which the equivalence checker accepts
by design.
"""

from __future__ import annotations

import math
from dataclasses import replace

from qforge.ir import Circuit, Gate

_ROTATIONS = frozenset({"rx", "ry", "rz"})
EPSILON = 1e-9


def is_zero_mod_two_pi(angle: float) -> bool:
    """True when *angle* is 0 modulo 2*pi within :data:`EPSILON`."""
    return abs(math.remainder(angle, math.tau)) <= EPSILON


class MergeRotations:
    """Merge adjacent same-axis rotations on the same qubit."""

    name = "merge-rotations"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with adjacent same-axis rotations merged."""
        gates: list[Gate | None] = list(circuit.gates)
        last: dict[int, int] = {}
        changed = False
        for i, gate in enumerate(circuit.gates):
            if gate.name not in _ROTATIONS:
                for q in gate.qubits:
                    last.pop(q, None)
                continue
            q = gate.qubits[0]
            p = last.get(q)
            previous = gates[p] if p is not None else None
            if p is not None and previous is not None and previous.name == gate.name:
                total = (previous.angle or 0.0) + (gate.angle or 0.0)
                gates[i] = None
                changed = True
                if is_zero_mod_two_pi(total):
                    gates[p] = None
                    last.pop(q, None)
                else:
                    gates[p] = replace(previous, angle=total)
            else:
                last[q] = i
        if not changed:
            return circuit
        return circuit.replace_gates(g for g in gates if g is not None)

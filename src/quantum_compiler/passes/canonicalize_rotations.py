"""Lower special-angle rotations to named Clifford+T gates.

A rotation whose angle is (modulo 2*pi) one of the Clifford+T special values is
equal *up to global phase* to a single named gate, which the equivalence
checker accepts:

- ``rz(pi/2) = S``, ``rz(-pi/2) = Sdg``, ``rz(pi) = Z``,
  ``rz(pi/4) = T``, ``rz(-pi/4) = Tdg``
- ``rx(pi) = X``, ``ry(pi) = Y``
- any rotation that is 0 modulo 2*pi is the identity and is dropped

This gives circuits a canonical Clifford+T normal form and exposes further
cancellations (an ``rz(pi/2)`` written next to an ``sdg`` becomes an ``s sdg``
pair the cancel-inverses pass can remove). Generic angles are left untouched.

Ordering: this runs *after* the peephole pass in the default pipeline, so a
``h rz(pi/4) h`` window is rewritten to ``rx(pi/4)`` before its ``rz`` could be
frozen into a ``t`` (see :func:`quantum_compiler.passes.default_passes`).
"""

from __future__ import annotations

import math

from quantum_compiler.ir import Circuit, Gate
from quantum_compiler.passes.merge_rotations import EPSILON

_ROTATIONS = frozenset({"rx", "ry", "rz"})

#: ``rz`` special angles (reduced to ``(-pi, pi]``) mapped to their named gate.
_RZ_ANGLES = [
    (math.pi / 2, "s"),
    (-math.pi / 2, "sdg"),
    (math.pi, "z"),
    (math.pi / 4, "t"),
    (-math.pi / 4, "tdg"),
]
#: For ``rx``/``ry`` only the pi rotation has a named (Pauli) form.
_PI_GATE = {"rx": "x", "ry": "y"}


def _named_for(axis: str, reduced_angle: float) -> str | None:
    """Named Clifford+T gate for a non-identity rotation, or ``None`` to keep it.

    *reduced_angle* is the rotation angle already reduced to ``(-pi, pi]`` and
    known to be non-zero.
    """
    if axis == "rz":
        for angle, name in _RZ_ANGLES:
            if abs(math.remainder(reduced_angle - angle, math.tau)) <= EPSILON:
                return name
        return None
    if abs(math.remainder(reduced_angle - math.pi, math.tau)) <= EPSILON:
        return _PI_GATE[axis]
    return None


class CanonicalizeRotations:
    """Rewrite special-angle rotations to named Clifford+T gates."""

    name = "canonicalize-rotations"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with special-angle rotations lowered/dropped."""
        new_gates: list[Gate] = []
        changed = False
        for gate in circuit.gates:
            if gate.name not in _ROTATIONS:
                new_gates.append(gate)
                continue
            reduced = math.remainder(gate.angle or 0.0, math.tau)  # in [-pi, pi]
            if abs(reduced) <= EPSILON:
                changed = True  # identity rotation: drop it
                continue
            name = _named_for(gate.name, reduced)
            if name is None:
                new_gates.append(gate)
            else:
                new_gates.append(Gate(name, gate.qubits))
                changed = True
        if not changed:
            return circuit
        return circuit.replace_gates(new_gates)

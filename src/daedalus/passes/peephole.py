"""Peephole identities on three-gate windows of a single wire.

Rewrites the Hadamard-conjugation family ``h g h -> g'`` where ``h g h``
equals a single named gate up to global phase:

- Paulis: ``h x h -> z``, ``h z h -> x``, ``h y h -> y`` (the last is
  ``-y``, a global-phase change the equivalence checker accepts).
- Basis-change rotations: ``h rz(a) h -> rx(a)``, ``h rx(a) h -> rz(a)``,
  ``h ry(a) h -> ry(-a)``.

A window qualifies only when all three gates are single-qubit gates
consecutive on that qubit's wire; the replacement is placed in the middle
slot, which is safe because single-qubit gates on one wire have no ordering
constraints against other wires.
"""

from __future__ import annotations

from daedalus.ir import Circuit, Gate

#: Constant-gate conjugations: ``("h", name, "h") -> replacement name``.
_PAULI_REWRITES = {("h", "x", "h"): "z", ("h", "z", "h"): "x", ("h", "y", "h"): "y"}
#: Rotation conjugations: ``rotation name -> (replacement name, angle sign)``.
_ROTATION_REWRITES = {"rz": ("rx", 1.0), "rx": ("rz", 1.0), "ry": ("ry", -1.0)}


class Peephole:
    """Apply Hadamard-conjugation identities on single-qubit wire windows."""

    name = "peephole"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with all non-overlapping peephole matches applied."""
        gates: list[Gate | None] = list(circuit.gates)
        changed = False
        wires = circuit.qubit_wires()
        for q in range(circuit.num_qubits):
            wire = wires[q]
            k = 0
            while k + 2 < len(wire):
                window = [gates[wire[k + offset]] for offset in range(3)]
                replacement = _match(window, q)
                if replacement is not None:
                    gates[wire[k]] = None
                    gates[wire[k + 1]] = replacement
                    gates[wire[k + 2]] = None
                    changed = True
                    k += 3
                else:
                    k += 1
        if not changed:
            return circuit
        return circuit.replace_gates(g for g in gates if g is not None)


def _match(window: list[Gate | None], qubit: int) -> Gate | None:
    """Replacement gate if *window* matches a rewrite on *qubit*, else ``None``."""
    if any(g is None or len(g.qubits) != 1 for g in window):
        return None
    outer, inner, closing = (g for g in window if g is not None)
    if outer.name != "h" or closing.name != "h":
        return None
    pauli = _PAULI_REWRITES.get((outer.name, inner.name, closing.name))
    if pauli is not None:
        return Gate(pauli, (qubit,))
    rotation = _ROTATION_REWRITES.get(inner.name)
    if rotation is not None:
        name, sign = rotation
        return Gate(name, (qubit,), angle=sign * (inner.angle or 0.0))
    return None

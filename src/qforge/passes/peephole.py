"""Peephole identities on three-gate windows of a single wire.

Rewrites ``h x h -> z`` and ``h z h -> x``. A window qualifies only when all
three gates are single-qubit gates consecutive on that qubit's wire; the
replacement is placed in the middle slot, which is safe because single-qubit
gates on one wire have no ordering constraints against other wires.
"""

from __future__ import annotations

from qforge.ir import Circuit, Gate

_REWRITES = {("h", "x", "h"): "z", ("h", "z", "h"): "x"}


class Peephole:
    """Apply h x h -> z and h z h -> x on single-qubit wire windows."""

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
                replacement = _match(window)
                if replacement is not None:
                    gates[wire[k]] = None
                    gates[wire[k + 1]] = Gate(replacement, (q,))
                    gates[wire[k + 2]] = None
                    changed = True
                    k += 3
                else:
                    k += 1
        if not changed:
            return circuit
        return circuit.replace_gates(g for g in gates if g is not None)


def _match(window: list[Gate | None]) -> str | None:
    """Replacement gate name if *window* matches a rewrite, else ``None``."""
    if any(g is None or len(g.qubits) != 1 for g in window):
        return None
    names = tuple(g.name for g in window if g is not None)
    return _REWRITES.get(names)

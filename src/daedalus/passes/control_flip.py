"""Reverse a cx by absorbing a Hadamard sandwich.

The identity ``(H (x) H) . CX(a, b) . (H (x) H) == CX(b, a)`` lets a cx flanked
by Hadamards on *both* of its wires be rewritten to a single reversed cx,
turning five gates into one. This is the standard trick for changing a cx's
direction (e.g. to match a hardware coupling arrow) and often exposes further
cancellation once two cx gates share a direction.

Matching is anchored on each cx: the gate immediately before and after it on the
control wire, and the gate immediately before and after it on the target wire,
must all be ``h``. Those four Hadamards are consumed and the cx's operands are
swapped in place. cx gates are visited in program order; Hadamards already
consumed by one rewrite cannot be reused by another.
"""

from __future__ import annotations

from daedalus.ir import Circuit, Gate


class ControlFlip:
    """Rewrite ``h h cx h h`` sandwiches to a single reversed cx."""

    name = "control-flip"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with Hadamard-sandwiched cx gates reversed."""
        gates: list[Gate | None] = list(circuit.gates)
        wires = circuit.qubit_wires()
        positions = {q: {idx: p for p, idx in enumerate(wire)} for q, wire in wires.items()}
        changed = False
        for k, gate in enumerate(circuit.gates):
            if gate.name != "cx":
                continue
            control, target = gate.qubits
            neighbours = _sandwich_hadamards(k, control, target, wires, positions, gates)
            if neighbours is None:
                continue
            for h_index in neighbours:
                gates[h_index] = None
            gates[k] = Gate("cx", (target, control))
            changed = True
        if not changed:
            return circuit
        return circuit.replace_gates(g for g in gates if g is not None)


def _sandwich_hadamards(
    k: int,
    control: int,
    target: int,
    wires: dict[int, list[int]],
    positions: dict[int, dict[int, int]],
    gates: list[Gate | None],
) -> list[int] | None:
    """Return the four flanking Hadamard indices, or ``None`` if not a sandwich."""
    found: list[int] = []
    for q in (control, target):
        wire = wires[q]
        p = positions[q][k]
        if p == 0 or p + 1 >= len(wire):
            return None
        before, after = wire[p - 1], wire[p + 1]
        gb, ga = gates[before], gates[after]
        if gb is None or ga is None or gb.name != "h" or ga.name != "h":
            return None
        found.extend((before, after))
    return found

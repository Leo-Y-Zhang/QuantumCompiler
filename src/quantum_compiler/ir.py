"""Gate-list IR with per-qubit wire ordering.

Why this is effectively a DAG
-----------------------------
The IR stores gates as a flat list in program order, but the *meaningful*
ordering constraints are only per qubit: two gates must keep their relative
order iff they share a qubit (gates on disjoint qubit sets commute trivially
as tensor-product operators). Interpreting each gate as a node with an edge
from A to B whenever A immediately precedes B on some shared wire yields a
dependency DAG, and any topological order of that DAG denotes the same
operator. Optimization passes therefore only need to respect the per-wire
sequences exposed by :meth:`Circuit.qubit_wires`; the flat list is simply one
convenient topological order. ``measure`` operations participate as ordinary
(order-blocking) nodes on their wire.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from quantum_compiler.angles import format_angle


@dataclass(frozen=True)
class Gate:
    """One IR operation: a named gate applied to an ordered qubit tuple.

    ``angle`` is set only for rx/ry/rz; ``bit`` only for measure.
    """

    name: str
    qubits: tuple[int, ...]
    angle: float | None = None
    bit: int | None = None


@dataclass
class Circuit:
    """A parsed program: register sizes plus the gate list (see module doc)."""

    num_qubits: int
    num_bits: int
    gates: list[Gate] = field(default_factory=list)

    def gate_counts(self) -> dict[str, int]:
        """Return ``{gate name: count}`` sorted by name (deterministic)."""
        counts: dict[str, int] = {}
        for gate in self.gates:
            counts[gate.name] = counts.get(gate.name, 0) + 1
        return dict(sorted(counts.items()))

    def qubit_wires(self) -> dict[int, list[int]]:
        """Return, per qubit, the gate indices touching it, in program order."""
        wires: dict[int, list[int]] = {q: [] for q in range(self.num_qubits)}
        for index, gate in enumerate(self.gates):
            for q in gate.qubits:
                wires[q].append(index)
        return wires

    def replace_gates(self, gates: Iterable[Gate]) -> Circuit:
        """Return a new circuit with the same registers but different gates."""
        return Circuit(self.num_qubits, self.num_bits, list(gates))


def dump(circuit: Circuit) -> str:
    """Serialize *circuit* back to DSL source (parseable round trip)."""
    lines = [f"qubits {circuit.num_qubits}"]
    if circuit.num_bits:
        lines.append(f"bits {circuit.num_bits}")
    for gate in circuit.gates:
        if gate.name == "measure":
            lines.append(f"measure q{gate.qubits[0]} -> c{gate.bit}")
        elif gate.name == "barrier":
            lines.append("barrier " + ", ".join(f"q{q}" for q in gate.qubits))
        elif gate.angle is not None:
            lines.append(f"{gate.name}({format_angle(gate.angle)}) q{gate.qubits[0]}")
        else:
            operands = ", ".join(f"q{q}" for q in gate.qubits)
            lines.append(f"{gate.name} {operands}")
    return "\n".join(lines) + "\n"

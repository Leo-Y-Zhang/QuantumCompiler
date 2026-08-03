"""Circuit resource analysis: depth, gate mix, two-qubit and T counts.

These are the numbers a compiler report cares about. *Depth* is the number of
moments in the greedy schedule shared with the diagram renderers. The *T-count*
(t + tdg) is highlighted because non-Clifford T gates are the dominant cost in
fault-tolerant quantum computing, so it is the standard headline resource
metric even though this simulator treats all gates as equally cheap.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantum_compiler.draw_ascii import column_layout
from quantum_compiler.ir import Circuit

_TWO_QUBIT = frozenset({"cx", "cz", "swap"})
_NON_OP = frozenset({"measure", "barrier"})


@dataclass(frozen=True)
class CircuitMetrics:
    """Resource counts for a circuit."""

    num_qubits: int
    num_bits: int
    operations: int
    depth: int
    single_qubit_count: int
    two_qubit_count: int
    t_count: int
    gate_histogram: dict[str, int]
    qubit_gate_counts: list[int]


def analyze(circuit: Circuit) -> CircuitMetrics:
    """Compute :class:`CircuitMetrics` for *circuit*."""
    two_qubit = sum(1 for g in circuit.gates if g.name in _TWO_QUBIT)
    single = sum(
        1 for g in circuit.gates if g.name not in _TWO_QUBIT and g.name not in _NON_OP
    )
    t_count = sum(1 for g in circuit.gates if g.name in ("t", "tdg"))
    wires = circuit.qubit_wires()
    return CircuitMetrics(
        num_qubits=circuit.num_qubits,
        num_bits=circuit.num_bits,
        operations=len(circuit.gates),
        depth=max(column_layout(circuit), default=-1) + 1,
        single_qubit_count=single,
        two_qubit_count=two_qubit,
        t_count=t_count,
        gate_histogram=circuit.gate_counts(),
        qubit_gate_counts=[len(wires[q]) for q in range(circuit.num_qubits)],
    )


def metrics_to_dict(metrics: CircuitMetrics) -> dict[str, object]:
    """Return a JSON-serializable dict of *metrics*."""
    return {
        "num_qubits": metrics.num_qubits,
        "num_bits": metrics.num_bits,
        "operations": metrics.operations,
        "depth": metrics.depth,
        "single_qubit_count": metrics.single_qubit_count,
        "two_qubit_count": metrics.two_qubit_count,
        "t_count": metrics.t_count,
        "gate_histogram": metrics.gate_histogram,
        "qubit_gate_counts": metrics.qubit_gate_counts,
    }


def format_report(metrics: CircuitMetrics) -> str:
    """Render *metrics* as an aligned human-readable report."""
    lines = [
        f"qubits: {metrics.num_qubits}    bits: {metrics.num_bits}",
        f"operations: {metrics.operations}",
        f"depth: {metrics.depth}",
        f"1-qubit gates: {metrics.single_qubit_count}",
        f"2-qubit gates: {metrics.two_qubit_count}",
        f"T-count (t+tdg): {metrics.t_count}",
        "gate histogram:",
    ]
    lines.extend(f"  {name}: {count}" for name, count in metrics.gate_histogram.items())
    if metrics.qubit_gate_counts:
        lines.append("per-qubit gate counts:")
        lines.extend(
            f"  q{q}: {count}" for q, count in enumerate(metrics.qubit_gate_counts)
        )
    return "\n".join(lines) + "\n"

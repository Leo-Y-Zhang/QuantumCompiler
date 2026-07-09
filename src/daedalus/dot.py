"""Graphviz DOT export of the IR dependency DAG.

The IR keeps gates in program order, but the only real ordering constraints are
per wire (see :mod:`daedalus.ir`). This emits that dependency graph literally:
one node per gate, and an edge from each gate to the next gate that shares one
of its qubits. Any topological order of the emitted DAG denotes the same
circuit. Render with ``dot -Tsvg circuit.dot -o circuit.svg``.
"""

from __future__ import annotations

from itertools import pairwise

from daedalus.angles import format_angle
from daedalus.ir import Circuit, Gate


def to_dot(circuit: Circuit) -> str:
    """Return a Graphviz DOT description of *circuit*'s dependency DAG."""
    lines = [
        "digraph circuit {",
        "  rankdir=LR;",
        '  node [shape=box, fontname="monospace"];',
    ]
    for i, gate in enumerate(circuit.gates):
        label = _node_label(gate).replace('"', '\\"')
        lines.append(f'  n{i} [label="{label}"];')
    edges: set[tuple[int, int]] = set()
    for wire in circuit.qubit_wires().values():
        edges.update(pairwise(wire))
    lines.extend(f"  n{a} -> n{b};" for a, b in sorted(edges))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _node_label(gate: Gate) -> str:
    """Human-readable node label for *gate*."""
    if gate.name == "measure":
        return f"measure q{gate.qubits[0]}->c{gate.bit}"
    operands = ",".join(f"q{q}" for q in gate.qubits)
    if gate.angle is not None:
        return f"{gate.name}({format_angle(gate.angle)}) {operands}"
    return f"{gate.name} {operands}"

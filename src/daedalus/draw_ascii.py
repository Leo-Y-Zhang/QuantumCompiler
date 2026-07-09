"""ASCII circuit diagrams with aligned columns and wire lines.

Layout uses greedy moment scheduling: each gate is placed in the earliest
column that is free on every wire in its qubit *span* (min..max), so vertical
connectors never collide with other gates. Symbols: ``[H]`` boxes for
single-qubit gates, ``o`` controls, ``(+)`` cx targets, ``x`` swap ends,
``[M->c0]`` measures, ``:`` barrier fences, and ``|`` vertical connectors.
"""

from __future__ import annotations

from daedalus.angles import format_angle
from daedalus.ir import Circuit, Gate


def column_layout(circuit: Circuit) -> list[int]:
    """Greedy moment scheduling: column index for each gate (span-blocking)."""
    depth = [0] * max(circuit.num_qubits, 1)
    columns: list[int] = []
    for gate in circuit.gates:
        lo, hi = min(gate.qubits), max(gate.qubits)
        column = max(depth[lo : hi + 1])
        columns.append(column)
        for q in range(lo, hi + 1):
            depth[q] = column + 1
    return columns


def gate_cells(gate: Gate) -> dict[int, str]:
    """Per-qubit diagram symbol for *gate* (deterministic)."""
    if gate.name == "measure":
        return {gate.qubits[0]: f"[M->c{gate.bit}]"}
    if gate.name == "barrier":
        return dict.fromkeys(gate.qubits, ":")
    if gate.name == "cx":
        control, target = gate.qubits
        return {control: "o", target: "(+)"}
    if gate.name == "cz":
        return {gate.qubits[0]: "o", gate.qubits[1]: "o"}
    if gate.name == "swap":
        return {gate.qubits[0]: "x", gate.qubits[1]: "x"}
    label = gate.name.upper()
    if gate.angle is not None:
        label += f"({format_angle(gate.angle)})"
    return {gate.qubits[0]: f"[{label}]"}


def render_ascii(circuit: Circuit) -> str:
    """Render *circuit* as an ASCII diagram (one wire row per qubit)."""
    columns = column_layout(circuit)
    num_columns = max(columns, default=-1) + 1
    n = max(circuit.num_qubits, 1)
    num_rows = 2 * n - 1

    content: list[list[str]] = [[""] * num_columns for _ in range(num_rows)]
    connector: set[tuple[int, int]] = set()
    for gate, column in zip(circuit.gates, columns, strict=True):
        for q, text in gate_cells(gate).items():
            content[2 * q][column] = text
        if len(gate.qubits) > 1 and gate.name != "barrier":
            lo, hi = min(gate.qubits), max(gate.qubits)
            for row in range(2 * lo + 1, 2 * hi):
                connector.add((row, column))

    widths = [
        max(max((len(content[row][col]) for row in range(num_rows)), default=1), 1) + 2
        for col in range(num_columns)
    ]
    labels = [f"q{q}: " for q in range(circuit.num_qubits)]
    label_width = max((len(label) for label in labels), default=0)

    lines: list[str] = []
    for row in range(2 * circuit.num_qubits - 1 if circuit.num_qubits else 0):
        is_wire = row % 2 == 0
        fill = "-" if is_wire else " "
        prefix = labels[row // 2].ljust(label_width) if is_wire else " " * label_width
        cells: list[str] = []
        for col in range(num_columns):
            text = content[row][col] or ("|" if (row, col) in connector else "")
            pad = widths[col] - len(text)
            left = pad // 2
            cells.append(fill * left + text + fill * (pad - left))
        if num_columns == 0 and is_wire:
            cells.append("-" * 5)
        lines.append(prefix + "".join(cells))
    return "\n".join(lines)

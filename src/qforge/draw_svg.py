"""Hand-rolled SVG circuit rendering built on ``xml.etree`` (stdlib only).

The SVG tree is *generated*, never parsed, so no untrusted XML is processed
here. Column layout is shared with the ASCII renderer for consistency.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from qforge.angles import format_angle
from qforge.draw_ascii import column_layout
from qforge.ir import Circuit, Gate

SVG_NS = "http://www.w3.org/2000/svg"

_LEFT_MARGIN = 52.0
_TOP_MARGIN = 32.0
_ROW_SPACING = 46.0
_BOX_HEIGHT = 26.0
_CHAR_WIDTH = 8.0
_INK = "#1f2430"


def render_svg(circuit: Circuit) -> str:
    """Render *circuit* as a standalone SVG document string."""
    columns = column_layout(circuit)
    num_columns = max(columns, default=-1) + 1
    widths = [40.0] * num_columns
    for gate, column in zip(circuit.gates, columns):
        label = _box_label(gate)
        if label is not None:
            widths[column] = max(widths[column], len(label) * _CHAR_WIDTH + 18.0)
    centers = []
    x = _LEFT_MARGIN
    for w in widths:
        centers.append(x + w / 2)
        x += w
    total_width = x + 16.0
    n = max(circuit.num_qubits, 1)
    total_height = _TOP_MARGIN + _ROW_SPACING * (n - 1) + _TOP_MARGIN

    root = ET.Element(
        "svg",
        {
            "xmlns": SVG_NS,
            "width": _fmt(total_width),
            "height": _fmt(total_height),
            "viewBox": f"0 0 {_fmt(total_width)} {_fmt(total_height)}",
            "font-family": "monospace",
            "font-size": "12",
        },
    )
    ET.SubElement(
        root,
        "rect",
        {"x": "0", "y": "0", "width": _fmt(total_width), "height": _fmt(total_height), "fill": "#ffffff"},
    )
    for q in range(circuit.num_qubits):
        y = _wire_y(q)
        label = ET.SubElement(root, "text", {"x": "8", "y": _fmt(y + 4), "fill": _INK})
        label.text = f"q{q}"
        ET.SubElement(
            root,
            "line",
            {
                "x1": _fmt(_LEFT_MARGIN - 8),
                "y1": _fmt(y),
                "x2": _fmt(total_width - 10),
                "y2": _fmt(y),
                "stroke": _INK,
                "stroke-width": "1",
            },
        )
    for gate, column in zip(circuit.gates, columns):
        _draw_gate(root, gate, centers[column])
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def _wire_y(q: int) -> float:
    return _TOP_MARGIN + _ROW_SPACING * q


def _box_label(gate: Gate) -> str | None:
    """Text label for box-style gates; ``None`` for symbol-style gates."""
    if gate.name == "measure":
        return f"M->c{gate.bit}"
    if gate.name in ("cx", "cz", "swap"):
        return None
    label = gate.name.upper()
    if gate.angle is not None:
        label += f"({format_angle(gate.angle)})"
    return label


def _draw_gate(root: ET.Element, gate: Gate, cx: float) -> None:
    label = _box_label(gate)
    if label is not None:
        _draw_box(root, cx, _wire_y(gate.qubits[0]), label)
        return
    ys = [_wire_y(q) for q in gate.qubits]
    _line(root, cx, min(ys), cx, max(ys))
    if gate.name == "cx":
        _dot(root, cx, ys[0])
        _target_ring(root, cx, ys[1])
    elif gate.name == "cz":
        _dot(root, cx, ys[0])
        _dot(root, cx, ys[1])
    else:  # swap
        _swap_mark(root, cx, ys[0])
        _swap_mark(root, cx, ys[1])


def _draw_box(root: ET.Element, cx: float, y: float, label: str) -> None:
    w = len(label) * _CHAR_WIDTH + 12.0
    ET.SubElement(
        root,
        "rect",
        {
            "x": _fmt(cx - w / 2),
            "y": _fmt(y - _BOX_HEIGHT / 2),
            "width": _fmt(w),
            "height": _fmt(_BOX_HEIGHT),
            "rx": "3",
            "fill": "#ffffff",
            "stroke": _INK,
            "stroke-width": "1",
        },
    )
    text = ET.SubElement(
        root,
        "text",
        {"x": _fmt(cx), "y": _fmt(y + 4), "text-anchor": "middle", "fill": _INK},
    )
    text.text = label


def _line(root: ET.Element, x1: float, y1: float, x2: float, y2: float) -> None:
    ET.SubElement(
        root,
        "line",
        {
            "x1": _fmt(x1),
            "y1": _fmt(y1),
            "x2": _fmt(x2),
            "y2": _fmt(y2),
            "stroke": _INK,
            "stroke-width": "1.5",
        },
    )


def _dot(root: ET.Element, cx: float, cy: float) -> None:
    ET.SubElement(
        root, "circle", {"cx": _fmt(cx), "cy": _fmt(cy), "r": "4", "fill": _INK}
    )


def _target_ring(root: ET.Element, cx: float, cy: float) -> None:
    ET.SubElement(
        root,
        "circle",
        {"cx": _fmt(cx), "cy": _fmt(cy), "r": "9", "fill": "none", "stroke": _INK, "stroke-width": "1.5"},
    )
    _line(root, cx - 9, cy, cx + 9, cy)
    _line(root, cx, cy - 9, cx, cy + 9)


def _swap_mark(root: ET.Element, cx: float, cy: float) -> None:
    _line(root, cx - 6, cy - 6, cx + 6, cy + 6)
    _line(root, cx - 6, cy + 6, cx + 6, cy - 6)


def _fmt(value: float) -> str:
    return f"{value:g}"

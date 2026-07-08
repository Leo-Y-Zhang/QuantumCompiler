"""Tests for the hand-rolled SVG renderer (well-formedness via xml.etree)."""

import xml.etree.ElementTree as ET

from daedalus.draw_svg import render_svg
from daedalus.parser import parse

SVG_NS = "{http://www.w3.org/2000/svg}"

SRC = "qubits 2\nbits 1\nh q0\ncx q0, q1\nrz(pi/4) q1\nmeasure q1 -> c0\n"


def render_root(src: str) -> ET.Element:
    return ET.fromstring(render_svg(parse(src)))


class TestWellFormedness:
    def test_parses_as_xml(self) -> None:
        root = render_root(SRC)
        assert root.tag == f"{SVG_NS}svg"

    def test_has_numeric_dimensions(self) -> None:
        root = render_root(SRC)
        assert float(root.get("width", "x")) > 0
        assert float(root.get("height", "x")) > 0

    def test_starts_with_xml_declaration(self) -> None:
        text = render_svg(parse(SRC))
        assert text.startswith("<?xml")


class TestContent:
    def test_wire_line_per_qubit(self) -> None:
        root = render_root(SRC)
        lines = root.findall(f".//{SVG_NS}line")
        assert len(lines) >= 2

    def test_qubit_labels(self) -> None:
        root = render_root(SRC)
        texts = {t.text for t in root.findall(f".//{SVG_NS}text")}
        assert {"q0", "q1"} <= texts

    def test_gate_boxes_and_labels(self) -> None:
        root = render_root(SRC)
        texts = {t.text for t in root.findall(f".//{SVG_NS}text")}
        assert "H" in texts
        assert "RZ(pi/4)" in texts
        rects = root.findall(f".//{SVG_NS}rect")
        assert len(rects) >= 3  # background + at least two gate boxes

    def test_control_dot_is_circle(self) -> None:
        root = render_root("qubits 2\ncx q0, q1\n")
        circles = root.findall(f".//{SVG_NS}circle")
        assert len(circles) >= 2  # control dot + target ring

    def test_deterministic_output(self) -> None:
        a = render_svg(parse(SRC))
        b = render_svg(parse(SRC))
        assert a == b

    def test_empty_circuit_renders(self) -> None:
        root = render_root("qubits 1\n")
        assert root.tag == f"{SVG_NS}svg"

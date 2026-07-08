"""Tests for the ASCII circuit renderer."""

from daedalus.draw_ascii import render_ascii
from daedalus.parser import parse


class TestRendering:
    def test_single_gate_exact(self) -> None:
        assert render_ascii(parse("qubits 1\nh q0\n")) == "q0: -[H]-"

    def test_all_lines_same_length(self) -> None:
        src = "qubits 3\nbits 1\nh q0\ncx q0, q1\nrz(pi/4) q1\nmeasure q1 -> c0\n"
        lines = render_ascii(parse(src)).splitlines()
        assert len({len(line) for line in lines}) == 1

    def test_row_labels(self) -> None:
        lines = render_ascii(parse("qubits 2\nh q0\n")).splitlines()
        assert lines[0].startswith("q0: ")
        assert lines[2].startswith("q1: ")

    def test_gate_labels_present(self) -> None:
        src = "qubits 2\nbits 1\nh q0\nrz(pi/4) q0\nmeasure q0 -> c0\n"
        out = render_ascii(parse(src))
        assert "[H]" in out
        assert "[RZ(pi/4)]" in out
        assert "[M->c0]" in out

    def test_cx_control_and_target_symbols(self) -> None:
        lines = render_ascii(parse("qubits 2\ncx q0, q1\n")).splitlines()
        assert "o" in lines[0]
        assert "(+)" in lines[2]
        assert "|" in lines[1]  # vertical connector on the spacer row

    def test_swap_symbols(self) -> None:
        lines = render_ascii(parse("qubits 2\nswap q0, q1\n")).splitlines()
        assert "x" in lines[0]
        assert "x" in lines[2]

    def test_connector_crosses_middle_wire(self) -> None:
        lines = render_ascii(parse("qubits 3\ncx q0, q2\n")).splitlines()
        assert "|" in lines[2]  # q1's wire is crossed, not touched

    def test_parallel_gates_share_a_column(self) -> None:
        # h q0 and h q1 are independent: the diagram needs only one column.
        one = render_ascii(parse("qubits 2\nh q0\nh q1\n")).splitlines()
        two = render_ascii(parse("qubits 2\nh q0\nh q0\n")).splitlines()
        assert len(one[0]) < len(two[0])

    def test_gate_order_left_to_right(self) -> None:
        line = render_ascii(parse("qubits 1\nh q0\nx q0\n")).splitlines()[0]
        assert line.index("[H]") < line.index("[X]")

    def test_empty_circuit(self) -> None:
        out = render_ascii(parse("qubits 2\n"))
        lines = out.splitlines()
        assert lines[0].startswith("q0: ")
        assert set(lines[0][4:]) <= {"-"}

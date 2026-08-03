"""Tests for the recursive-descent parser: valid programs and precise errors."""

import math

import pytest

from quantum_compiler.errors import ParseError
from quantum_compiler.ir import Gate
from quantum_compiler.parser import parse

EXAMPLE = """\
qubits 3
bits 3
h q0
cx q0, q1
rz(pi/4) q1
rz(pi/4) q1
x q2
x q2
measure q0 -> c0
"""


class TestValidPrograms:
    def test_example_program(self) -> None:
        circuit = parse(EXAMPLE)
        assert circuit.num_qubits == 3
        assert circuit.num_bits == 3
        assert len(circuit.gates) == 7
        assert circuit.gates[0] == Gate("h", (0,))
        assert circuit.gates[1] == Gate("cx", (0, 1))
        assert circuit.gates[2] == Gate("rz", (1,), angle=math.pi / 4)
        assert circuit.gates[-1] == Gate("measure", (0,), bit=0)

    def test_all_gate_names(self) -> None:
        src = (
            "qubits 2\nbits 1\n"
            "h q0\nx q0\ny q0\nz q0\ns q0\nsdg q0\nt q0\ntdg q0\n"
            "rx(pi) q0\nry(-pi/2) q0\nrz(2*pi) q0\n"
            "cx q0, q1\ncz q0, q1\nswap q0, q1\nmeasure q1 -> c0\n"
        )
        circuit = parse(src)
        assert len(circuit.gates) == 15

    def test_comments_and_blank_lines(self) -> None:
        circuit = parse("# header\nqubits 1\n\nh q0  # comment\n")
        assert [g.name for g in circuit.gates] == ["h"]

    def test_bits_default_to_zero(self) -> None:
        circuit = parse("qubits 1\nh q0\n")
        assert circuit.num_bits == 0

    def test_angle_expression(self) -> None:
        circuit = parse("qubits 1\nrz(pi/4 + pi/4) q0\n")
        assert circuit.gates[0].angle == pytest.approx(math.pi / 2)


class TestParseErrors:
    def test_unknown_gate(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nfoo q0\n")
        assert (exc.value.line, exc.value.column) == (2, 1)
        assert "unknown gate 'foo'" in exc.value.message

    def test_gate_before_qubits(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("h q0\n")
        assert (exc.value.line, exc.value.column) == (1, 1)
        assert "qubits" in exc.value.message

    def test_qubit_out_of_range(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 3\nh q9\n")
        assert (exc.value.line, exc.value.column) == (2, 3)
        assert "q9" in exc.value.message

    def test_missing_comma(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 2\ncx q0 q1\n")
        assert (exc.value.line, exc.value.column) == (2, 7)

    def test_duplicate_qubit_operand(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 2\ncx q0, q0\n")
        assert (exc.value.line, exc.value.column) == (2, 8)
        assert "duplicate" in exc.value.message

    def test_angle_on_plain_gate(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nh(pi) q0\n")
        assert (exc.value.line, exc.value.column) == (2, 2)

    def test_missing_angle_on_rotation(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nrz q0\n")
        assert (exc.value.line, exc.value.column) == (2, 4)

    def test_bad_qubit_operand(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nh foo\n")
        assert (exc.value.line, exc.value.column) == (2, 3)

    def test_measure_bit_out_of_range(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nbits 1\nmeasure q0 -> c5\n")
        assert (exc.value.line, exc.value.column) == (3, 15)

    def test_measure_without_arrow(self) -> None:
        with pytest.raises(ParseError):
            parse("qubits 1\nbits 1\nmeasure q0 c0\n")

    def test_trailing_tokens(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nh q0 q0\n")
        assert (exc.value.line, exc.value.column) == (2, 6)

    def test_duplicate_qubits_declaration(self) -> None:
        with pytest.raises(ParseError):
            parse("qubits 1\nqubits 2\n")

    def test_zero_qubits(self) -> None:
        with pytest.raises(ParseError):
            parse("qubits 0\n")

    def test_non_integer_qubits(self) -> None:
        with pytest.raises(ParseError):
            parse("qubits 1.5\n")

    def test_error_in_angle_expression_position(self) -> None:
        with pytest.raises(ParseError) as exc:
            parse("qubits 1\nrz(pi/) q0\n")
        assert exc.value.line == 2
        assert exc.value.column == 7

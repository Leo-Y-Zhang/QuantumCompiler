"""Tests for OpenQASM 2.0 interop: emitter, subset importer, and roundtrips."""

import math
from pathlib import Path

import pytest

from daedalus.errors import ParseError
from daedalus.ir import Circuit, Gate
from daedalus.parser import parse
from daedalus.passes import PassManager, default_passes
from daedalus.qasm import emit_qasm, parse_qasm
from daedalus.verify import check_equivalence

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

BELL_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
x q[1];
x q[1];
cx q[0],q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""

PRELUDE = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncreg c[2];\n'


class TestEmitter:
    def test_bell_exact_output(self) -> None:
        source = (EXAMPLES / "bell.qf").read_text(encoding="ascii")
        assert emit_qasm(parse(source)) == BELL_QASM

    def test_rotation_angles_emitted_as_floats(self) -> None:
        circuit = parse("qubits 1\nrx(pi/2) q0\n")
        assert "rx(1.5707963267948966) q[0];" in emit_qasm(circuit)

    def test_negative_angle(self) -> None:
        circuit = parse("qubits 1\nrz(-pi/2) q0\n")
        assert "rz(-1.5707963267948966) q[0];" in emit_qasm(circuit)

    def test_no_creg_line_when_no_bits(self) -> None:
        output = emit_qasm(parse("qubits 1\nh q0\n"))
        assert "creg" not in output
        assert "qreg q[1];" in output

    def test_zero_qubit_circuit_rejected(self) -> None:
        with pytest.raises(ValueError):
            emit_qasm(Circuit(num_qubits=0, num_bits=0))

    def test_every_gate_emits_and_reimports(self) -> None:
        src = (
            "qubits 2\nbits 1\n"
            "h q0\nx q0\ny q0\nz q0\ns q0\nsdg q0\nt q0\ntdg q0\n"
            "rx(pi) q0\nry(-pi/2) q0\nrz(2*pi) q0\n"
            "cx q0, q1\ncz q0, q1\nswap q0, q1\nmeasure q1 -> c0\n"
        )
        circuit = parse(src)
        assert parse_qasm(emit_qasm(circuit)) == circuit


class TestImporter:
    def test_bell_matches_dsl_parse(self) -> None:
        source = (EXAMPLES / "bell.qf").read_text(encoding="ascii")
        assert parse_qasm(BELL_QASM) == parse(source)

    def test_include_is_optional(self) -> None:
        circuit = parse_qasm("OPENQASM 2.0;\nqreg q[1];\nh q[0];\n")
        assert circuit.gates == [Gate("h", (0,))]

    def test_arbitrary_register_names(self) -> None:
        source = (
            "OPENQASM 2.0;\nqreg wires[2];\ncreg out[1];\n"
            "h wires[0];\ncx wires[0],wires[1];\nmeasure wires[1] -> out[0];\n"
        )
        circuit = parse_qasm(source)
        assert circuit.num_qubits == 2
        assert circuit.num_bits == 1
        assert circuit.gates == [
            Gate("h", (0,)),
            Gate("cx", (0, 1)),
            Gate("measure", (1,), bit=0),
        ]

    def test_comments_and_blank_lines(self) -> None:
        source = (
            "// leading comment\nOPENQASM 2.0; // trailing comment\n\n"
            'include "qelib1.inc";\nqreg q[1];\n\n// another\nx q[0];\n'
        )
        assert parse_qasm(source).gates == [Gate("x", (0,))]

    def test_statements_may_span_lines(self) -> None:
        source = "OPENQASM 2.0;\nqreg q[1];\nh\nq[0]\n;\n"
        assert parse_qasm(source).gates == [Gate("h", (0,))]

    @pytest.mark.parametrize(
        ("expr", "value"),
        [
            ("pi/2", math.pi / 2),
            ("-0.25", -0.25),
            ("2*pi", 2 * math.pi),
            ("pi/2 + pi/4", 3 * math.pi / 4),
            ("1e-05", 1e-05),
            ("6.123233995736766e-17", 6.123233995736766e-17),
        ],
    )
    def test_angle_expressions(self, expr: str, value: float) -> None:
        circuit = parse_qasm(f"OPENQASM 2.0;\nqreg q[1];\nrx({expr}) q[0];\n")
        assert circuit.gates[0].angle == pytest.approx(value, abs=0.0)


class TestImporterErrors:
    @pytest.mark.parametrize(
        ("source", "line", "column", "fragment"),
        [
            ("qreg q[1];\n", 1, 1, "expected 'OPENQASM 2.0;' header"),
            ("OPENQASM 3.0;\n", 1, 10, "only OPENQASM 2.0 is supported"),
            ('OPENQASM 2.0;\ninclude "other.inc";\n', 2, 9, 'only include "qelib1.inc"'),
            (PRELUDE + "barrier q;\n", 5, 1, "'barrier' is not supported"),
            (PRELUDE + "if (c == 1) x q[0];\n", 5, 1, "'if' statements are not supported"),
            (PRELUDE + "gate foo a { x a; }\n", 5, 1, "user-defined gates are not supported"),
            (PRELUDE + "opaque foo a;\n", 5, 1, "'opaque' declarations are not supported"),
            (PRELUDE + "reset q[0];\n", 5, 1, "'reset' is not supported"),
            (PRELUDE + "qreg r[1];\n", 5, 1, "only a single qreg is supported"),
            (PRELUDE + "creg d[1];\n", 5, 1, "only a single creg is supported"),
            (PRELUDE + "h q;\n", 5, 4, "whole-register operands are not supported"),
            (PRELUDE + "h r[0];\n", 5, 3, "unknown register 'r'"),
            (PRELUDE + "foo q[0];\n", 5, 1, "unknown gate 'foo'"),
            (PRELUDE + "U(0,0,0) q[0];\n", 5, 1, "builtin 'U' is not supported"),
            (PRELUDE + "CX q[0],q[1];\n", 5, 1, "builtin 'CX' is not supported"),
            (PRELUDE + "x q[2];\n", 5, 5, "out of range"),
            (PRELUDE + "measure q[0] -> c[5];\n", 5, 19, "out of range"),
            (PRELUDE + "cx q[0],q[0];\n", 5, 9, "duplicate qubit operand"),
            (PRELUDE + "h(0.5) q[0];\n", 5, 2, "does not take an angle"),
            (PRELUDE + "rx q[0];\n", 5, 4, "requires an angle"),
            (PRELUDE + "h c[0];\n", 5, 3, "classical register 'c'"),
            (PRELUDE + "measure q[0] -> q[0];\n", 5, 17, "qubit register 'q'"),
            ("OPENQASM 2.0;\nqreg q[0];\n", 2, 8, "at least 1"),
            ("OPENQASM 2.0;\nqreg q[2.5];\n", 2, 8, "must be an integer"),
            (
                "OPENQASM 2.0;\nqreg q[1];\nmeasure q[0] -> c[0];\n",
                3,
                17,
                "no creg declared",
            ),
            ("OPENQASM 2.0;\nqreg q[1];\nh q[0]\nx q[0];\n", 4, 1, "expected ';'"),
        ],
    )
    def test_error_position_and_message(
        self, source: str, line: int, column: int, fragment: str
    ) -> None:
        with pytest.raises(ParseError) as excinfo:
            parse_qasm(source)
        assert excinfo.value.line == line
        assert excinfo.value.column == column
        assert fragment in excinfo.value.message

    def test_error_formats_like_dsl_errors(self) -> None:
        with pytest.raises(ParseError) as excinfo:
            parse_qasm(PRELUDE + "barrier q;\n")
        assert excinfo.value.format("bad.qasm") == (
            "bad.qasm:5:1: error: 'barrier' is not supported"
        )


class TestRoundtrip:
    @pytest.mark.parametrize("name", ["bell", "ghz", "rotations"])
    def test_examples_roundtrip_structurally_and_semantically(self, name: str) -> None:
        source = (EXAMPLES / f"{name}.qf").read_text(encoding="ascii")
        original = parse(source)
        optimized, _ = PassManager(default_passes()).run(original)
        for circuit in (original, optimized):
            back = parse_qasm(emit_qasm(circuit))
            assert back == circuit
            result = check_equivalence(circuit, back)
            assert result.equivalent
            assert result.max_error <= 1e-9

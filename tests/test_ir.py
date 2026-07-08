"""Tests for the gate-list IR and its per-qubit wire (DAG) structure."""

from daedalus.ir import dump
from daedalus.parser import parse

SRC = """\
qubits 3
bits 1
h q0
cx q0, q1
x q2
rz(pi/4) q1
measure q1 -> c0
"""


class TestCircuit:
    def test_gate_counts_sorted(self) -> None:
        circuit = parse(SRC)
        assert circuit.gate_counts() == {
            "cx": 1,
            "h": 1,
            "measure": 1,
            "rz": 1,
            "x": 1,
        }
        assert list(circuit.gate_counts()) == sorted(circuit.gate_counts())

    def test_qubit_wires(self) -> None:
        circuit = parse(SRC)
        wires = circuit.qubit_wires()
        assert wires[0] == [0, 1]  # h, cx
        assert wires[1] == [1, 3, 4]  # cx, rz, measure
        assert wires[2] == [2]  # x

    def test_qubit_wires_cover_all_qubits(self) -> None:
        circuit = parse("qubits 2\nh q0\n")
        wires = circuit.qubit_wires()
        assert wires[1] == []

    def test_replace_gates_returns_new_circuit(self) -> None:
        circuit = parse(SRC)
        smaller = circuit.replace_gates(circuit.gates[:2])
        assert len(smaller.gates) == 2
        assert len(circuit.gates) == 5
        assert smaller.num_qubits == circuit.num_qubits


class TestDump:
    def test_dump_round_trips(self) -> None:
        circuit = parse(SRC)
        again = parse(dump(circuit))
        assert again.gates == circuit.gates
        assert again.num_qubits == circuit.num_qubits
        assert again.num_bits == circuit.num_bits

    def test_dump_formats_pi_angles(self) -> None:
        text = dump(parse("qubits 1\nrz(pi/4) q0\n"))
        assert "rz(pi/4) q0" in text

"""canonicalize-rotations: special-angle rotations -> named Clifford+T gates.

Every rewrite is checked semantics-preserving (up to global phase) by the exact
unitary proof, and the emitted gate name is asserted so the normal form is
locked, not just the semantics.
"""

import math

import pytest

from daedalus.ir import Circuit, Gate
from daedalus.parser import parse
from daedalus.passes.canonicalize_rotations import CanonicalizeRotations
from daedalus.unitary import prove_circuit_equivalence


def run(src: str) -> Circuit:
    return CanonicalizeRotations().run(parse(src))


def names(circuit: Circuit) -> list[str]:
    return [g.name for g in circuit.gates]


class TestRzMappings:
    @pytest.mark.parametrize(
        "angle, expected",
        [
            ("pi/2", "s"),
            ("-pi/2", "sdg"),
            ("3*pi/2", "sdg"),
            ("pi", "z"),
            ("-pi", "z"),
            ("pi/4", "t"),
            ("-pi/4", "tdg"),
        ],
    )
    def test_rz_special_angles(self, angle: str, expected: str) -> None:
        original = parse(f"qubits 1\nrz({angle}) q0\n")
        result = CanonicalizeRotations().run(original)
        assert names(result) == [expected]
        assert prove_circuit_equivalence(original, result).equivalent

    def test_rz_zero_is_dropped(self) -> None:
        assert names(run("qubits 1\nrz(0) q0\n")) == []

    def test_rz_two_pi_is_dropped(self) -> None:
        original = parse("qubits 1\nrz(2*pi) q0\n")
        result = CanonicalizeRotations().run(original)
        assert result.gates == []
        assert prove_circuit_equivalence(original, result).equivalent


class TestRxRyMappings:
    def test_rx_pi_is_x(self) -> None:
        original = parse("qubits 1\nrx(pi) q0\n")
        result = CanonicalizeRotations().run(original)
        assert names(result) == ["x"]
        assert prove_circuit_equivalence(original, result).equivalent

    def test_ry_pi_is_y(self) -> None:
        original = parse("qubits 1\nry(pi) q0\n")
        result = CanonicalizeRotations().run(original)
        assert names(result) == ["y"]
        assert prove_circuit_equivalence(original, result).equivalent

    def test_rx_zero_dropped(self) -> None:
        assert run("qubits 1\nrx(0) q0\n").gates == []


class TestLeavesGenericAnglesAlone:
    def test_generic_angle_unchanged(self) -> None:
        circuit = parse("qubits 1\nrz(0.37) q0\n")
        result = CanonicalizeRotations().run(circuit)
        assert result is circuit  # no change -> same object

    def test_rx_pi_over_two_has_no_named_form(self) -> None:
        circuit = parse("qubits 1\nrx(pi/2) q0\n")
        assert names(CanonicalizeRotations().run(circuit)) == ["rx"]

    def test_near_special_but_outside_tolerance(self) -> None:
        circuit = parse("qubits 1\nrz(1.5707) q0\n")  # pi/2 - 0.00009...
        assert names(CanonicalizeRotations().run(circuit)) == ["rz"]


class TestPreservesOtherGates:
    def test_only_rotations_touched(self) -> None:
        original = parse("qubits 2\nh q0\nrz(pi/2) q0\ncx q0, q1\nrx(pi) q1\n")
        result = CanonicalizeRotations().run(original)
        assert names(result) == ["h", "s", "cx", "x"]
        assert prove_circuit_equivalence(original, result).equivalent

    def test_angle_carried_on_replacement_when_needed(self) -> None:
        # A non-special rotation keeps its float angle unchanged.
        g = run("qubits 1\nrz(0.9) q0\n").gates[0]
        assert g.name == "rz"
        assert g.angle == pytest.approx(0.9)


class TestConstruction:
    def test_direct_gate_list(self) -> None:
        circuit = Circuit(1, 0, [Gate("rz", (0,), angle=math.pi / 4)])
        assert names(CanonicalizeRotations().run(circuit)) == ["t"]

"""Tests for the peephole-identity pass.

Covers the Hadamard-conjugation family h x h -> z, h z h -> x, h y h -> y,
and the basis-change rotation rewrites h rz(a) h -> rx(a), h rx(a) h -> rz(a),
h ry(a) h -> ry(-a).
"""

import math

import pytest

from daedalus.parser import parse
from daedalus.passes.peephole import Peephole
from daedalus.verify import check_equivalence

PASS = Peephole()


def names(src: str) -> list[str]:
    return [g.name for g in PASS.run(parse(src)).gates]


class TestRewrites:
    def test_hxh_to_z(self) -> None:
        assert names("qubits 1\nh q0\nx q0\nh q0\n") == ["z"]

    def test_hzh_to_x(self) -> None:
        assert names("qubits 1\nh q0\nz q0\nh q0\n") == ["x"]

    def test_hyh_to_y(self) -> None:
        assert names("qubits 1\nh q0\ny q0\nh q0\n") == ["y"]

    def test_hrzh_to_rx(self) -> None:
        out = PASS.run(parse("qubits 1\nh q0\nrz(pi/4) q0\nh q0\n"))
        assert [g.name for g in out.gates] == ["rx"]
        assert out.gates[0].angle == pytest.approx(math.pi / 4)

    def test_hrxh_to_rz(self) -> None:
        out = PASS.run(parse("qubits 1\nh q0\nrx(pi/4) q0\nh q0\n"))
        assert [g.name for g in out.gates] == ["rz"]
        assert out.gates[0].angle == pytest.approx(math.pi / 4)

    def test_hryh_negates_angle(self) -> None:
        out = PASS.run(parse("qubits 1\nh q0\nry(pi/4) q0\nh q0\n"))
        assert [g.name for g in out.gates] == ["ry"]
        assert out.gates[0].angle == pytest.approx(-math.pi / 4)

    def test_rewrite_embedded_in_larger_circuit(self) -> None:
        src = "qubits 2\ncx q0, q1\nh q1\nx q1\nh q1\nt q0\n"
        assert names(src) == ["cx", "z", "t"]

    def test_two_disjoint_rewrites_in_one_run(self) -> None:
        src = "qubits 2\nh q0\nx q0\nh q0\nh q1\nz q1\nh q1\n"
        assert sorted(names(src)) == ["x", "z"]


class TestBlocked:
    def test_pattern_across_different_qubits_not_rewritten(self) -> None:
        assert names("qubits 2\nh q0\nx q1\nh q0\n") == ["h", "x", "h"]

    def test_intervening_two_qubit_gate_blocks(self) -> None:
        src = "qubits 2\nh q0\ncx q0, q1\nx q0\nh q0\n"
        assert names(src) == ["h", "cx", "x", "h"]

    def test_partial_pattern_untouched(self) -> None:
        assert names("qubits 1\nh q0\nx q0\n") == ["h", "x"]


class TestSemantics:
    def test_pass_preserves_semantics(self) -> None:
        src = "qubits 2\nh q0\nx q0\nh q0\ncx q0, q1\nh q1\nz q1\nh q1\n"
        original = parse(src)
        assert check_equivalence(original, PASS.run(original)).equivalent

    def test_hyh_preserves_semantics(self) -> None:
        # H Y H == -Y; the rewrite to y is a global-phase change the checker accepts.
        original = parse("qubits 1\nh q0\ny q0\nh q0\n")
        assert check_equivalence(original, PASS.run(original)).equivalent

    def test_rotation_basis_changes_preserve_semantics(self) -> None:
        src = "qubits 1\nh q0\nrz(0.7) q0\nh q0\nh q0\nrx(-1.2) q0\nh q0\n"
        original = parse(src)
        assert check_equivalence(original, PASS.run(original)).equivalent

    def test_ry_basis_change_preserves_semantics(self) -> None:
        original = parse("qubits 2\nh q0\nry(1.1) q0\nh q0\ncx q0, q1\n")
        assert check_equivalence(original, PASS.run(original)).equivalent

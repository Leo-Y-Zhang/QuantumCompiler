"""Tests for the rotation-merging pass."""

import math

import pytest

from qforge.parser import parse
from qforge.passes.merge_rotations import MergeRotations
from qforge.verify import check_equivalence

PASS = MergeRotations()


class TestMerging:
    def test_adjacent_rz_merge(self) -> None:
        out = PASS.run(parse("qubits 1\nrz(pi/4) q0\nrz(pi/4) q0\n"))
        assert len(out.gates) == 1
        assert out.gates[0].name == "rz"
        assert out.gates[0].angle == pytest.approx(math.pi / 2)

    def test_rx_and_ry_merge_too(self) -> None:
        for name in ("rx", "ry"):
            out = PASS.run(parse(f"qubits 1\n{name}(0.3) q0\n{name}(0.4) q0\n"))
            assert [g.name for g in out.gates] == [name]
            assert out.gates[0].angle == pytest.approx(0.7)

    def test_zero_mod_two_pi_is_dropped(self) -> None:
        out = PASS.run(parse("qubits 1\nrz(pi) q0\nrz(pi) q0\n"))
        assert out.gates == []

    def test_exact_zero_sum_dropped(self) -> None:
        out = PASS.run(parse("qubits 1\nrx(pi/4) q0\nrx(-pi/4) q0\n"))
        assert out.gates == []


class TestBlocked:
    def test_different_axes_not_merged(self) -> None:
        out = PASS.run(parse("qubits 1\nrx(0.3) q0\nry(0.3) q0\n"))
        assert len(out.gates) == 2

    def test_different_qubits_not_merged(self) -> None:
        out = PASS.run(parse("qubits 2\nrz(0.3) q0\nrz(0.3) q1\n"))
        assert len(out.gates) == 2

    def test_intervening_gate_blocks(self) -> None:
        out = PASS.run(parse("qubits 2\nrz(0.3) q0\ncx q0, q1\nrz(0.3) q0\n"))
        assert len(out.gates) == 3

    def test_measure_blocks(self) -> None:
        src = "qubits 1\nbits 1\nrz(0.3) q0\nmeasure q0 -> c0\nrz(0.3) q0\n"
        out = PASS.run(parse(src))
        assert len(out.gates) == 3


class TestSemantics:
    def test_pass_preserves_semantics(self) -> None:
        src = "qubits 2\nrz(pi/4) q0\nrz(pi/4) q0\nrx(0.3) q1\nrx(-0.3) q1\nh q0\n"
        original = parse(src)
        assert check_equivalence(original, PASS.run(original)).equivalent

    def test_two_pi_drop_is_global_phase_only(self) -> None:
        # rz(pi) rz(pi) == rz(2*pi) == -I; dropping it is a global-phase change.
        original = parse("qubits 1\nrz(pi) q0\nrz(pi) q0\n")
        assert check_equivalence(original, PASS.run(original)).equivalent

"""Tests for commutation-aware cancellation across cx controls / cz qubits."""

import math

import pytest

from daedalus.parser import parse
from daedalus.passes.commute_cancel import CommuteCancel
from daedalus.verify import check_equivalence

PASS = CommuteCancel()


def names(src: str) -> list[str]:
    return [g.name for g in PASS.run(parse(src)).gates]


class TestCancellation:
    def test_rz_cancels_across_cx_control(self) -> None:
        src = "qubits 2\nrz(pi/4) q0\ncx q0, q1\nrz(-pi/4) q0\n"
        assert names(src) == ["cx"]

    def test_rz_merges_across_cx_control(self) -> None:
        src = "qubits 2\nrz(pi/4) q0\ncx q0, q1\nrz(pi/4) q0\n"
        out = PASS.run(parse(src))
        assert [g.name for g in out.gates] == ["rz", "cx"]
        assert out.gates[0].angle == pytest.approx(math.pi / 2)

    def test_z_cancels_across_cx_control(self) -> None:
        assert names("qubits 2\nz q0\ncx q0, q1\nz q0\n") == ["cx"]

    def test_s_sdg_cancels_across_cx_control(self) -> None:
        assert names("qubits 2\ns q0\ncx q0, q1\nsdg q0\n") == ["cx"]

    def test_t_tdg_cancels_across_multiple_cx_controls(self) -> None:
        src = "qubits 3\nt q0\ncx q0, q1\ncx q0, q2\ntdg q0\n"
        assert names(src) == ["cx", "cx"]

    def test_cancels_across_cz_either_qubit(self) -> None:
        assert names("qubits 2\nrz(0.3) q1\ncz q0, q1\nrz(-0.3) q1\n") == ["cz"]


class TestBlocked:
    def test_cx_target_blocks(self) -> None:
        src = "qubits 2\nrz(0.3) q0\ncx q1, q0\nrz(-0.3) q0\n"
        assert names(src) == ["rz", "cx", "rz"]

    def test_h_blocks(self) -> None:
        src = "qubits 1\nrz(0.3) q0\nh q0\nrz(-0.3) q0\n"
        assert names(src) == ["rz", "h", "rz"]

    def test_measure_blocks(self) -> None:
        src = "qubits 2\nbits 1\nrz(0.3) q0\nmeasure q0 -> c0\nrz(-0.3) q0\n"
        assert names(src) == ["rz", "measure", "rz"]

    def test_x_basis_rotation_does_not_commute(self) -> None:
        src = "qubits 2\nrx(0.3) q0\ncx q0, q1\nrx(-0.3) q0\n"
        assert names(src) == ["rx", "cx", "rx"]


class TestSemantics:
    def test_cancellation_preserves_semantics(self) -> None:
        src = "qubits 2\nh q0\nrz(pi/4) q0\ncx q0, q1\nrz(-pi/4) q0\nh q1\n"
        original = parse(src)
        assert check_equivalence(original, PASS.run(original)).equivalent

    def test_merge_preserves_semantics(self) -> None:
        src = "qubits 3\nh q0\nt q0\ncx q0, q1\ncz q0, q2\ntdg q0\nh q2\n"
        original = parse(src)
        assert check_equivalence(original, PASS.run(original)).equivalent

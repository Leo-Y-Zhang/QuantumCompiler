"""Tests for the adjacent inverse-pair cancellation pass."""

from qforge.parser import parse
from qforge.passes.cancel_inverses import CancelInverses
from qforge.verify import check_equivalence

PASS = CancelInverses()


def names(src: str) -> list[str]:
    return [g.name for g in PASS.run(parse(src)).gates]


class TestCancellation:
    def test_hh_cancels(self) -> None:
        assert names("qubits 1\nh q0\nh q0\n") == []

    def test_xx_cancels(self) -> None:
        assert names("qubits 1\nx q0\nx q0\n") == []

    def test_s_sdg_cancels_both_orders(self) -> None:
        assert names("qubits 1\ns q0\nsdg q0\n") == []
        assert names("qubits 1\nsdg q0\ns q0\n") == []

    def test_t_tdg_cancels(self) -> None:
        assert names("qubits 1\nt q0\ntdg q0\n") == []

    def test_cx_cx_same_qubits_cancels(self) -> None:
        assert names("qubits 2\ncx q0, q1\ncx q0, q1\n") == []

    def test_cascading_cancellation_single_run(self) -> None:
        # x (y y) x collapses fully in one run via the wire stacks.
        assert names("qubits 1\nx q0\ny q0\ny q0\nx q0\n") == []


class TestBlocked:
    def test_different_qubits_do_not_cancel(self) -> None:
        assert names("qubits 2\nh q0\nh q1\n") == ["h", "h"]

    def test_intervening_gate_blocks(self) -> None:
        assert names("qubits 1\nh q0\nx q0\nh q0\n") == ["h", "x", "h"]

    def test_cx_reversed_operands_do_not_cancel(self) -> None:
        assert names("qubits 2\ncx q0, q1\ncx q1, q0\n") == ["cx", "cx"]

    def test_cz_is_symmetric(self) -> None:
        assert names("qubits 2\ncz q0, q1\ncz q1, q0\n") == []

    def test_swap_is_symmetric(self) -> None:
        assert names("qubits 2\nswap q0, q1\nswap q1, q0\n") == []

    def test_intervening_gate_on_one_wire_blocks_two_qubit_pair(self) -> None:
        src = "qubits 2\ncx q0, q1\nh q1\ncx q0, q1\n"
        assert names(src) == ["cx", "h", "cx"]

    def test_measure_blocks_cancellation(self) -> None:
        src = "qubits 1\nbits 1\nh q0\nmeasure q0 -> c0\nh q0\n"
        assert names(src) == ["h", "measure", "h"]

    def test_rotations_left_alone(self) -> None:
        src = "qubits 1\nrz(pi/4) q0\nrz(-pi/4) q0\n"
        assert names(src) == ["rz", "rz"]


class TestSemantics:
    def test_pass_preserves_semantics(self) -> None:
        src = (
            "qubits 3\nh q0\nx q1\nx q1\ncx q0, q1\ncx q0, q1\n"
            "t q2\ntdg q2\nswap q0, q2\n"
        )
        original = parse(src)
        assert check_equivalence(original, PASS.run(original)).equivalent

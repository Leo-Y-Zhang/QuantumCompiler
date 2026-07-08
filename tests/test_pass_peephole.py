"""Tests for the peephole-identity pass (h x h -> z, h z h -> x)."""

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

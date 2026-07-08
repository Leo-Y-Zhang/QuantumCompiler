"""Tests for opt-in dead-code elimination and its documented caveat."""

from daedalus.parser import parse
from daedalus.passes.dead_code import DeadCodeElimination
from daedalus.verify import check_equivalence

PASS = DeadCodeElimination()


def names(src: str) -> list[str]:
    return [g.name for g in PASS.run(parse(src)).gates]


class TestElimination:
    def test_gate_on_unmeasured_disconnected_qubit_removed(self) -> None:
        src = "qubits 2\nbits 1\nx q0\nh q1\nmeasure q0 -> c0\n"
        assert names(src) == ["x", "measure"]

    def test_no_measurements_removes_everything(self) -> None:
        assert names("qubits 2\nh q0\ncx q0, q1\n") == []

    def test_measures_are_never_removed(self) -> None:
        src = "qubits 1\nbits 1\nmeasure q0 -> c0\n"
        assert names(src) == ["measure"]


class TestLiveness:
    def test_entangled_qubit_is_live(self) -> None:
        # q1 is never measured but interacts with measured q0.
        src = "qubits 2\nbits 1\nh q1\ncx q1, q0\nmeasure q0 -> c0\n"
        assert names(src) == ["h", "cx", "measure"]

    def test_transitive_liveness(self) -> None:
        # q2 -> q1 -> q0 (measured): the whole chain is live.
        src = "qubits 3\nbits 1\nh q2\ncx q2, q1\ncx q1, q0\nmeasure q0 -> c0\n"
        assert names(src) == ["h", "cx", "cx", "measure"]

    def test_dead_island_removed_next_to_live_chain(self) -> None:
        src = (
            "qubits 4\nbits 1\nh q0\ncx q0, q1\nmeasure q1 -> c0\n"
            "h q2\ncx q2, q3\n"
        )
        assert names(src) == ["h", "cx", "measure"]


class TestCaveat:
    def test_dce_changes_unobserved_state(self) -> None:
        """DCE is intentionally NOT statevector-preserving.

        Removing gates on unmeasured qubits changes the (unobserved) global
        state, so the full-state equivalence checker must flag it. This is
        exactly why the pass is off by default.
        """
        original = parse("qubits 2\nbits 1\nx q0\nh q1\nmeasure q0 -> c0\n")
        optimized = PASS.run(original)
        assert not check_equivalence(original, optimized).equivalent

    def test_dce_preserves_state_when_nothing_is_dead(self) -> None:
        original = parse("qubits 2\nbits 2\nh q0\ncx q0, q1\nmeasure q0 -> c0\nmeasure q1 -> c1\n")
        optimized = PASS.run(original)
        assert optimized.gates == original.gates
        assert check_equivalence(original, optimized).equivalent

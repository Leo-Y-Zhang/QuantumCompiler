"""control-flip: h a; h b; cx a,b; h a; h b  ->  cx b,a (Hadamard sandwich).

(H (x) H) . CX(a,b) . (H (x) H) == CX(b,a). The pass matches the five-gate
window and rewrites it to a single reversed cx (5 -> 1). Every rewrite is
proven equivalent by the exact unitary.
"""

from daedalus.parser import parse
from daedalus.passes import PassManager, default_passes
from daedalus.passes.control_flip import ControlFlip
from daedalus.unitary import prove_circuit_equivalence

PASS = ControlFlip()


def names(circuit):
    return [g.name for g in circuit.gates]


class TestFires:
    def test_reverses_cx(self) -> None:
        original = parse("qubits 2\nh q0\nh q1\ncx q0, q1\nh q0\nh q1\n")
        out = PASS.run(original)
        assert [(g.name, g.qubits) for g in out.gates] == [("cx", (1, 0))]
        assert prove_circuit_equivalence(original, out).equivalent

    def test_reverses_cx_the_other_way(self) -> None:
        original = parse("qubits 2\nh q0\nh q1\ncx q1, q0\nh q0\nh q1\n")
        out = PASS.run(original)
        assert [(g.name, g.qubits) for g in out.gates] == [("cx", (0, 1))]
        assert prove_circuit_equivalence(original, out).equivalent

    def test_fires_within_larger_circuit(self) -> None:
        # A sandwiched cx on q0,q1 while q2 carries unrelated gates.
        original = parse(
            "qubits 3\nt q2\nh q0\nh q1\ncx q0, q1\nh q0\nh q1\ntdg q2\n"
        )
        out = PASS.run(original)
        assert names(out) == ["t", "cx", "tdg"]
        assert prove_circuit_equivalence(original, out).equivalent


class TestDoesNotFire:
    def test_extra_gate_breaks_adjacency(self) -> None:
        original = parse("qubits 2\nh q0\nh q1\ncx q0, q1\nx q0\nh q0\nh q1\n")
        assert PASS.run(original) is original

    def test_missing_hadamard_on_one_wire(self) -> None:
        original = parse("qubits 2\nh q0\ncx q0, q1\nh q0\n")
        assert PASS.run(original) is original

    def test_only_leading_sandwich(self) -> None:
        original = parse("qubits 2\nh q0\nh q1\ncx q0, q1\n")
        assert PASS.run(original) is original

    def test_wrong_gate_in_sandwich(self) -> None:
        original = parse("qubits 2\nx q0\nh q1\ncx q0, q1\nh q0\nh q1\n")
        assert PASS.run(original) is original


class TestPipeline:
    def test_flip_then_cancel_collapses_to_identity(self) -> None:
        # (H(x)H)CX(0,1)(H(x)H) . CX(1,0) == CX(1,0).CX(1,0) == I.
        src = "qubits 2\nh q0\nh q1\ncx q0, q1\nh q0\nh q1\ncx q1, q0\n"
        optimized, _ = PassManager(default_passes()).run(parse(src))
        assert optimized.gates == []

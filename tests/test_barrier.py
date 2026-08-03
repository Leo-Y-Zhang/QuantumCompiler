"""barrier: an optimization fence honored by every pass.

A barrier is a no-op for simulation but blocks any rewrite from moving a gate
across it. Each test pairs a circuit that optimizes freely with the same circuit
fenced by a barrier that must stay un-optimized.
"""

import pytest

from quantum_compiler.ir import Gate, dump
from quantum_compiler.parser import parse
from quantum_compiler.passes import PassManager, default_passes
from quantum_compiler.qasm import emit_qasm, parse_qasm
from quantum_compiler.sim import simulate
from quantum_compiler.verify import check_equivalence


def names(circuit):
    return [g.name for g in circuit.gates]


def optimize(circuit):
    return PassManager(default_passes()).run(circuit)[0]


class TestParsing:
    def test_single_qubit_barrier(self) -> None:
        circuit = parse("qubits 2\nbarrier q0\n")
        assert circuit.gates == [Gate("barrier", (0,))]

    def test_multi_qubit_barrier(self) -> None:
        circuit = parse("qubits 3\nbarrier q0, q2\n")
        assert circuit.gates == [Gate("barrier", (0, 2))]

    def test_duplicate_qubit_rejected(self) -> None:
        with pytest.raises(Exception, match="duplicate"):
            parse("qubits 2\nbarrier q0, q0\n")

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(Exception, match="out of range"):
            parse("qubits 2\nbarrier q5\n")

    def test_dump_roundtrips(self) -> None:
        src = "qubits 3\nh q0\nbarrier q0, q1, q2\nx q1\n"
        assert dump(parse(src)) == src


class TestSimulation:
    def test_barrier_is_identity(self) -> None:
        with_barrier = simulate(parse("qubits 2\nh q0\nbarrier q0, q1\ncx q0, q1\n"))
        without = simulate(parse("qubits 2\nh q0\ncx q0, q1\n"))
        for a, b in zip(with_barrier, without, strict=True):
            assert a == pytest.approx(b)


class TestFenceBlocksPasses:
    def test_cancel_inverses_blocked(self) -> None:
        assert names(optimize(parse("qubits 1\nx q0\nbarrier q0\nx q0\n"))) == [
            "x",
            "barrier",
            "x",
        ]
        # Same circuit without the fence collapses entirely.
        assert optimize(parse("qubits 1\nx q0\nx q0\n")).gates == []

    def test_merge_rotations_blocked(self) -> None:
        fenced = optimize(parse("qubits 1\nrz(0.3) q0\nbarrier q0\nrz(0.4) q0\n"))
        assert names(fenced) == ["rz", "barrier", "rz"]
        assert names(optimize(parse("qubits 1\nrz(0.3) q0\nrz(0.4) q0\n"))) == ["rz"]

    def test_peephole_blocked(self) -> None:
        fenced = optimize(parse("qubits 1\nh q0\nbarrier q0\nx q0\nh q0\n"))
        assert "z" not in names(fenced)  # h x h -> z is prevented
        assert names(optimize(parse("qubits 1\nh q0\nx q0\nh q0\n"))) == ["z"]

    def test_commute_cancel_blocked(self) -> None:
        # The rz pair would cancel across the cx control, but the barrier blocks
        # it; they survive (lowered to t/tdg by canonicalize) instead of vanishing.
        src = "qubits 2\nrz(pi/4) q0\nbarrier q0\ncx q0, q1\nrz(-pi/4) q0\n"
        fenced = names(optimize(parse(src)))
        assert "t" in fenced and "tdg" in fenced and "barrier" in fenced
        no_fence = "qubits 2\nrz(pi/4) q0\ncx q0, q1\nrz(-pi/4) q0\n"
        assert names(optimize(parse(no_fence))) == ["cx"]

    def test_control_flip_blocked(self) -> None:
        src = "qubits 2\nh q0\nh q1\nbarrier q0\ncx q0, q1\nh q0\nh q1\n"
        # The barrier on q0 breaks the sandwich; cx keeps its original direction.
        cx = [g for g in optimize(parse(src)).gates if g.name == "cx"]
        assert cx == [Gate("cx", (0, 1))]


class TestSemanticsPreserved:
    def test_optimized_with_barrier_still_verified(self) -> None:
        src = "qubits 2\nh q0\nrz(pi/4) q0\nbarrier q0, q1\nrz(pi/4) q0\ncx q0, q1\n"
        original = parse(src)
        assert check_equivalence(original, optimize(original)).equivalent


class TestQasmInterop:
    def test_emit_barrier(self) -> None:
        qasm = emit_qasm(parse("qubits 2\nh q0\nbarrier q0, q1\n"))
        assert "barrier q[0],q[1];" in qasm

    def test_qasm_barrier_roundtrip(self) -> None:
        qasm = 'OPENQASM 2.0;\nqreg q[2];\nh q[0];\nbarrier q[0],q[1];\ncx q[0],q[1];\n'
        circuit = parse_qasm(qasm)
        assert names(circuit) == ["h", "barrier", "cx"]
        assert circuit.gates[1].qubits == (0, 1)

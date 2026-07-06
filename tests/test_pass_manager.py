"""Pass-manager tests: fixpoint behavior, stats, and full-pipeline verification."""

import math
import random

from qforge.ir import Circuit, Gate
from qforge.parser import parse
from qforge.passes import PassManager, default_passes
from qforge.verify import check_equivalence


def optimize(src: str):
    return PassManager(default_passes()).run(parse(src))


class TestFixpoint:
    def test_multi_iteration_fixpoint(self) -> None:
        # Iteration 1: peephole turns h x h into z (cancel finds nothing first).
        # Iteration 2: cancel-inverses removes the new z z pair.
        circuit, stats = optimize("qubits 1\nh q0\nx q0\nh q0\nz q0\n")
        assert circuit.gates == []
        assert max(s.iteration for s in stats) >= 2

    def test_fixpoint_terminates_on_already_optimal(self) -> None:
        circuit, stats = optimize("qubits 2\nh q0\ncx q0, q1\n")
        assert [g.name for g in circuit.gates] == ["h", "cx"]

    def test_stats_chain_is_consistent(self) -> None:
        _, stats = optimize("qubits 1\nh q0\nh q0\nx q0\nx q0\n")
        for s in stats:
            assert s.gates_after <= s.gates_before
        # Consecutive entries chain: after of one == before of the next.
        for a, b in zip(stats, stats[1:]):
            assert a.gates_after == b.gates_before

    def test_deterministic(self) -> None:
        src = "qubits 2\nh q0\nx q0\nh q0\nrz(pi/4) q0\nrz(pi/4) q0\ncx q0, q1\n"
        c1, s1 = optimize(src)
        c2, s2 = optimize(src)
        assert c1.gates == c2.gates
        assert s1 == s2

    def test_empty_circuit(self) -> None:
        circuit, _ = optimize("qubits 1\n")
        assert circuit.gates == []


class TestPipelineSemantics:
    def test_example_program_verified(self) -> None:
        src = (
            "qubits 3\nbits 3\nh q0\ncx q0, q1\nrz(pi/4) q1\nrz(pi/4) q1\n"
            "x q2\nx q2\nmeasure q0 -> c0\n"
        )
        original = parse(src)
        optimized, _ = PassManager(default_passes()).run(original)
        assert len(optimized.gates) < len(original.gates)
        assert check_equivalence(original, optimized).equivalent

    def test_measures_preserved_verbatim(self) -> None:
        src = "qubits 2\nbits 2\nh q0\nh q0\nmeasure q0 -> c0\nmeasure q1 -> c1\n"
        optimized, _ = optimize(src)
        measures = [g for g in optimized.gates if g.name == "measure"]
        assert measures == [Gate("measure", (0,), bit=0), Gate("measure", (1,), bit=1)]

    def test_seeded_fuzz_circuits_stay_equivalent(self) -> None:
        """The headline guarantee: the default pipeline preserves semantics."""
        for seed in range(12):
            original = _random_circuit(random.Random(seed))
            optimized, _ = PassManager(default_passes()).run(original)
            assert len(optimized.gates) <= len(original.gates)
            result = check_equivalence(original, optimized)
            assert result.equivalent, f"seed {seed}: max_error={result.max_error}"


def _random_circuit(rng: random.Random, num_qubits: int = 4, num_gates: int = 30) -> Circuit:
    plain = ["h", "x", "y", "z", "s", "sdg", "t", "tdg"]
    rotations = ["rx", "ry", "rz"]
    pairs = ["cx", "cz", "swap"]
    angles = [math.pi / 4, -math.pi / 4, math.pi / 2, math.pi, 0.3]
    gates: list[Gate] = []
    for _ in range(num_gates):
        roll = rng.random()
        if roll < 0.5:
            gates.append(Gate(rng.choice(plain), (rng.randrange(num_qubits),)))
        elif roll < 0.75:
            gates.append(
                Gate(rng.choice(rotations), (rng.randrange(num_qubits),), angle=rng.choice(angles))
            )
        else:
            a = rng.randrange(num_qubits)
            b = rng.choice([q for q in range(num_qubits) if q != a])
            gates.append(Gate(rng.choice(pairs), (a, b)))
    return Circuit(num_qubits=num_qubits, num_bits=0, gates=gates)

"""Exact-unitary construction and up-to-global-phase comparison.

These lock the *exact* proof engine: it must build the correct circuit unitary,
accept global-phase differences, reject relative-phase ones, and agree with the
randomized oracle wherever both apply.
"""

import cmath
import math
import random

import pytest

from quantum_compiler.parser import parse
from quantum_compiler.unitary import (
    PROOF_MAX_QUBITS,
    circuit_unitary,
    compare_unitaries,
    prove_circuit_equivalence,
)
from quantum_compiler.verify import check_equivalence

SQRT1_2 = 1 / math.sqrt(2)


def approx_matrix(actual, expected, tol=1e-12):
    assert len(actual) == len(expected)
    for row_a, row_e in zip(actual, expected, strict=True):
        assert len(row_a) == len(row_e)
        for a, e in zip(row_a, row_e, strict=True):
            assert abs(a - e) < tol


class TestCircuitUnitary:
    def test_empty_circuit_is_identity(self):
        u = circuit_unitary(parse("qubits 2\n"))
        approx_matrix(u, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])

    def test_hadamard(self):
        u = circuit_unitary(parse("qubits 1\nh q0\n"))
        approx_matrix(u, [[SQRT1_2, SQRT1_2], [SQRT1_2, -SQRT1_2]])

    def test_pauli_x(self):
        u = circuit_unitary(parse("qubits 1\nx q0\n"))
        approx_matrix(u, [[0, 1], [1, 0]])

    def test_s_gate_is_diag_1_i(self):
        u = circuit_unitary(parse("qubits 1\ns q0\n"))
        approx_matrix(u, [[1, 0], [0, 1j]])

    def test_t_gate_phase(self):
        u = circuit_unitary(parse("qubits 1\nt q0\n"))
        approx_matrix(u, [[1, 0], [0, cmath.exp(1j * math.pi / 4)]])

    def test_cx_permutation_lsb_control(self):
        # cx q0,q1: control=q0 (LSB). Basis index bit0=q0, bit1=q1.
        # |01>(idx1,q0=1)->flip q1->|11>(idx3); |11>(idx3)->|01>(idx1).
        u = circuit_unitary(parse("qubits 2\ncx q0, q1\n"))
        expected = [[0.0] * 4 for _ in range(4)]
        for col, row in {0: 0, 1: 3, 2: 2, 3: 1}.items():
            expected[row][col] = 1.0
        approx_matrix(u, expected)

    def test_is_unitary(self):
        # U U^dagger = I for a nontrivial circuit.
        u = circuit_unitary(parse("qubits 2\nh q0\ncx q0, q1\nrz(pi/3) q1\n"))
        dim = len(u)
        for i in range(dim):
            for j in range(dim):
                dot = sum(u[i][k] * u[j][k].conjugate() for k in range(dim))
                assert abs(dot - (1.0 if i == j else 0.0)) < 1e-12

    def test_rejects_too_many_qubits(self):
        with pytest.raises(ValueError, match="qubits"):
            circuit_unitary(parse(f"qubits {PROOF_MAX_QUBITS + 1}\n"))


class TestCompareUnitaries:
    def test_identical_equivalent(self):
        u = circuit_unitary(parse("qubits 1\nh q0\n"))
        result = compare_unitaries(u, u)
        assert result.equivalent
        assert result.diff_norm < 1e-12
        assert result.process_fidelity == pytest.approx(1.0, abs=1e-12)

    def test_global_phase_accepted(self):
        u = circuit_unitary(parse("qubits 1\nh q0\n"))
        phase = cmath.exp(1j * 0.777)
        u_scaled = [[phase * x for x in row] for row in u]
        result = compare_unitaries(u, u_scaled)
        assert result.equivalent
        assert result.process_fidelity == pytest.approx(1.0, abs=1e-9)

    def test_negation_is_global_phase(self):
        # Z vs -Z differ only by global phase -1.
        z = circuit_unitary(parse("qubits 1\nz q0\n"))
        neg_z = [[-x for x in row] for row in z]
        assert compare_unitaries(z, neg_z).equivalent

    def test_relative_phase_rejected(self):
        # I vs Z agree on basis states up to a per-state phase but differ by a
        # relative phase; the exact check must reject them.
        identity = circuit_unitary(parse("qubits 1\n"))
        z = circuit_unitary(parse("qubits 1\nz q0\n"))
        result = compare_unitaries(identity, z)
        assert not result.equivalent
        assert result.process_fidelity < 0.99

    def test_dimension_mismatch_rejected(self):
        one = circuit_unitary(parse("qubits 1\n"))
        two = circuit_unitary(parse("qubits 2\n"))
        assert not compare_unitaries(one, two).equivalent


class TestProveCircuitEquivalence:
    def test_bell_with_redundant_pair(self):
        original = parse("qubits 2\nh q0\nx q1\nx q1\ncx q0, q1\n")
        optimized = parse("qubits 2\nh q0\ncx q0, q1\n")
        assert prove_circuit_equivalence(original, optimized).equivalent

    def test_peephole_global_phase_hyh(self):
        # h y h == -y: a genuine global-phase change the exact proof accepts.
        assert prove_circuit_equivalence(
            parse("qubits 1\nh q0\ny q0\nh q0\n"), parse("qubits 1\ny q0\n")
        ).equivalent

    def test_wrong_rewrite_caught(self):
        assert not prove_circuit_equivalence(
            parse("qubits 1\nh q0\n"), parse("qubits 1\nx q0\n")
        ).equivalent

    def test_differing_qubit_count_not_equivalent(self):
        assert not prove_circuit_equivalence(
            parse("qubits 1\n"), parse("qubits 2\n")
        ).equivalent

    def test_agrees_with_randomized_oracle(self):
        # On a batch of random small circuits, the exact and randomized checks
        # must reach the same verdict for both a true and a corrupted rewrite.
        rng = random.Random(20260709)
        names1 = ["h", "x", "y", "z", "s", "sdg", "t", "tdg"]
        for _ in range(60):
            n = rng.randint(1, 3)
            lines = [f"qubits {n}"]
            for _ in range(rng.randint(1, 6)):
                if n >= 2 and rng.random() < 0.4:
                    a, b = rng.sample(range(n), 2)
                    lines.append(f"{rng.choice(['cx', 'cz', 'swap'])} q{a}, q{b}")
                elif rng.random() < 0.3:
                    axis = rng.choice(["rx", "ry", "rz"])
                    lines.append(f"{axis}({rng.uniform(-3, 3)}) q{rng.randrange(n)}")
                else:
                    lines.append(f"{rng.choice(names1)} q{rng.randrange(n)}")
            circuit = parse("\n".join(lines) + "\n")
            # identity rewrite: must be equivalent under both oracles
            exact = prove_circuit_equivalence(circuit, circuit)
            rand = check_equivalence(circuit, circuit)
            assert exact.equivalent == rand.equivalent is True
            # corrupt by appending one X: both oracles should usually agree.
            if circuit.gates:
                corrupt = circuit.replace_gates(
                    [*circuit.gates, type(circuit.gates[0])("x", (0,))]
                )
                assert (
                    prove_circuit_equivalence(circuit, corrupt).equivalent
                    == check_equivalence(circuit, corrupt).equivalent
                )

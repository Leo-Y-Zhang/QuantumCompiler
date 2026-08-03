"""Equivalence-prover tests: witnesses on failure, ddmin shrink to 1-minimal pairs."""

import pytest

from quantum_compiler.equiv import find_witness, shrink_counterexample
from quantum_compiler.ir import Circuit
from quantum_compiler.parser import parse
from quantum_compiler.verify import prove_equivalence


def assert_one_minimal(a: Circuit, b: Circuit) -> None:
    """Assert the ddmin guarantee: dropping any single gate makes the pair equivalent."""
    for index in range(len(a.gates)):
        reduced = a.replace_gates(g for i, g in enumerate(a.gates) if i != index)
        assert prove_equivalence(reduced, b).equivalent, (
            f"pair still disagrees after dropping gate {index} of A - not 1-minimal"
        )
    for index in range(len(b.gates)):
        reduced = b.replace_gates(g for i, g in enumerate(b.gates) if i != index)
        assert prove_equivalence(a, reduced).equivalent, (
            f"pair still disagrees after dropping gate {index} of B - not 1-minimal"
        )


class TestFindWitness:
    def test_equivalent_circuits_have_no_witness(self) -> None:
        a = parse("qubits 2\nh q0\nx q1\nx q1\ncx q0, q1\n")
        b = parse("qubits 2\nh q0\ncx q0, q1\n")
        assert find_witness(a, b) is None

    def test_global_phase_difference_has_no_witness(self) -> None:
        # rz(2*pi) == -I: a pure global phase must not be witnessed as a failure.
        a = parse("qubits 1\nrz(2*pi) q0\n")
        b = parse("qubits 1\n")
        assert find_witness(a, b) is None

    def test_x_vs_identity_fails_on_basis_zero(self) -> None:
        a = parse("qubits 1\n")
        b = parse("qubits 1\nx q0\n")
        witness = find_witness(a, b)
        assert witness is not None
        assert witness.basis_index == 0
        assert witness.label() == "|0>"
        assert witness.max_error > 0.9

    def test_relative_phase_z_witnessed_on_basis_one(self) -> None:
        # z fixes |0> and negates |1|; with the shared phase fixed on the first
        # battery input (|0>), the first failing input is |1> with error 2.
        a = parse("qubits 1\n")
        b = parse("qubits 1\nz q0\n")
        witness = find_witness(a, b)
        assert witness is not None
        assert witness.basis_index == 1
        assert witness.label() == "|1>"
        assert abs(witness.max_error - 2.0) < 1e-9
        assert witness.worst_index == 1

    def test_label_orders_most_significant_qubit_first(self) -> None:
        # cx q0->q1 acts only when q0 = 1, i.e. first on basis index 1 = |01>.
        a = parse("qubits 2\n")
        b = parse("qubits 2\ncx q0, q1\n")
        witness = find_witness(a, b)
        assert witness is not None
        assert witness.basis_index == 1
        assert witness.label() == "|01>"

    def test_witness_records_both_outputs(self) -> None:
        a = parse("qubits 1\n")
        b = parse("qubits 1\nx q0\n")
        witness = find_witness(a, b)
        assert witness is not None
        assert abs(witness.output_a[0] - 1) < 1e-12  # identity keeps |0>
        assert abs(witness.output_b[1] - 1) < 1e-12  # x maps |0> to |1>

    def test_phase_anchor_is_the_lowest_near_peak_index(self) -> None:
        # 8-qubit GHZ ladder ending t vs tdg: the GHZ state has two amplitudes
        # tied at 1/sqrt(2), and platform rounding must not be allowed to pick
        # the anchor between them. The anchor is defined as the lowest index
        # within 1e-9 of the peak, i.e. |00000000>, giving phase 1 and a worst
        # row (|11111111>) whose raw A/B amplitudes visibly differ.
        ladder = "qubits 8\nh q0\n" + "".join(f"cx q{i}, q{i + 1}\n" for i in range(7))
        a = parse(ladder + "t q7\n")
        b = parse(ladder + "tdg q7\n")
        witness = find_witness(a, b)
        assert witness is not None
        assert witness.basis_index == 0
        assert abs(witness.phase - 1) < 1e-9
        assert witness.worst_index == 255
        assert abs(witness.max_error - 1.0) < 1e-9
        assert abs(witness.output_a[255] - witness.output_b[255]) > 0.9

    def test_mismatched_qubit_counts_have_no_witness(self) -> None:
        a = parse("qubits 1\nh q0\n")
        b = parse("qubits 2\nh q0\n")
        assert find_witness(a, b) is None

    def test_none_witness_despite_negative_verdict_near_tolerance(self) -> None:
        # Frobenius-vs-per-amplitude metric mismatch (documented in the
        # find_witness docstring): a 2-qubit rz(9.5e-10) vs identity gives an
        # exact-engine diff norm of sqrt(2) * 9.5e-10 > atol (accumulated over
        # the whole unitary) while no single amplitude of any battery input
        # errs above atol. The oracle says NOT equivalent; the witness search
        # honestly comes back empty. Every basis state IS sampled here, so the
        # cause is the metric, not battery coverage.
        a = parse("qubits 2\n")
        b = parse("qubits 2\nrz(0.00000000095) q0\n")
        proof = prove_equivalence(a, b)
        assert not proof.equivalent
        assert 1e-9 < proof.max_error < 2e-9
        assert find_witness(a, b) is None


class TestShrinkCounterexample:
    def test_shrunk_pair_still_disagrees_and_is_one_minimal(self) -> None:
        a = parse("qubits 2\nh q0\ncx q0, q1\nx q1\n")
        b = parse("qubits 2\nh q0\ncx q0, q1\n")
        result = shrink_counterexample(a, b)
        assert result.gates_before == 5
        assert result.gates_after <= 2
        assert result.gates_after == len(result.circuit_a.gates) + len(result.circuit_b.gates)
        assert not prove_equivalence(result.circuit_a, result.circuit_b).equivalent
        assert_one_minimal(result.circuit_a, result.circuit_b)

    def test_shrink_reports_oracle_calls(self) -> None:
        a = parse("qubits 1\nx q0\nz q0\n")
        b = parse("qubits 1\nz q0\nz q0\n")
        result = shrink_counterexample(a, b)
        assert result.oracle_calls >= 1
        assert result.gates_after < result.gates_before
        assert not prove_equivalence(result.circuit_a, result.circuit_b).equivalent
        assert_one_minimal(result.circuit_a, result.circuit_b)

    def test_measure_and_barrier_noise_is_removed(self) -> None:
        # Neither measure nor barrier affects the compared state, so a 1-minimal
        # counterexample can never keep one.
        a = parse("qubits 2\nbits 1\nh q0\nbarrier q0, q1\nz q0\nmeasure q0 -> c0\n")
        b = parse("qubits 2\nbits 1\nh q0\nmeasure q0 -> c0\n")
        result = shrink_counterexample(a, b)
        names = {g.name for g in result.circuit_a.gates}
        names |= {g.name for g in result.circuit_b.gates}
        assert "barrier" not in names
        assert "measure" not in names
        assert not prove_equivalence(result.circuit_a, result.circuit_b).equivalent
        assert_one_minimal(result.circuit_a, result.circuit_b)

    def test_larger_pair_shrinks_to_a_small_core(self) -> None:
        a = parse(
            "qubits 3\nh q0\ncx q0, q1\ncx q1, q2\nt q2\ns q0\nsdg q0\n"
        )
        b = parse(
            "qubits 3\nh q0\ncx q0, q1\ncx q1, q2\ntdg q2\n"
        )
        result = shrink_counterexample(a, b)
        assert result.gates_before == 10
        assert result.gates_after <= 3
        assert not prove_equivalence(result.circuit_a, result.circuit_b).equivalent
        assert_one_minimal(result.circuit_a, result.circuit_b)

    def test_shrinking_an_equivalent_pair_raises(self) -> None:
        a = parse("qubits 1\nh q0\nh q0\n")
        b = parse("qubits 1\n")
        with pytest.raises(ValueError, match="equivalent"):
            shrink_counterexample(a, b)

    def test_shrunk_circuits_keep_register_sizes(self) -> None:
        a = parse("qubits 2\nbits 2\nx q1\n")
        b = parse("qubits 2\nbits 2\n")
        result = shrink_counterexample(a, b)
        assert result.circuit_a.num_qubits == 2
        assert result.circuit_a.num_bits == 2
        assert result.circuit_b.num_qubits == 2

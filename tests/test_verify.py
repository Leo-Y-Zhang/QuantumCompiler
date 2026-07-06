"""Equivalence-checker tests: equal circuits, unequal circuits, phase traps."""

from qforge.parser import parse
from qforge.verify import check_equivalence


class TestEquivalent:
    def test_identical_circuits(self) -> None:
        a = parse("qubits 2\nh q0\ncx q0, q1\n")
        result = check_equivalence(a, a)
        assert result.equivalent
        assert result.max_error < 1e-12
        assert result.inputs_checked > 0

    def test_redundant_gates_removed(self) -> None:
        a = parse("qubits 2\nh q0\nx q1\nx q1\ncx q0, q1\n")
        b = parse("qubits 2\nh q0\ncx q0, q1\n")
        assert check_equivalence(a, b).equivalent

    def test_global_phase_is_accepted(self) -> None:
        # rz(2*pi) == -I: differs from the empty circuit only by global phase.
        a = parse("qubits 1\nrz(2*pi) q0\n")
        b = parse("qubits 1\n")
        assert check_equivalence(a, b).equivalent

    def test_merged_rotations(self) -> None:
        a = parse("qubits 1\nrz(pi/4) q0\nrz(pi/4) q0\n")
        b = parse("qubits 1\nrz(pi/2) q0\n")
        assert check_equivalence(a, b).equivalent

    def test_hxh_equals_z(self) -> None:
        a = parse("qubits 1\nh q0\nx q0\nh q0\n")
        b = parse("qubits 1\nz q0\n")
        assert check_equivalence(a, b).equivalent


class TestNotEquivalent:
    def test_x_vs_z(self) -> None:
        a = parse("qubits 1\nx q0\n")
        b = parse("qubits 1\nz q0\n")
        result = check_equivalence(a, b)
        assert not result.equivalent
        assert result.max_error > 0.1

    def test_z_vs_identity_relative_phase_trap(self) -> None:
        # z fixes every basis state up to a per-state phase; a naive checker
        # that allows a different phase per input would wrongly accept this.
        a = parse("qubits 1\nz q0\n")
        b = parse("qubits 1\n")
        assert not check_equivalence(a, b).equivalent

    def test_close_rotations_differ(self) -> None:
        a = parse("qubits 1\nrz(0.3) q0\n")
        b = parse("qubits 1\nrz(0.4) q0\n")
        assert not check_equivalence(a, b).equivalent

    def test_different_qubit_counts(self) -> None:
        a = parse("qubits 1\nh q0\n")
        b = parse("qubits 2\nh q0\n")
        result = check_equivalence(a, b)
        assert not result.equivalent
        assert "qubit" in result.detail

    def test_control_target_swapped(self) -> None:
        a = parse("qubits 2\ncx q0, q1\n")
        b = parse("qubits 2\ncx q1, q0\n")
        assert not check_equivalence(a, b).equivalent


class TestDeterminism:
    def test_repeated_runs_identical(self) -> None:
        a = parse("qubits 3\nh q0\ncx q0, q1\nrz(0.3) q2\n")
        b = parse("qubits 3\nh q0\ncx q0, q1\nrz(0.3) q2\nz q2\n")
        r1 = check_equivalence(a, b)
        r2 = check_equivalence(a, b)
        assert (r1.equivalent, r1.max_error) == (r2.equivalent, r2.max_error)

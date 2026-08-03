"""Equivalence-checker tests: equal circuits, unequal circuits, phase traps."""

from quantum_compiler.parser import parse
from quantum_compiler.verify import check_equivalence, check_routing_equivalence, prove_equivalence


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


class TestProveEquivalence:
    def test_small_circuit_uses_exact_engine(self) -> None:
        a = parse("qubits 2\nh q0\nx q1\nx q1\ncx q0, q1\n")
        b = parse("qubits 2\nh q0\ncx q0, q1\n")
        result = prove_equivalence(a, b)
        assert result.equivalent
        assert result.method == "exact-unitary"
        assert result.process_fidelity is not None
        assert result.process_fidelity > 1.0 - 1e-9

    def test_large_circuit_falls_back_to_randomized(self) -> None:
        big = parse("qubits 8\nh q0\ncx q0, q1\n")
        result = prove_equivalence(big, big)
        assert result.equivalent
        assert result.method == "randomized"
        assert result.process_fidelity is None

    def test_exact_catches_wrong_rewrite(self) -> None:
        result = prove_equivalence(parse("qubits 1\nh q0\n"), parse("qubits 1\nx q0\n"))
        assert not result.equivalent
        assert result.method == "exact-unitary"

    def test_qubit_count_mismatch(self) -> None:
        result = prove_equivalence(parse("qubits 1\n"), parse("qubits 2\n"))
        assert not result.equivalent
        assert "qubit" in result.detail

    def test_summary_mentions_method(self) -> None:
        exact = prove_equivalence(parse("qubits 1\nh q0\n"), parse("qubits 1\nh q0\n"))
        assert "exact" in exact.summary().lower()
        rand = prove_equivalence(parse("qubits 8\n"), parse("qubits 8\n"))
        assert "random" in rand.summary().lower()


class TestRoutingInitialLayout:
    """The routing oracle can start from a non-trivial initial placement.

    A SABRE-style router chooses where each logical qubit *starts*, so the
    oracle takes an optional ``initial_layout`` (default: the trivial layout,
    preserving the original behaviour byte for byte).
    """

    def test_relabeled_cx_accepted_only_under_its_initial_layout(self) -> None:
        # Logical cx q0,q1 placed with logical 0 on physical 1 and vice versa:
        # the physical circuit is cx q1,q0 and no SWAPs are needed.
        original = parse("qubits 2\ncx q0, q1\n")
        routed = parse("qubits 2\ncx q1, q0\n")
        layout = [1, 0]
        good = check_routing_equivalence(original, routed, layout, initial_layout=layout)
        assert good.equivalent
        # Under the trivial initial layout the same physical circuit is a
        # *different* operator (control and target swapped), so it must fail.
        bad = check_routing_equivalence(original, routed, [0, 1])
        assert not bad.equivalent

    def test_trivial_initial_layout_matches_default(self) -> None:
        original = parse("qubits 3\ncx q0, q2\nh q1\n")
        routed = parse("qubits 3\nswap q0, q1\ncx q1, q2\nh q0\n")
        layout = [1, 0, 2]
        default = check_routing_equivalence(original, routed, layout)
        explicit = check_routing_equivalence(original, routed, layout, initial_layout=[0, 1, 2])
        assert default.equivalent and explicit.equivalent
        assert default.max_error == explicit.max_error

    def test_invalid_initial_layout_rejected(self) -> None:
        original = parse("qubits 2\ncx q0, q1\n")
        routed = parse("qubits 2\ncx q0, q1\n")
        for layout in ([0], [0, 0], [0, 2]):
            result = check_routing_equivalence(
                original, routed, [0, 1], initial_layout=layout
            )
            assert not result.equivalent
            assert "initial layout" in result.detail

    def test_wrong_start_placement_detected(self) -> None:
        # x on logical 0 lands on physical 1 under this placement; claiming the
        # trivial start makes the routed circuit act on the wrong logical qubit.
        original = parse("qubits 2\nx q0\n")
        routed = parse("qubits 2\nx q1\n")
        assert check_routing_equivalence(
            original, routed, [1, 0], initial_layout=[1, 0]
        ).equivalent
        assert not check_routing_equivalence(original, routed, [0, 1]).equivalent

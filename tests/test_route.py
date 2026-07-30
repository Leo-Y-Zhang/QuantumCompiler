"""Router tests: adjacency is satisfied and routing is provably equivalent.

The verification here is the point of the feature: after routing, every 2-qubit
gate lands on a coupled pair, and the routed circuit reproduces the original up
to the reported final layout — checked both by the permutation-aware oracle and,
for small cases, by the exact unitary.
"""

import random
from pathlib import Path

import pytest

from daedalus.ir import Circuit, Gate
from daedalus.parser import parse
from daedalus.route import route
from daedalus.topology import CouplingMap
from daedalus.unitary import circuit_unitary, compare_unitaries
from daedalus.verify import _permute_embed, check_routing_equivalence

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

_TWO_QUBIT = {"cx", "cz", "swap"}


def assert_adjacency(routed: Circuit, coupling: CouplingMap) -> None:
    for gate in routed.gates:
        if gate.name in _TWO_QUBIT:
            a, b = gate.qubits
            assert coupling.are_adjacent(a, b), f"{gate.name} {gate.qubits} not coupled"


class TestBasicRouting:
    def test_line_cx_far_apart_inserts_swap(self) -> None:
        original = parse("qubits 3\ncx q0, q2\n")
        result = route(original, CouplingMap.line(3))
        assert result.swaps_added == 1
        assert result.final_layout == [1, 0, 2]
        assert [(g.name, g.qubits) for g in result.circuit.gates] == [
            ("swap", (0, 1)),
            ("cx", (1, 2)),
        ]
        assert_adjacency(result.circuit, CouplingMap.line(3))
        assert check_routing_equivalence(original, result.circuit, result.final_layout).equivalent

    def test_full_map_needs_no_swaps(self) -> None:
        original = parse("qubits 3\ncx q0, q2\n")
        result = route(original, CouplingMap.full(3))
        assert result.swaps_added == 0
        assert result.final_layout == [0, 1, 2]

    def test_adjacent_chain_no_swaps(self) -> None:
        original = parse("qubits 3\ncx q0, q1\ncx q1, q2\n")
        result = route(original, CouplingMap.line(3))
        assert result.swaps_added == 0
        assert check_routing_equivalence(original, result.circuit, result.final_layout).equivalent

    def test_single_qubit_only_is_identity_layout(self) -> None:
        original = parse("qubits 3\nh q0\nx q2\n")
        result = route(original, CouplingMap.line(3))
        assert result.swaps_added == 0
        assert result.final_layout == [0, 1, 2]

    def test_measures_follow_mapping(self) -> None:
        original = parse("qubits 3\nbits 1\ncx q0, q2\nmeasure q0 -> c0\n")
        result = route(original, CouplingMap.line(3))
        measure = next(g for g in result.circuit.gates if g.name == "measure")
        assert measure.qubits[0] == result.final_layout[0]
        assert measure.bit == 0

    def test_multi_qubit_barrier_survives_routing(self) -> None:
        # Regression: a barrier must keep all its wires (relabeled), not collapse
        # to its first operand. verify is blind to this (barrier = identity).
        original = parse("qubits 3\nh q0\nbarrier q0, q1, q2\ncx q0, q2\n")
        result = route(original, CouplingMap.line(3))
        barrier = next(g for g in result.circuit.gates if g.name == "barrier")
        assert len(barrier.qubits) == 3
        assert sorted(barrier.qubits) == [0, 1, 2]  # a permutation of all wires


def _permute_unitary_rows(matrix, n, layout):
    """Apply the final-layout qubit permutation to every column of *matrix*."""
    dim = len(matrix)
    columns = [
        _permute_embed([matrix[i][j] for i in range(dim)], n, n, layout)
        for j in range(dim)
    ]
    return [[columns[j][i] for j in range(dim)] for i in range(dim)]


class TestExactProof:
    def test_line_routed_cx_exact_unitary(self) -> None:
        original = parse("qubits 3\ncx q0, q2\n")
        result = route(original, CouplingMap.line(3))
        expected = _permute_unitary_rows(circuit_unitary(original), 3, result.final_layout)
        assert compare_unitaries(expected, circuit_unitary(result.circuit)).equivalent


class TestErrors:
    def test_too_few_physical_qubits(self) -> None:
        with pytest.raises(ValueError, match="coupling map"):
            route(parse("qubits 4\n"), CouplingMap.line(3))

    def test_disconnected_map_unroutable_gate(self) -> None:
        cm = CouplingMap(4, [(0, 1), (2, 3)])
        with pytest.raises(ValueError, match="disconnected"):
            route(parse("qubits 4\ncx q0, q2\n"), cm)


class TestRandomizedRouting:
    @pytest.mark.parametrize(
        "coupling",
        [
            CouplingMap.line(4),
            CouplingMap.ring(4),
            CouplingMap.grid(2, 2),
            CouplingMap.grid(2, 3),  # m > n case
            CouplingMap.full(4),
        ],
    )
    @pytest.mark.parametrize("strategy", ["greedy", "sabre"])
    def test_random_circuits_route_equivalently(
        self, coupling: CouplingMap, strategy: str
    ) -> None:
        rng = random.Random(4242)
        for _ in range(15):
            n = 4
            gates: list[Gate] = []
            for _ in range(rng.randint(2, 8)):
                if rng.random() < 0.6:
                    a, b = rng.sample(range(n), 2)
                    gates.append(Gate(rng.choice(["cx", "cz", "swap"]), (a, b)))
                else:
                    gates.append(Gate(rng.choice(["h", "x", "z"]), (rng.randrange(n),)))
            original = Circuit(n, 0, gates)
            result = route(original, coupling, strategy=strategy)
            assert_adjacency(result.circuit, coupling)
            assert sorted(result.final_layout) == sorted(set(result.final_layout))
            check = check_routing_equivalence(
                original,
                result.circuit,
                result.final_layout,
                initial_layout=result.initial_layout,
            )
            assert check.equivalent, f"routing changed semantics on {coupling.edges}"


class TestSabre:
    def test_far_apart_cx_routes_and_verifies(self) -> None:
        original = parse("qubits 3\ncx q0, q2\n")
        result = route(original, CouplingMap.line(3), strategy="sabre")
        assert_adjacency(result.circuit, CouplingMap.line(3))
        check = check_routing_equivalence(
            original, result.circuit, result.final_layout,
            initial_layout=result.initial_layout,
        )
        assert check.equivalent

    def test_initial_layout_is_a_valid_placement(self) -> None:
        original = parse("qubits 3\ncx q0, q2\ncx q0, q1\n")
        result = route(original, CouplingMap.line(4), strategy="sabre")
        assert len(result.initial_layout) == 3
        assert len(set(result.initial_layout)) == 3
        assert all(0 <= p < 4 for p in result.initial_layout)

    def test_greedy_reports_the_trivial_initial_layout(self) -> None:
        original = parse("qubits 3\ncx q0, q2\n")
        result = route(original, CouplingMap.line(3))
        assert result.initial_layout == [0, 1, 2]

    def test_deterministic_same_input_same_output(self) -> None:
        original = parse("qubits 4\nh q0\ncx q0, q3\ncz q1, q3\ncx q0, q2\n")
        first = route(original, CouplingMap.ring(4), strategy="sabre")
        second = route(original, CouplingMap.ring(4), strategy="sabre")
        assert first.circuit.gates == second.circuit.gates
        assert first.initial_layout == second.initial_layout
        assert first.final_layout == second.final_layout
        assert first.swaps_added == second.swaps_added

    def test_unknown_strategy_rejected(self) -> None:
        with pytest.raises(ValueError, match="strategy"):
            route(parse("qubits 2\ncx q0, q1\n"), CouplingMap.line(2), strategy="magic")

    def test_too_few_physical_qubits(self) -> None:
        with pytest.raises(ValueError, match="coupling map"):
            route(parse("qubits 4\n"), CouplingMap.line(3), strategy="sabre")

    def test_disconnected_map_unroutable_gate(self) -> None:
        cm = CouplingMap(4, [(0, 1), (2, 3)])
        with pytest.raises(ValueError, match="disconnected"):
            route(parse("qubits 4\ncx q0, q2\n"), cm, strategy="sabre")

    def test_disconnected_gate_in_lookahead_still_a_clean_error(self) -> None:
        # The first cx is blocked but routable; the second shares a wire with
        # it (so it sits in the lookahead window, not the front) and spans
        # components, where its infinite distance must not poison the SWAP
        # scores - the clean error comes when it reaches the front.
        cm = CouplingMap(4, [(0, 1), (1, 2)])  # qubit 3 isolated
        circuit = parse("qubits 4\ncx q0, q2\ncx q2, q3\n")
        with pytest.raises(ValueError, match="disconnected"):
            route(circuit, cm, strategy="sabre")

    def test_measures_follow_mapping(self) -> None:
        original = parse("qubits 3\nbits 1\ncx q0, q2\nmeasure q0 -> c0\n")
        result = route(original, CouplingMap.line(3), strategy="sabre")
        measure = next(g for g in result.circuit.gates if g.name == "measure")
        assert measure.qubits[0] == result.final_layout[0]
        assert measure.bit == 0

    def test_multi_qubit_barrier_survives_routing(self) -> None:
        original = parse("qubits 3\nh q0\nbarrier q0, q1, q2\ncx q0, q2\n")
        result = route(original, CouplingMap.line(3), strategy="sabre")
        barrier = next(g for g in result.circuit.gates if g.name == "barrier")
        assert len(barrier.qubits) == 3
        assert sorted(barrier.qubits) == [0, 1, 2]  # a permutation of all wires

    def test_barrier_blocks_reordering_across_it(self) -> None:
        # The dependency DAG must treat a barrier as order-blocking on its
        # wires: the cx may not be emitted before the barrier.
        original = parse("qubits 2\nh q0\nbarrier q0, q1\ncx q0, q1\n")
        result = route(original, CouplingMap.line(2), strategy="sabre")
        names = [g.name for g in result.circuit.gates]
        assert names.index("barrier") < names.index("cx")

    def test_never_worse_than_greedy_on_the_showcase_line(self) -> None:
        # Not a general claim - just pins the showcase example so a regression
        # in layout selection is caught. Greedy needs 4 swaps here.
        source = (EXAMPLES / "routed_line.qf").read_text(encoding="ascii")
        original = parse(source)
        greedy = route(original, CouplingMap.line(4))
        sabre = route(original, CouplingMap.line(4), strategy="sabre")
        assert sabre.swaps_added <= greedy.swaps_added

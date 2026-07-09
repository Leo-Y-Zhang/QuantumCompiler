"""Router tests: adjacency is satisfied and routing is provably equivalent.

The verification here is the point of the feature: after routing, every 2-qubit
gate lands on a coupled pair, and the routed circuit reproduces the original up
to the reported final layout — checked both by the permutation-aware oracle and,
for small cases, by the exact unitary.
"""

import random

import pytest

from daedalus.ir import Circuit, Gate
from daedalus.parser import parse
from daedalus.route import route
from daedalus.topology import CouplingMap
from daedalus.unitary import circuit_unitary, compare_unitaries
from daedalus.verify import _permute_embed, check_routing_equivalence

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
    def test_random_circuits_route_equivalently(self, coupling: CouplingMap) -> None:
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
            result = route(original, coupling)
            assert_adjacency(result.circuit, coupling)
            assert sorted(result.final_layout) == sorted(set(result.final_layout))
            check = check_routing_equivalence(original, result.circuit, result.final_layout)
            assert check.equivalent, f"routing changed semantics on {coupling.edges}"

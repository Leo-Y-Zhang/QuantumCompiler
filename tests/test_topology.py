"""Coupling-map topologies: adjacency, BFS distance, shortest paths."""

import pytest

from quantum_compiler.topology import CouplingMap


class TestConstructors:
    def test_line_edges(self) -> None:
        cm = CouplingMap.line(4)
        assert cm.num_qubits == 4
        assert cm.are_adjacent(0, 1)
        assert cm.are_adjacent(2, 3)
        assert not cm.are_adjacent(0, 2)
        assert not cm.are_adjacent(0, 3)

    def test_ring_wraps_around(self) -> None:
        cm = CouplingMap.ring(4)
        assert cm.are_adjacent(3, 0)
        assert cm.are_adjacent(0, 1)
        assert not cm.are_adjacent(0, 2)

    def test_ring_requires_three(self) -> None:
        with pytest.raises(ValueError):
            CouplingMap.ring(2)

    def test_full_all_pairs(self) -> None:
        cm = CouplingMap.full(3)
        for a in range(3):
            for b in range(3):
                if a != b:
                    assert cm.are_adjacent(a, b)

    def test_grid_neighbours(self) -> None:
        cm = CouplingMap.grid(2, 3)  # 6 qubits, id = row*3 + col
        assert cm.num_qubits == 6
        assert cm.are_adjacent(0, 1)  # (0,0)-(0,1)
        assert cm.are_adjacent(0, 3)  # (0,0)-(1,0)
        assert not cm.are_adjacent(0, 2)  # (0,0)-(0,2) not adjacent
        assert not cm.are_adjacent(0, 4)  # diagonal not adjacent

    def test_custom_edges(self) -> None:
        cm = CouplingMap(4, [(0, 1), (1, 2), (0, 3)])
        assert cm.are_adjacent(1, 0)  # undirected
        assert cm.are_adjacent(0, 3)
        assert not cm.are_adjacent(2, 3)

    def test_rejects_out_of_range_edge(self) -> None:
        with pytest.raises(ValueError):
            CouplingMap(2, [(0, 5)])

    def test_rejects_self_loop(self) -> None:
        with pytest.raises(ValueError):
            CouplingMap(2, [(1, 1)])


class TestDistanceAndPath:
    def test_distance_on_line(self) -> None:
        cm = CouplingMap.line(5)
        assert cm.distance(0, 0) == 0
        assert cm.distance(0, 1) == 1
        assert cm.distance(0, 4) == 4

    def test_shortest_path_on_line(self) -> None:
        cm = CouplingMap.line(5)
        assert cm.shortest_path(0, 3) == [0, 1, 2, 3]
        assert cm.shortest_path(3, 3) == [3]

    def test_shortest_path_uses_ring_shortcut(self) -> None:
        cm = CouplingMap.ring(6)
        # 0 to 5 is one hop the wrap-around way.
        assert cm.distance(0, 5) == 1
        assert cm.shortest_path(0, 5) in ([0, 5],)

    def test_grid_distance_is_manhattan(self) -> None:
        cm = CouplingMap.grid(3, 3)
        assert cm.distance(0, 8) == 4  # (0,0) to (2,2)

    def test_neighbours_sorted(self) -> None:
        cm = CouplingMap.line(3)
        assert cm.neighbours(1) == [0, 2]


class TestConnectivity:
    def test_connected_line(self) -> None:
        assert CouplingMap.line(4).is_connected()

    def test_disconnected_custom(self) -> None:
        cm = CouplingMap(4, [(0, 1), (2, 3)])
        assert not cm.is_connected()
        assert cm.distance(0, 3) is None
        assert cm.shortest_path(0, 3) is None

    def test_single_qubit_is_connected(self) -> None:
        assert CouplingMap(1, []).is_connected()

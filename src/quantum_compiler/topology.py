"""Hardware coupling maps: which physical qubit pairs can host a 2-qubit gate.

A :class:`CouplingMap` is an undirected graph on ``num_qubits`` physical qubits.
The router (:mod:`quantum_compiler.route`) uses it to decide when a 2-qubit gate's
operands are physically adjacent and, when they are not, the shortest chain of
SWAPs that brings them together. Distances and paths come from breadth-first
search, so this is an abstract connectivity model only — no gate timings, error
rates, or calibration (see the README Limitations).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class CouplingMap:
    """An undirected connectivity graph on ``num_qubits`` physical qubits."""

    num_qubits: int
    edges: list[tuple[int, int]]
    _adjacency: dict[int, set[int]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.num_qubits < 1:
            raise ValueError("a coupling map needs at least one qubit")
        self._adjacency = {q: set() for q in range(self.num_qubits)}
        for a, b in self.edges:
            if not (0 <= a < self.num_qubits and 0 <= b < self.num_qubits):
                raise ValueError(f"edge ({a}, {b}) out of range for {self.num_qubits} qubits")
            if a == b:
                raise ValueError(f"self-loop ({a}, {b}) is not a valid coupling")
            self._adjacency[a].add(b)
            self._adjacency[b].add(a)

    # -- constructors -----------------------------------------------------
    @classmethod
    def line(cls, n: int) -> CouplingMap:
        """A linear chain ``0-1-2-...-(n-1)``."""
        return cls(n, [(i, i + 1) for i in range(n - 1)])

    @classmethod
    def ring(cls, n: int) -> CouplingMap:
        """A ring: a line whose ends are also joined (needs ``n >= 3``)."""
        if n < 3:
            raise ValueError("a ring needs at least 3 qubits")
        return cls(n, [(i, (i + 1) % n) for i in range(n)])

    @classmethod
    def grid(cls, rows: int, cols: int) -> CouplingMap:
        """A ``rows x cols`` grid; qubit ``r*cols + c`` joins its 4-neighbours."""
        if rows < 1 or cols < 1:
            raise ValueError("grid dimensions must be positive")
        edges: list[tuple[int, int]] = []
        for r in range(rows):
            for c in range(cols):
                q = r * cols + c
                if c + 1 < cols:
                    edges.append((q, q + 1))
                if r + 1 < rows:
                    edges.append((q, q + cols))
        return cls(rows * cols, edges)

    @classmethod
    def full(cls, n: int) -> CouplingMap:
        """All-to-all connectivity on ``n`` qubits."""
        return cls(n, [(a, b) for a in range(n) for b in range(a + 1, n)])

    # -- queries ----------------------------------------------------------
    def neighbours(self, q: int) -> list[int]:
        """Physical qubits directly coupled to *q*, sorted ascending."""
        return sorted(self._adjacency[q])

    def are_adjacent(self, a: int, b: int) -> bool:
        """True when *a* and *b* share an edge."""
        return b in self._adjacency[a]

    def distance(self, a: int, b: int) -> int | None:
        """BFS hop count between *a* and *b*, or ``None`` if disconnected."""
        path = self.shortest_path(a, b)
        return None if path is None else len(path) - 1

    def shortest_path(self, a: int, b: int) -> list[int] | None:
        """A shortest physical path ``[a, ..., b]``, or ``None`` if none exists."""
        if a == b:
            return [a]
        previous: dict[int, int] = {a: a}
        queue: deque[int] = deque([a])
        while queue:
            node = queue.popleft()
            for neighbour in self.neighbours(node):
                if neighbour in previous:
                    continue
                previous[neighbour] = node
                if neighbour == b:
                    return _reconstruct(previous, a, b)
                queue.append(neighbour)
        return None

    def is_connected(self) -> bool:
        """True when every physical qubit is reachable from qubit 0."""
        seen = {0}
        queue: deque[int] = deque([0])
        while queue:
            node = queue.popleft()
            for neighbour in self.neighbours(node):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return len(seen) == self.num_qubits


def _reconstruct(previous: dict[int, int], a: int, b: int) -> list[int]:
    """Walk the BFS predecessor chain from *b* back to *a*."""
    path = [b]
    while path[-1] != a:
        path.append(previous[path[-1]])
    path.reverse()
    return path

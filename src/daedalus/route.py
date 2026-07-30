"""SWAP-insertion routing: map a logical circuit onto a coupling map.

Every 2-qubit gate must act on physically adjacent qubits. Two strategies are
offered, both *verified* by :func:`daedalus.verify.check_routing_equivalence`,
which proves the routed circuit reproduces the original once inputs are placed
through the initial layout and outputs read back through the final layout.

``greedy``
    Starts from the trivial layout (logical qubit ``l`` on physical qubit
    ``l``) and walks the circuit in order; when a 2-qubit gate's operands are
    not adjacent it inserts SWAPs along a shortest coupling-map path. No
    lookahead, no layout selection.

``sabre``
    A SABRE-lite router after Li, Ding & Xie 2019 ("Tackling the Qubit Mapping
    Problem for NISQ-Era Quantum Devices"). Implemented subset: the front layer
    of the dependency DAG, candidate SWAPs scored by the summed BFS distance of
    the front layer plus a weighted lookahead window of upcoming 2-qubit gates,
    and reverse-traversal initial-layout selection (one forward and one
    backward routing pass over the circuit choose where each logical qubit
    starts). Not implemented from the paper: the decay factor and multiple
    reverse-traversal rounds. Everything is deterministic - ties break on the
    smallest candidate edge - and a greedy shortest-path fallback fires if the
    heuristic stalls, so routing always terminates.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from daedalus.ir import Circuit, Gate
from daedalus.topology import CouplingMap

_TWO_QUBIT = frozenset({"cx", "cz", "swap"})

#: How many upcoming 2-qubit gates the sabre heuristic looks ahead at.
_LOOKAHEAD_WINDOW = 20
#: Weight of the lookahead window relative to the front layer in SWAP scores.
_LOOKAHEAD_WEIGHT = 0.5
#: Consecutive non-executing SWAPs before the greedy fallback force-routes the
#: lowest-index blocked gate (guarantees termination without decay factors).
_STALL_LIMIT = 8


@dataclass(frozen=True)
class RoutingResult:
    """A routed circuit plus the qubit placements it starts and ends with."""

    circuit: Circuit
    #: ``initial_layout[logical]`` = the physical qubit hosting logical at the
    #: start (always ``[0, 1, ...]`` for the greedy strategy).
    initial_layout: list[int]
    #: ``final_layout[logical]`` = the physical qubit carrying logical at the end.
    final_layout: list[int]
    swaps_added: int


def route(
    circuit: Circuit, coupling: CouplingMap, strategy: str = "greedy"
) -> RoutingResult:
    """Route *circuit* onto *coupling*, inserting SWAPs to satisfy adjacency."""
    n, m = circuit.num_qubits, coupling.num_qubits
    if n > m:
        raise ValueError(f"circuit needs {n} qubits but the coupling map has {m}")
    if strategy == "greedy":
        return _route_greedy(circuit, coupling)
    if strategy == "sabre":
        return _route_sabre(circuit, coupling)
    raise ValueError(f"unknown routing strategy '{strategy}'; use greedy or sabre")


def _route_greedy(circuit: Circuit, coupling: CouplingMap) -> RoutingResult:
    """The original in-order router: trivial initial layout, no lookahead."""
    n, m = circuit.num_qubits, coupling.num_qubits
    phys = list(range(n))  # phys[logical] -> physical location
    loc: list[int | None] = [p if p < n else None for p in range(m)]  # physical -> logical
    routed: list[Gate] = []
    swaps_added = 0

    for gate in circuit.gates:
        if gate.name in _TWO_QUBIT:
            a, b = gate.qubits
            if not coupling.are_adjacent(phys[a], phys[b]):
                path = coupling.shortest_path(phys[a], phys[b])
                if path is None:
                    raise ValueError(
                        f"cannot route gate on q{a}, q{b}: physical qubits "
                        f"{phys[a]} and {phys[b]} are disconnected"
                    )
                # Carry logical a's token along the path until it is adjacent to
                # b: swap the first path edges, stopping one short of b's node.
                for i in range(len(path) - 2):
                    u, v = path[i], path[i + 1]
                    routed.append(Gate("swap", (u, v)))
                    _swap_tokens(phys, loc, u, v)
                    swaps_added += 1
            routed.append(Gate(gate.name, (phys[a], phys[b])))
        elif gate.name == "measure":
            routed.append(Gate("measure", (phys[gate.qubits[0]],), bit=gate.bit))
        elif gate.name == "barrier":
            # A fence can span any number of wires; relabel every operand so the
            # full barrier survives routing (the single-qubit branch would drop
            # all but the first, and the equivalence check cannot see it because
            # a barrier simulates as identity).
            routed.append(Gate("barrier", tuple(phys[q] for q in gate.qubits)))
        else:
            routed.append(Gate(gate.name, (phys[gate.qubits[0]],), angle=gate.angle))

    return RoutingResult(
        Circuit(m, circuit.num_bits, routed), list(range(n)), list(phys), swaps_added
    )


def _route_sabre(circuit: Circuit, coupling: CouplingMap) -> RoutingResult:
    """SABRE-lite: reverse-traversal layout selection, then one scored pass."""
    m = coupling.num_qubits
    dist = _all_distances(coupling)
    # Reverse traversal: route forward from the trivial layout, then route the
    # reversed circuit from where that ended; the mapping it finishes with
    # becomes the initial layout (gates far into the circuit have pulled the
    # qubits they need together before the real pass starts).
    layout = list(range(circuit.num_qubits))
    _, layout, _ = _sabre_pass(circuit.gates, coupling, dist, layout)
    _, layout, _ = _sabre_pass(list(reversed(circuit.gates)), coupling, dist, layout)
    routed, final, swaps_added = _sabre_pass(circuit.gates, coupling, dist, layout)
    return RoutingResult(Circuit(m, circuit.num_bits, routed), layout, final, swaps_added)


def _sabre_pass(
    gates: Sequence[Gate],
    coupling: CouplingMap,
    dist: list[list[float]],
    initial: list[int],
) -> tuple[list[Gate], list[int], int]:
    """One front-layer routing pass; returns (routed gates, final phys, swaps).

    Walks the dependency DAG: every dependency-free gate that is executable
    (1-qubit, measure, barrier, or a 2-qubit gate on adjacent physical qubits)
    is emitted in ascending program order; when nothing is executable, the
    candidate SWAP with the best :func:`_swap_score` is applied. Deterministic
    throughout: gate emission and tie-breaks follow fixed orderings.
    """
    m = coupling.num_qubits
    phys = list(initial)  # phys[logical] -> physical location
    loc: list[int | None] = [None] * m  # physical -> logical
    for logical, p in enumerate(phys):
        loc[p] = logical

    indegree, successors = _dependency_dag(gates)
    front = {i for i in range(len(gates)) if indegree[i] == 0}
    routed: list[Gate] = []
    swaps_added = 0
    stall = 0

    while front:
        executed = False
        for i in sorted(front):
            gate = gates[i]
            if gate.name in _TWO_QUBIT:
                a, b = gate.qubits
                if not coupling.are_adjacent(phys[a], phys[b]):
                    continue
                routed.append(Gate(gate.name, (phys[a], phys[b])))
            elif gate.name == "measure":
                routed.append(Gate("measure", (phys[gate.qubits[0]],), bit=gate.bit))
            elif gate.name == "barrier":
                routed.append(Gate("barrier", tuple(phys[q] for q in gate.qubits)))
            else:
                routed.append(Gate(gate.name, (phys[gate.qubits[0]],), angle=gate.angle))
            front.discard(i)
            for j in successors[i]:
                indegree[j] -= 1
                if indegree[j] == 0:
                    front.add(j)
            executed = True
        if executed:
            stall = 0
            continue

        # Everything left in the front is a blocked 2-qubit gate (all other
        # gate kinds are always executable).
        blocked = sorted(front)
        for i in blocked:
            a, b = gates[i].qubits
            if math.isinf(dist[phys[a]][phys[b]]):
                raise ValueError(
                    f"cannot route gate on q{a}, q{b}: physical qubits "
                    f"{phys[a]} and {phys[b]} are disconnected"
                )
        if stall >= _STALL_LIMIT:
            # Heuristic stalled: force-route the first blocked gate along a
            # shortest path, exactly like the greedy strategy would.
            a, b = gates[blocked[0]].qubits
            path = coupling.shortest_path(phys[a], phys[b])
            assert path is not None  # disconnected pairs raised above
            for k in range(len(path) - 2):
                u, v = path[k], path[k + 1]
                routed.append(Gate("swap", (u, v)))
                _swap_tokens(phys, loc, u, v)
                swaps_added += 1
            stall = 0
            continue

        lookahead = _lookahead_gates(gates, successors, front)
        best_edge: tuple[int, int] | None = None
        best_score = math.inf
        for edge in _candidate_swaps(coupling, phys, gates, blocked):
            score = _swap_score(edge, phys, gates, blocked, lookahead, dist)
            if score < best_score:
                best_edge, best_score = edge, score
        assert best_edge is not None  # blocked gates always yield candidates
        routed.append(Gate("swap", best_edge))
        _swap_tokens(phys, loc, *best_edge)
        swaps_added += 1
        stall += 1

    return routed, phys, swaps_added


def _dependency_dag(gates: Sequence[Gate]) -> tuple[list[int], list[list[int]]]:
    """Per-wire dependency DAG: (in-degree, successor indices) per gate.

    Gate *j* depends on gate *i* when *i* is the previous gate touching one of
    *j*'s qubits (barriers participate on every wire they fence, so no gate is
    reordered across one). Duplicate edges (two shared wires) are kept so the
    in-degree bookkeeping stays symmetric.
    """
    indegree = [0] * len(gates)
    successors: list[list[int]] = [[] for _ in gates]
    last_on_wire: dict[int, int] = {}
    for i, gate in enumerate(gates):
        for q in gate.qubits:
            previous = last_on_wire.get(q)
            if previous is not None:
                successors[previous].append(i)
                indegree[i] += 1
            last_on_wire[q] = i
    return indegree, successors


def _lookahead_gates(
    gates: Sequence[Gate], successors: list[list[int]], front: set[int]
) -> list[int]:
    """Up to ``_LOOKAHEAD_WINDOW`` upcoming 2-qubit gates, nearest-first (BFS)."""
    collected: list[int] = []
    seen = set(front)
    queue: deque[int] = deque(sorted(front))
    while queue and len(collected) < _LOOKAHEAD_WINDOW:
        for j in successors[queue.popleft()]:
            if j in seen:
                continue
            seen.add(j)
            if gates[j].name in _TWO_QUBIT:
                collected.append(j)
                if len(collected) == _LOOKAHEAD_WINDOW:
                    break
            queue.append(j)
    return collected


def _candidate_swaps(
    coupling: CouplingMap,
    phys: list[int],
    gates: Sequence[Gate],
    blocked: list[int],
) -> list[tuple[int, int]]:
    """Coupling edges touching any blocked front gate's qubits, sorted."""
    candidates: set[tuple[int, int]] = set()
    for i in blocked:
        for q in gates[i].qubits:
            p = phys[q]
            for neighbour in coupling.neighbours(p):
                candidates.add((min(p, neighbour), max(p, neighbour)))
    return sorted(candidates)


def _swap_score(
    edge: tuple[int, int],
    phys: list[int],
    gates: Sequence[Gate],
    blocked: list[int],
    lookahead: list[int],
    dist: list[list[float]],
) -> float:
    """SABRE heuristic: mean front-layer distance plus weighted lookahead mean.

    Distances are evaluated as if *edge* had been swapped; lower is better.
    Unreachable lookahead pairs are ignored: no SWAP can help them, their
    unreachability never changes within a pass (tokens cannot leave their
    component), and including their infinite distance would make every
    candidate score infinite. They raise cleanly once they reach the front.
    """
    u, v = edge

    def moved(p: int) -> int:
        return v if p == u else u if p == v else p

    def gate_distance(i: int) -> float:
        a, b = gates[i].qubits
        return dist[moved(phys[a])][moved(phys[b])]

    score = sum(gate_distance(i) for i in blocked) / len(blocked)
    ahead = [d for d in (gate_distance(i) for i in lookahead) if not math.isinf(d)]
    if ahead:
        score += _LOOKAHEAD_WEIGHT * sum(ahead) / len(ahead)
    return score


def _all_distances(coupling: CouplingMap) -> list[list[float]]:
    """All-pairs BFS hop counts; ``inf`` marks disconnected pairs."""
    m = coupling.num_qubits
    dist = [[math.inf] * m for _ in range(m)]
    for source in range(m):
        dist[source][source] = 0.0
        queue: deque[int] = deque([source])
        while queue:
            node = queue.popleft()
            for neighbour in coupling.neighbours(node):
                if math.isinf(dist[source][neighbour]):
                    dist[source][neighbour] = dist[source][node] + 1.0
                    queue.append(neighbour)
    return dist


def _swap_tokens(phys: list[int], loc: list[int | None], u: int, v: int) -> None:
    """Exchange whatever logical tokens sit on physical qubits *u* and *v*."""
    lu, lv = loc[u], loc[v]
    loc[u], loc[v] = lv, lu
    if lu is not None:
        phys[lu] = v
    if lv is not None:
        phys[lv] = u

"""SWAP-insertion router: map a logical circuit onto a coupling map.

Every 2-qubit gate must act on physically adjacent qubits. Starting from the
trivial layout (logical qubit ``l`` on physical qubit ``l``), the router walks
the circuit in order keeping a live logical->physical mapping. When a 2-qubit
gate's operands are not adjacent it inserts SWAPs along a shortest coupling-map
path to bring them together, updating the mapping as it goes; single-qubit gates
and measures are emitted on the operand's current physical location.

This is a deliberately simple greedy router (no lookahead, trivial initial
layout) — but it is *verified*: :func:`daedalus.verify.check_routing_equivalence`
proves the routed circuit reproduces the original up to the final qubit
permutation returned here. Smarter initial placement and lookahead are noted as
future work in the README.
"""

from __future__ import annotations

from dataclasses import dataclass

from daedalus.ir import Circuit, Gate
from daedalus.topology import CouplingMap

_TWO_QUBIT = frozenset({"cx", "cz", "swap"})


@dataclass(frozen=True)
class RoutingResult:
    """A routed circuit plus the qubit permutation it induces."""

    circuit: Circuit
    #: ``final_layout[logical]`` = the physical qubit carrying logical at the end.
    final_layout: list[int]
    swaps_added: int


def route(circuit: Circuit, coupling: CouplingMap) -> RoutingResult:
    """Route *circuit* onto *coupling*, inserting SWAPs to satisfy adjacency."""
    n, m = circuit.num_qubits, coupling.num_qubits
    if n > m:
        raise ValueError(f"circuit needs {n} qubits but the coupling map has {m}")

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

    return RoutingResult(Circuit(m, circuit.num_bits, routed), list(phys), swaps_added)


def _swap_tokens(phys: list[int], loc: list[int | None], u: int, v: int) -> None:
    """Exchange whatever logical tokens sit on physical qubits *u* and *v*."""
    lu, lv = loc[u], loc[v]
    loc[u], loc[v] = lv, lu
    if lu is not None:
        phys[lu] = v
    if lv is not None:
        phys[lv] = u

"""Pass manager: run passes to fixpoint with before/after statistics.

Termination: no pass ever adds a gate, so the gate count is non-increasing. The
only pass that can rewrite without shrinking is ``canonicalize-rotations``,
which renames a special-angle rotation to a named Clifford+T gate. Order the
lexicographic measure ``(len(gates), number of special-angle rotations)``: any
gate-count reduction lowers the first component, and any equal-length change
(canonicalize renaming a rotation) strictly lowers the second while never
raising it. Creation of a fresh special-angle rotation (merge or peephole)
always coincides with a strict length decrease, so the measure is bounded below
and strictly decreases on every change: the loop reaches a fixpoint.
``max_iterations`` is a defensive bound on top of that argument.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from daedalus.ir import Circuit
from daedalus.passes.cancel_inverses import CancelInverses
from daedalus.passes.canonicalize_rotations import CanonicalizeRotations
from daedalus.passes.commute_cancel import CommuteCancel
from daedalus.passes.control_flip import ControlFlip
from daedalus.passes.dead_code import DeadCodeElimination
from daedalus.passes.merge_rotations import MergeRotations
from daedalus.passes.peephole import Peephole

__all__ = [
    "CancelInverses",
    "CanonicalizeRotations",
    "CommuteCancel",
    "ControlFlip",
    "DeadCodeElimination",
    "MergeRotations",
    "Pass",
    "PassManager",
    "PassStats",
    "Peephole",
    "default_passes",
]


class Pass(Protocol):
    """A circuit-to-circuit rewrite with a stable name."""

    name: str

    def run(self, circuit: Circuit) -> Circuit:
        """Return the rewritten circuit (may be the input if unchanged)."""
        ...


@dataclass(frozen=True)
class PassStats:
    """Gate counts around one pass invocation within one fixpoint iteration."""

    iteration: int
    name: str
    gates_before: int
    gates_after: int


class PassManager:
    """Runs a pass list repeatedly until no pass changes the circuit."""

    def __init__(self, passes: Sequence[Pass], max_iterations: int = 1000) -> None:
        self.passes = list(passes)
        self.max_iterations = max_iterations

    def run(self, circuit: Circuit) -> tuple[Circuit, list[PassStats]]:
        """Optimize *circuit* to fixpoint; return (circuit, per-run stats)."""
        stats: list[PassStats] = []
        for iteration in range(1, self.max_iterations + 1):
            changed = False
            for pass_ in self.passes:
                before = len(circuit.gates)
                result = pass_.run(circuit)
                stats.append(PassStats(iteration, pass_.name, before, len(result.gates)))
                if result.gates != circuit.gates:
                    changed = True
                circuit = result
            if not changed:
                return circuit, stats
        raise RuntimeError("pass manager failed to reach a fixpoint")


def default_passes(dce: bool = False) -> list[Pass]:
    """The standard pipeline; dead-code elimination only when *dce* is True.

    ``canonicalize-rotations`` runs last so the peephole pass sees raw
    ``rz``/``rx``/``ry`` before any are frozen into named Clifford+T gates.
    """
    passes: list[Pass] = [
        CancelInverses(),
        MergeRotations(),
        Peephole(),
        ControlFlip(),
        CommuteCancel(),
        CanonicalizeRotations(),
    ]
    if dce:
        passes.append(DeadCodeElimination())
    return passes

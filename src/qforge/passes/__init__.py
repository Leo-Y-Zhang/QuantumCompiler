"""Pass manager: run passes to fixpoint with before/after statistics.

Termination: every pass either leaves the gate list unchanged or strictly
shrinks it (cancellation, merging, and 3->1 rewrites never add gates), so the
fixpoint loop terminates after at most ``len(gates) + 1`` iterations;
``max_iterations`` is a defensive bound on top of that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from qforge.ir import Circuit
from qforge.passes.cancel_inverses import CancelInverses
from qforge.passes.commute_cancel import CommuteCancel
from qforge.passes.dead_code import DeadCodeElimination
from qforge.passes.merge_rotations import MergeRotations
from qforge.passes.peephole import Peephole

__all__ = [
    "Pass",
    "PassManager",
    "PassStats",
    "default_passes",
    "CancelInverses",
    "CommuteCancel",
    "DeadCodeElimination",
    "MergeRotations",
    "Peephole",
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
    """The standard pipeline; dead-code elimination only when *dce* is True."""
    passes: list[Pass] = [CancelInverses(), MergeRotations(), Peephole(), CommuteCancel()]
    if dce:
        passes.append(DeadCodeElimination())
    return passes

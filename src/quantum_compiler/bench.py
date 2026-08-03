"""Routing benchmark: swaps added and depth delta, sabre vs greedy.

Runs both routing strategies over every committed example circuit on the same
five topologies the test suite proves equivalence on, and prints a Markdown
table (the one in the README is this module's verbatim output, regenerable with
``python -m quantum_compiler.bench``). Honest scope: these are tiny circuits (2-4
qubits, at most ~20 gates), so the numbers say nothing about asymptotic
routing quality - they only show how the two shipped strategies compare on the
repository's own examples. Runs from a repository checkout (it reads
``examples/``), not from an installed package alone.
"""

from __future__ import annotations

from pathlib import Path

from quantum_compiler.draw_ascii import column_layout
from quantum_compiler.ir import Circuit
from quantum_compiler.parser import parse
from quantum_compiler.route import route
from quantum_compiler.topology import CouplingMap

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

EXAMPLE_NAMES = ["bell", "ghz", "rotations", "qft3", "clifford_t", "routed_line"]

#: The same five topologies the routing tests prove equivalence on.
TOPOLOGIES: list[tuple[str, CouplingMap]] = [
    ("line:4", CouplingMap.line(4)),
    ("ring:4", CouplingMap.ring(4)),
    ("grid:2x2", CouplingMap.grid(2, 2)),
    ("grid:2x3", CouplingMap.grid(2, 3)),
    ("full:4", CouplingMap.full(4)),
]

_HEADER = (
    "| circuit | topology | swaps greedy | swaps sabre | depth greedy | depth sabre |"
)
_RULE = "|---|---|---:|---:|---:|---:|"


def benchmark_table(examples_dir: Path = EXAMPLES_DIR) -> str:
    """Render the sabre-vs-greedy Markdown table for the example circuits.

    ``swaps`` columns count inserted SWAP gates; ``depth`` columns show the
    routed depth minus the original circuit depth (``+0`` = no change).
    """
    lines = [_HEADER, _RULE]
    for name in EXAMPLE_NAMES:
        original = parse((examples_dir / f"{name}.qf").read_text(encoding="ascii"))
        depth = _depth(original)
        for label, coupling in TOPOLOGIES:
            greedy = route(original, coupling)
            sabre = route(original, coupling, strategy="sabre")
            lines.append(
                _format_row(
                    name,
                    label,
                    greedy.swaps_added,
                    sabre.swaps_added,
                    _depth(greedy.circuit) - depth,
                    _depth(sabre.circuit) - depth,
                )
            )
    return "\n".join(lines) + "\n"


def _format_row(
    name: str,
    topology: str,
    swaps_greedy: int,
    swaps_sabre: int,
    depth_delta_greedy: int,
    depth_delta_sabre: int,
) -> str:
    return (
        f"| {name} | {topology} | {swaps_greedy} | {swaps_sabre} "
        f"| {depth_delta_greedy:+d} | {depth_delta_sabre:+d} |"
    )


def _depth(circuit: Circuit) -> int:
    """Circuit depth = number of moments in the greedy schedule."""
    return max(column_layout(circuit), default=-1) + 1


def main() -> int:
    """Print the benchmark table; the README table is this output verbatim."""
    print(benchmark_table(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

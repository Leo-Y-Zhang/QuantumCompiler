"""Every shipped example parses, optimizes soundly, and does what it claims.

The headline check proves the elementary-gate ``qft3.qf`` circuit really is the
Quantum Fourier Transform by comparing its unitary to the analytic DFT matrix.
"""

import cmath
import math
from pathlib import Path

import pytest

from daedalus.parser import parse
from daedalus.passes import PassManager, default_passes
from daedalus.route import route
from daedalus.topology import CouplingMap
from daedalus.unitary import circuit_unitary, compare_unitaries
from daedalus.verify import check_equivalence, check_routing_equivalence

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
EXAMPLE_NAMES = ["bell", "ghz", "rotations", "qft3", "clifford_t", "routed_line"]

_TWO_QUBIT = {"cx", "cz", "swap"}


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_example_optimizes_equivalently(name: str) -> None:
    original = parse((EXAMPLES / f"{name}.qf").read_text(encoding="ascii"))
    optimized, _ = PassManager(default_passes()).run(original)
    assert check_equivalence(original, optimized).equivalent


def test_qft3_is_the_dft_matrix() -> None:
    circuit = parse((EXAMPLES / "qft3.qf").read_text(encoding="ascii"))
    unitary = circuit_unitary(circuit)
    n = 8
    dft = [
        [cmath.exp(2j * math.pi * j * k / n) / math.sqrt(n) for k in range(n)]
        for j in range(n)
    ]
    result = compare_unitaries(dft, unitary)
    assert result.equivalent
    assert result.process_fidelity == pytest.approx(1.0, abs=1e-9)


def test_qft3_optimizes_to_fewer_gates_but_stays_the_dft() -> None:
    original = parse((EXAMPLES / "qft3.qf").read_text(encoding="ascii"))
    optimized, _ = PassManager(default_passes()).run(original)
    assert len(optimized.gates) <= len(original.gates)
    assert check_equivalence(original, optimized).equivalent


def test_clifford_t_lowers_and_cancels() -> None:
    original = parse((EXAMPLES / "clifford_t.qf").read_text(encoding="ascii"))
    optimized, _ = PassManager(default_passes()).run(original)
    names = [g.name for g in optimized.gates]
    assert "t" in names  # rz(pi/4) lowered to t
    assert "s" in names  # rz(pi/2) lowered to s
    assert names.count("t") + names.count("tdg") == 1  # the trailing t/tdg cancelled


def test_routed_line_routes_and_verifies() -> None:
    original = parse((EXAMPLES / "routed_line.qf").read_text(encoding="ascii"))
    coupling = CouplingMap.line(4)
    result = route(original, coupling)
    assert result.swaps_added > 0
    for gate in result.circuit.gates:
        if gate.name in _TWO_QUBIT:
            assert coupling.are_adjacent(*gate.qubits)
    assert check_routing_equivalence(original, result.circuit, result.final_layout).equivalent


@pytest.mark.parametrize(
    "coupling",
    [
        pytest.param(CouplingMap.line(4), id="line4"),
        pytest.param(CouplingMap.ring(4), id="ring4"),
        pytest.param(CouplingMap.grid(2, 2), id="grid2x2"),
        pytest.param(CouplingMap.grid(2, 3), id="grid2x3"),
        pytest.param(CouplingMap.full(4), id="full4"),
    ],
)
@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_example_sabre_routes_equivalently(name: str, coupling: CouplingMap) -> None:
    """Every sabre-routed example is proven correct on all five topologies."""
    original = parse((EXAMPLES / f"{name}.qf").read_text(encoding="ascii"))
    result = route(original, coupling, strategy="sabre")
    for gate in result.circuit.gates:
        if gate.name in _TWO_QUBIT:
            assert coupling.are_adjacent(*gate.qubits)
    check = check_routing_equivalence(
        original,
        result.circuit,
        result.final_layout,
        initial_layout=result.initial_layout,
    )
    assert check.equivalent, f"sabre routing changed semantics on {name}"

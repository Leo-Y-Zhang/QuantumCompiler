"""quantum_compiler: a toy educational quantum-circuit DSL compiler.

Demonstrates real compiler architecture (lexer, parser, IR, pass manager,
semantic verification) on a deliberately small quantum-circuit language.
Python standard library only. Not a production quantum compiler.
"""

from quantum_compiler.analyze import CircuitMetrics, analyze
from quantum_compiler.dot import to_dot
from quantum_compiler.equiv import ShrinkResult, Witness, find_witness, shrink_counterexample
from quantum_compiler.ir import Circuit, Gate
from quantum_compiler.parser import parse
from quantum_compiler.qasm import emit_qasm, parse_qasm
from quantum_compiler.route import RoutingResult, route
from quantum_compiler.sim import simulate
from quantum_compiler.topology import CouplingMap
from quantum_compiler.unitary import circuit_unitary, prove_circuit_equivalence
from quantum_compiler.verify import (
    EquivalenceResult,
    ProofResult,
    check_equivalence,
    check_routing_equivalence,
    prove_equivalence,
)

__version__ = "1.2.0"

__all__ = [
    "Circuit",
    "CircuitMetrics",
    "CouplingMap",
    "EquivalenceResult",
    "Gate",
    "ProofResult",
    "RoutingResult",
    "ShrinkResult",
    "Witness",
    "__version__",
    "analyze",
    "check_equivalence",
    "check_routing_equivalence",
    "circuit_unitary",
    "emit_qasm",
    "find_witness",
    "parse",
    "parse_qasm",
    "prove_circuit_equivalence",
    "prove_equivalence",
    "route",
    "shrink_counterexample",
    "simulate",
    "to_dot",
]

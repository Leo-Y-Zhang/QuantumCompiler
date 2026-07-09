"""daedalus: a toy educational quantum-circuit DSL compiler.

Demonstrates real compiler architecture (lexer, parser, IR, pass manager,
semantic verification) on a deliberately small quantum-circuit language.
Python standard library only. Not a production quantum compiler.
"""

from daedalus.ir import Circuit, Gate
from daedalus.parser import parse
from daedalus.qasm import emit_qasm, parse_qasm
from daedalus.sim import simulate
from daedalus.unitary import circuit_unitary, prove_circuit_equivalence
from daedalus.verify import (
    EquivalenceResult,
    ProofResult,
    check_equivalence,
    prove_equivalence,
)

__version__ = "0.2.0"

__all__ = [
    "Circuit",
    "EquivalenceResult",
    "Gate",
    "ProofResult",
    "__version__",
    "check_equivalence",
    "circuit_unitary",
    "emit_qasm",
    "parse",
    "parse_qasm",
    "prove_circuit_equivalence",
    "prove_equivalence",
    "simulate",
]

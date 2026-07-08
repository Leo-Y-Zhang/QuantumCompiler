"""daedalus: a toy educational quantum-circuit DSL compiler.

Demonstrates real compiler architecture (lexer, parser, IR, pass manager,
semantic verification) on a deliberately small quantum-circuit language.
Python standard library only. Not a production quantum compiler.
"""

from daedalus.ir import Circuit, Gate
from daedalus.parser import parse
from daedalus.qasm import emit_qasm, parse_qasm
from daedalus.sim import simulate
from daedalus.verify import EquivalenceResult, check_equivalence

__version__ = "0.2.0"

__all__ = [
    "Circuit",
    "EquivalenceResult",
    "Gate",
    "__version__",
    "check_equivalence",
    "emit_qasm",
    "parse",
    "parse_qasm",
    "simulate",
]

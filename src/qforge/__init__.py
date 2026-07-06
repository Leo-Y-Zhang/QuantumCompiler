"""qforge: a toy educational quantum-circuit DSL compiler.

Demonstrates real compiler architecture (lexer, parser, IR, pass manager,
semantic verification) on a deliberately small quantum-circuit language.
Python standard library only. Not a production quantum compiler.
"""

from qforge.ir import Circuit, Gate
from qforge.parser import parse
from qforge.sim import simulate
from qforge.verify import EquivalenceResult, check_equivalence

__version__ = "0.1.0"

__all__ = [
    "Circuit",
    "EquivalenceResult",
    "Gate",
    "__version__",
    "check_equivalence",
    "parse",
    "simulate",
]

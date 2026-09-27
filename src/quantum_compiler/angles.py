"""Safe angle-expression evaluation with pi arithmetic. No ``eval`` anywhere.

Grammar (recursive descent over lexer tokens)::

    expr  := term  (('+' | '-') term)*
    term  := unary (('*' | '/') unary)*
    unary := ('+' | '-') unary | atom
    atom  := NUMBER | 'pi' | '(' expr ')'

Only numbers and the constant ``pi`` exist; anything else is a parse error,
so expressions cannot reach Python execution by construction.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction

from quantum_compiler.errors import ParseError
from quantum_compiler.lexer import Token, describe, tokenize

_PI_TOLERANCE = 1e-12
_MAX_DENOMINATOR = 8


def evaluate(text: str) -> float:
    """Evaluate a standalone angle expression such as ``"3*pi/4"``."""
    tokens = [t for t in tokenize(text) if t.kind != "NEWLINE"]
    value, pos = parse_expression(tokens, 0)
    if tokens[pos].kind != "EOF":
        tok = tokens[pos]
        raise ParseError(
            f"unexpected {describe(tok)} after angle expression", tok.line, tok.column
        )
    return value


def parse_expression(tokens: Sequence[Token], pos: int) -> tuple[float, int]:
    """Parse an expression starting at ``tokens[pos]``; return (value, next_pos).

    A value that overflows to ``inf`` (or becomes ``nan``) is rejected here, at
    the expression's first token: no gate has a meaningful non-finite angle,
    and letting one through would surface later as an uncaught
    ``math.remainder`` domain error inside the optimizer.
    """
    start = tokens[pos]
    value, pos = _term(tokens, pos)
    while tokens[pos].kind in ("PLUS", "MINUS"):
        op = tokens[pos]
        rhs, pos = _term(tokens, pos + 1)
        value = value + rhs if op.kind == "PLUS" else value - rhs
    if not math.isfinite(value):
        raise ParseError(
            "angle expression is not a finite number", start.line, start.column
        )
    return value, pos


def _term(tokens: Sequence[Token], pos: int) -> tuple[float, int]:
    value, pos = _unary(tokens, pos)
    while tokens[pos].kind in ("STAR", "SLASH"):
        op = tokens[pos]
        rhs, pos = _unary(tokens, pos + 1)
        if op.kind == "STAR":
            value *= rhs
        else:
            if rhs == 0:
                raise ParseError("division by zero in angle expression", op.line, op.column)
            value /= rhs
    return value, pos


def _unary(tokens: Sequence[Token], pos: int) -> tuple[float, int]:
    kind = tokens[pos].kind
    if kind == "MINUS":
        value, pos = _unary(tokens, pos + 1)
        return -value, pos
    if kind == "PLUS":
        return _unary(tokens, pos + 1)
    return _atom(tokens, pos)


def _atom(tokens: Sequence[Token], pos: int) -> tuple[float, int]:
    tok = tokens[pos]
    if tok.kind == "NUMBER":
        assert tok.value is not None
        return tok.value, pos + 1
    if tok.kind == "IDENT":
        if tok.text == "pi":
            return math.pi, pos + 1
        raise ParseError(
            f"unknown identifier '{tok.text}' in angle expression", tok.line, tok.column
        )
    if tok.kind == "LPAREN":
        value, pos = parse_expression(tokens, pos + 1)
        closing = tokens[pos]
        if closing.kind != "RPAREN":
            raise ParseError(
                f"expected ')' in angle expression, found {describe(closing)}",
                closing.line,
                closing.column,
            )
        return value, pos + 1
    raise ParseError(
        f"expected number, 'pi', or '(' in angle expression, found {describe(tok)}",
        tok.line,
        tok.column,
    )


def format_angle(theta: float) -> str:
    """Format *theta* as DSL source: ``pi/4`` style when close, else a decimal.

    The decimal fallback is ``repr`` written positionally. ``repr`` switches to
    exponent notation outside roughly ``1e-4 .. 1e16`` and the DSL grammar has
    no exponent literal, so emitting it verbatim would produce source this
    package's own parser rejects. Expanding the same digits through
    :class:`~decimal.Decimal` keeps the value bit-exact (``repr`` is already
    the shortest round-tripping decimal) and keeps the text parseable.
    """
    if theta == 0:
        return "0"
    frac = Fraction(theta / math.pi).limit_denominator(_MAX_DENOMINATOR)
    if frac != 0 and abs(float(frac) * math.pi - theta) < _PI_TOLERANCE:
        sign = "-" if frac < 0 else ""
        num, den = abs(frac.numerator), frac.denominator
        pi_part = "pi" if num == 1 else f"{num}*pi"
        return f"{sign}{pi_part}" if den == 1 else f"{sign}{pi_part}/{den}"
    text = repr(theta)
    if "e" in text or "E" in text:
        return format(Decimal(text), "f")
    return text

"""Hand-written lexer for the QuantumCompiler DSL.

Produces a flat token list with 1-based line/column positions so the parser
can report precise diagnostics. ``#`` starts a comment that runs to the end
of the line; CRLF line endings are accepted.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantum_compiler.errors import LexError

_SYMBOLS = {
    "(": "LPAREN",
    ")": "RPAREN",
    ",": "COMMA",
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
}


@dataclass(frozen=True)
class Token:
    """A single lexeme with its source position (and value for numbers)."""

    kind: str
    text: str
    line: int
    column: int
    value: float | None = None


def describe(token: Token) -> str:
    """Human-readable description of a token for error messages."""
    if token.kind == "EOF":
        return "end of input"
    if token.kind == "NEWLINE":
        return "end of line"
    return f"'{token.text}'"


def _is_ident_start(ch: str) -> bool:
    return "a" <= ch <= "z" or "A" <= ch <= "Z" or ch == "_"


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def tokenize(source: str) -> list[Token]:
    """Tokenize *source*, raising :class:`LexError` on unexpected characters."""
    tokens: list[Token] = []
    line, column, i = 1, 1, 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "\r":
            i += 1
            continue
        if ch == "\n":
            tokens.append(Token("NEWLINE", "\\n", line, column))
            line, column, i = line + 1, 1, i + 1
            continue
        if ch in " \t":
            i += 1
            column += 1
            continue
        if ch == "#":
            while i < n and source[i] != "\n":
                i += 1
                column += 1
            continue
        if ch == "-" and i + 1 < n and source[i + 1] == ">":
            tokens.append(Token("ARROW", "->", line, column))
            i += 2
            column += 2
            continue
        if ch in _SYMBOLS:
            tokens.append(Token(_SYMBOLS[ch], ch, line, column))
            i += 1
            column += 1
            continue
        if _is_digit(ch):
            start, start_column = i, column
            while i < n and _is_digit(source[i]):
                i += 1
            if i < n and source[i] == "." and i + 1 < n and _is_digit(source[i + 1]):
                i += 1
                while i < n and _is_digit(source[i]):
                    i += 1
            text = source[start:i]
            column += i - start
            tokens.append(Token("NUMBER", text, line, start_column, value=float(text)))
            continue
        if _is_ident_start(ch):
            start, start_column = i, column
            while i < n and (_is_ident_start(source[i]) or _is_digit(source[i])):
                i += 1
            text = source[start:i]
            column += i - start
            tokens.append(Token("IDENT", text, line, start_column))
            continue
        raise LexError(f"unexpected character '{ch}'", line, column)
    tokens.append(Token("EOF", "", line, column))
    return tokens

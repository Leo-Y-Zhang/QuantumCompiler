"""Error types carrying precise source positions (1-based line/column)."""

from __future__ import annotations


class DaedalusError(Exception):
    """Base class for source-level errors with a line/column position."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"{line}:{column}: {message}")
        self.message = message
        self.line = line
        self.column = column

    def format(self, filename: str = "<input>") -> str:
        """Render as ``file:line:col: error: message`` (gcc-style)."""
        return f"{filename}:{self.line}:{self.column}: error: {self.message}"


class LexError(DaedalusError):
    """Raised for characters the lexer cannot tokenize."""


class ParseError(DaedalusError):
    """Raised for token sequences the parser cannot accept."""

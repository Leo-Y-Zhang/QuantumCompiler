"""Tests for the hand-written lexer, including exact error positions."""

import pytest

from daedalus.errors import LexError
from daedalus.lexer import Token, tokenize


def kinds(tokens: list[Token]) -> list[str]:
    return [t.kind for t in tokens]


class TestTokenize:
    def test_simple_gate_line(self) -> None:
        tokens = tokenize("h q0\n")
        assert kinds(tokens) == ["IDENT", "IDENT", "NEWLINE", "EOF"]
        assert tokens[0].text == "h"
        assert tokens[1].text == "q0"

    def test_positions_are_one_based(self) -> None:
        tokens = tokenize("cx q0, q1\n")
        assert (tokens[0].line, tokens[0].column) == (1, 1)  # cx
        assert (tokens[1].line, tokens[1].column) == (1, 4)  # q0
        assert (tokens[2].line, tokens[2].column) == (1, 6)  # ,
        assert (tokens[3].line, tokens[3].column) == (1, 8)  # q1

    def test_second_line_position(self) -> None:
        tokens = tokenize("qubits 2\nh q1\n")
        h = [t for t in tokens if t.text == "h"][0]
        assert (h.line, h.column) == (2, 1)

    def test_arrow(self) -> None:
        tokens = tokenize("measure q0 -> c0\n")
        assert "ARROW" in kinds(tokens)

    def test_number_int(self) -> None:
        tokens = tokenize("qubits 3\n")
        num = tokens[1]
        assert num.kind == "NUMBER"
        assert num.value == 3.0

    def test_number_float(self) -> None:
        tokens = tokenize("rx(0.5) q0\n")
        num = [t for t in tokens if t.kind == "NUMBER"][0]
        assert num.value == 0.5

    def test_arithmetic_operators(self) -> None:
        tokens = tokenize("rz(2*pi - pi/4 + 1) q0\n")
        assert {"STAR", "MINUS", "SLASH", "PLUS"} <= set(kinds(tokens))

    def test_comment_is_skipped(self) -> None:
        tokens = tokenize("# a comment\nh q0  # trailing\n")
        assert [t.text for t in tokens if t.kind == "IDENT"] == ["h", "q0"]

    def test_blank_lines(self) -> None:
        tokens = tokenize("\n\nh q0\n\n")
        assert [t.text for t in tokens if t.kind == "IDENT"] == ["h", "q0"]

    def test_crlf_line_endings(self) -> None:
        tokens = tokenize("qubits 1\r\nh q0\r\n")
        h = [t for t in tokens if t.text == "h"][0]
        assert (h.line, h.column) == (2, 1)

    def test_missing_final_newline(self) -> None:
        tokens = tokenize("h q0")
        assert kinds(tokens)[-1] == "EOF"


class TestLexErrors:
    def test_unexpected_character_position(self) -> None:
        with pytest.raises(LexError) as exc:
            tokenize("qubits 1\nh $q0\n")
        assert (exc.value.line, exc.value.column) == (2, 3)
        assert "$" in exc.value.message

    def test_formatted_message(self) -> None:
        with pytest.raises(LexError) as exc:
            tokenize("h ?\n")
        assert exc.value.format("prog.qf") == "prog.qf:1:3: error: unexpected character '?'"

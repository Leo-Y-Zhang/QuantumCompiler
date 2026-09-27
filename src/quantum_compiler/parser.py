"""Recursive-descent parser for the QuantumCompiler DSL.

Grammar (one statement per line)::

    program   := line*
    line      := 'qubits' INT | 'bits' INT | gate | measure | barrier
    gate      := NAME operands | NAME '(' expr ')' operands
    operands  := qubit (',' qubit)*
    measure   := 'measure' qubit '->' bit
    barrier   := 'barrier' qubit (',' qubit)*

Every diagnostic carries the 1-based line/column of the offending token.
"""

from __future__ import annotations

import math

from quantum_compiler.angles import parse_expression
from quantum_compiler.errors import ParseError
from quantum_compiler.ir import Circuit, Gate
from quantum_compiler.lexer import Token, describe, tokenize

_SINGLE = ("h", "x", "y", "z", "s", "sdg", "t", "tdg")
_ROTATIONS = ("rx", "ry", "rz")
_PAIRS = ("cx", "cz", "swap")

#: Gate name -> number of qubit operands (measure is handled separately).
GATE_ARITY: dict[str, int] = {
    **dict.fromkeys(_SINGLE + _ROTATIONS, 1),
    **dict.fromkeys(_PAIRS, 2),
}


def parse(source: str) -> Circuit:
    """Parse DSL *source* into a :class:`Circuit`.

    Raises :class:`quantum_compiler.errors.LexError` or :class:`ParseError` with a
    precise position on invalid input.
    """
    return _Parser(tokenize(source)).parse_program()


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # -- token helpers ----------------------------------------------------
    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def skip_newlines(self) -> None:
        while self.peek().kind == "NEWLINE":
            self.pos += 1

    def end_statement(self) -> None:
        token = self.peek()
        if token.kind == "NEWLINE":
            self.pos += 1
        elif token.kind != "EOF":
            raise ParseError(
                f"unexpected {describe(token)} after statement", token.line, token.column
            )

    # -- grammar ----------------------------------------------------------
    def parse_program(self) -> Circuit:
        num_qubits: int | None = None
        num_bits = 0
        bits_declared = False
        gates: list[Gate] = []
        while True:
            self.skip_newlines()
            token = self.peek()
            if token.kind == "EOF":
                break
            if token.kind != "IDENT":
                raise ParseError(
                    f"expected a statement, found {describe(token)}",
                    token.line,
                    token.column,
                )
            if token.text == "qubits":
                if num_qubits is not None:
                    raise ParseError("duplicate 'qubits' declaration", token.line, token.column)
                if gates:
                    raise ParseError(
                        "'qubits' must be declared before gates", token.line, token.column
                    )
                self.advance()
                num_qubits = self.parse_count("qubit count", minimum=1)
            elif token.text == "bits":
                if bits_declared:
                    raise ParseError("duplicate 'bits' declaration", token.line, token.column)
                if gates:
                    raise ParseError(
                        "'bits' must be declared before gates", token.line, token.column
                    )
                self.advance()
                num_bits = self.parse_count("bit count", minimum=0)
                bits_declared = True
            else:
                if num_qubits is None:
                    raise ParseError(
                        "'qubits' must be declared before gates", token.line, token.column
                    )
                if token.text == "measure":
                    gates.append(self.parse_measure(num_qubits, num_bits))
                elif token.text == "barrier":
                    gates.append(self.parse_barrier(num_qubits))
                else:
                    gates.append(self.parse_gate(num_qubits))
            self.end_statement()
        if num_qubits is None:
            num_qubits = 0
        return Circuit(num_qubits=num_qubits, num_bits=num_bits, gates=gates)

    def parse_count(self, what: str, minimum: int) -> int:
        token = self.peek()
        if (
            token.kind != "NUMBER"
            or token.value is None
            or not math.isfinite(token.value)
            or token.value != int(token.value)
        ):
            raise ParseError(
                f"{what} must be an integer, found {describe(token)}",
                token.line,
                token.column,
            )
        count = int(token.value)
        if count < minimum:
            raise ParseError(f"{what} must be at least {minimum}", token.line, token.column)
        self.advance()
        return count

    def parse_gate(self, num_qubits: int) -> Gate:
        name_token = self.advance()
        name = name_token.text
        if name not in GATE_ARITY:
            raise ParseError(f"unknown gate '{name}'", name_token.line, name_token.column)
        angle = self.parse_angle_clause(name)
        qubits = [self.parse_qubit(num_qubits)]
        for _ in range(GATE_ARITY[name] - 1):
            comma = self.peek()
            if comma.kind != "COMMA":
                raise ParseError(
                    f"expected ',' between qubit operands, found {describe(comma)}",
                    comma.line,
                    comma.column,
                )
            self.advance()
            operand_token = self.peek()
            qubit = self.parse_qubit(num_qubits)
            if qubit in qubits:
                raise ParseError(
                    f"duplicate qubit operand 'q{qubit}'",
                    operand_token.line,
                    operand_token.column,
                )
            qubits.append(qubit)
        return Gate(name, tuple(qubits), angle=angle)

    def parse_angle_clause(self, name: str) -> float | None:
        token = self.peek()
        if token.kind == "LPAREN":
            if name not in _ROTATIONS:
                raise ParseError(
                    f"gate '{name}' does not take an angle", token.line, token.column
                )
            self.advance()
            value, self.pos = parse_expression(self.tokens, self.pos)
            closing = self.peek()
            if closing.kind != "RPAREN":
                raise ParseError(
                    f"expected ')' after angle, found {describe(closing)}",
                    closing.line,
                    closing.column,
                )
            self.advance()
            return value
        if name in _ROTATIONS:
            raise ParseError(
                f"gate '{name}' requires an angle, e.g. {name}(pi/2)",
                token.line,
                token.column,
            )
        return None

    def parse_measure(self, num_qubits: int, num_bits: int) -> Gate:
        self.advance()  # 'measure'
        qubit = self.parse_qubit(num_qubits)
        arrow = self.peek()
        if arrow.kind != "ARROW":
            raise ParseError(
                f"expected '->' after measured qubit, found {describe(arrow)}",
                arrow.line,
                arrow.column,
            )
        self.advance()
        bit = self.parse_register("c", num_bits, "bit", "bits")
        return Gate("measure", (qubit,), bit=bit)

    def parse_barrier(self, num_qubits: int) -> Gate:
        self.advance()  # 'barrier'
        qubits = [self.parse_qubit(num_qubits)]
        while self.peek().kind == "COMMA":
            self.advance()
            operand = self.peek()
            qubit = self.parse_qubit(num_qubits)
            if qubit in qubits:
                raise ParseError(
                    f"duplicate qubit operand 'q{qubit}'", operand.line, operand.column
                )
            qubits.append(qubit)
        return Gate("barrier", tuple(qubits))

    def parse_qubit(self, num_qubits: int) -> int:
        return self.parse_register("q", num_qubits, "qubit", "qubits")

    def parse_register(self, prefix: str, size: int, kind: str, decl: str) -> int:
        token = self.peek()
        text = token.text
        if (
            token.kind != "IDENT"
            or len(text) < 2
            or not text.startswith(prefix)
            or not text[1:].isdigit()
        ):
            raise ParseError(
                f"expected {kind} operand like '{prefix}0', found {describe(token)}",
                token.line,
                token.column,
            )
        index = int(text[1:])
        if index >= size:
            raise ParseError(
                f"{kind} '{text}' out of range (declared {decl} {size})",
                token.line,
                token.column,
            )
        self.advance()
        return index

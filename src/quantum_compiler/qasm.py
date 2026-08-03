"""OpenQASM 2.0 interop: an emitter and a documented-subset importer.

Emitter
-------
:func:`emit_qasm` serializes any :class:`~quantum_compiler.ir.Circuit` to OpenQASM 2.0
text targeting the standard ``qelib1.inc`` gate library. Registers are always
named ``q`` and ``c``; rotation angles are emitted as plain Python floats
(``repr``), so symbolic spellings like ``pi/4`` are lost but the value is
preserved bit-exactly.

Importer
--------
:func:`parse_qasm` accepts a deliberately small, documented subset of
OpenQASM 2.0 — enough to round-trip everything the emitter produces plus
hand-written files of the same shape:

- a mandatory ``OPENQASM 2.0;`` header, then optional ``include "qelib1.inc";``
- exactly one ``qreg`` and at most one ``creg`` (any names; sizes >= 1)
- gate ops from the qelib1 subset ``h x y z s sdg t tdg rx ry rz cx cz swap``
  with *indexed* operands only (``q[0]``, never a whole register)
- ``measure q[i] -> c[j];`` and ``barrier q[i], q[j], ...;``
- angle expressions over numbers (including exponent notation), ``pi``,
  ``+ - * /``, unary minus, and parentheses
- ``//`` comments; statements are free-form (newlines are insignificant)

Everything else — user-defined ``gate`` blocks, ``if``, ``opaque``, ``reset``,
the ``U``/``CX`` builtins, whole-register broadcast, multiple qregs/cregs — is
rejected with a precise 1-based line:column error, in the same format as the
DSL parser's diagnostics.
"""

from __future__ import annotations

from quantum_compiler.angles import parse_expression
from quantum_compiler.errors import LexError, ParseError
from quantum_compiler.ir import Circuit, Gate
from quantum_compiler.lexer import Token, describe
from quantum_compiler.parser import GATE_ARITY

_ROTATIONS = ("rx", "ry", "rz")

_UNSUPPORTED = {
    "gate": "user-defined gates are not supported",
    "opaque": "'opaque' declarations are not supported",
    "if": "'if' statements are not supported",
    "reset": "'reset' is not supported",
}

_BUILTINS = ("U", "CX")


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------


def emit_qasm(circuit: Circuit) -> str:
    """Serialize *circuit* as OpenQASM 2.0 text (see module docstring)."""
    if circuit.num_qubits < 1:
        raise ValueError("cannot emit OpenQASM for a circuit with no qubits")
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{circuit.num_qubits}];"]
    if circuit.num_bits:
        lines.append(f"creg c[{circuit.num_bits}];")
    for gate in circuit.gates:
        if gate.name == "measure":
            lines.append(f"measure q[{gate.qubits[0]}] -> c[{gate.bit}];")
        elif gate.name == "barrier":
            lines.append("barrier " + ",".join(f"q[{q}]" for q in gate.qubits) + ";")
        elif gate.angle is not None:
            lines.append(f"{gate.name}({gate.angle!r}) q[{gate.qubits[0]}];")
        else:
            operands = ",".join(f"q[{q}]" for q in gate.qubits)
            lines.append(f"{gate.name} {operands};")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Lexer (OpenQASM is free-form: newlines are whitespace, comments are ``//``)
# ---------------------------------------------------------------------------

_SYMBOLS = {
    "(": "LPAREN",
    ")": "RPAREN",
    "[": "LBRACKET",
    "]": "RBRACKET",
    "{": "LBRACE",
    "}": "RBRACE",
    ",": "COMMA",
    ";": "SEMI",
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "=": "EQUALS",
}


def _is_ident_start(ch: str) -> bool:
    return "a" <= ch <= "z" or "A" <= ch <= "Z" or ch == "_"


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def _tokenize(source: str) -> list[Token]:
    """Tokenize QASM *source*, raising :class:`LexError` on stray characters."""
    tokens: list[Token] = []
    line, column, i = 1, 1, 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "\r":
            i += 1
            continue
        if ch == "\n":
            line, column, i = line + 1, 1, i + 1
            continue
        if ch in " \t":
            i += 1
            column += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "-" and i + 1 < n and source[i + 1] == ">":
            tokens.append(Token("ARROW", "->", line, column))
            i += 2
            column += 2
            continue
        if ch == '"':
            start, start_column = i, column
            i += 1
            while i < n and source[i] not in '"\n':
                i += 1
            if i >= n or source[i] != '"':
                raise LexError("unterminated string literal", line, start_column)
            i += 1
            text = source[start:i]
            column += i - start
            tokens.append(Token("STRING", text, line, start_column))
            continue
        if ch in _SYMBOLS:
            tokens.append(Token(_SYMBOLS[ch], ch, line, column))
            i += 1
            column += 1
            continue
        if _is_digit(ch) or (ch == "." and i + 1 < n and _is_digit(source[i + 1])):
            start, start_column = i, column
            while i < n and _is_digit(source[i]):
                i += 1
            if i < n and source[i] == "." and i + 1 < n and _is_digit(source[i + 1]):
                i += 1
                while i < n and _is_digit(source[i]):
                    i += 1
            if (
                i < n
                and source[i] in "eE"
                and (
                    (i + 1 < n and _is_digit(source[i + 1]))
                    or (
                        i + 2 < n
                        and source[i + 1] in "+-"
                        and _is_digit(source[i + 2])
                    )
                )
            ):
                i += 2 if source[i + 1] in "+-" else 1
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


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_qasm(source: str) -> Circuit:
    """Parse the supported OpenQASM 2.0 subset into a :class:`Circuit`.

    Raises :class:`quantum_compiler.errors.LexError` or :class:`ParseError` with a
    precise 1-based line/column position on anything outside the subset.
    """
    return _QasmParser(_tokenize(source)).parse_program()


class _QasmParser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.qreg: tuple[str, int] | None = None
        self.creg: tuple[str, int] | None = None
        self.gates: list[Gate] = []

    # -- token helpers ----------------------------------------------------
    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, kind: str, what: str) -> Token:
        token = self.peek()
        if token.kind != kind:
            raise ParseError(
                f"expected {what}, found {describe(token)}", token.line, token.column
            )
        return self.advance()

    def end_statement(self) -> None:
        token = self.peek()
        if token.kind != "SEMI":
            raise ParseError(
                f"expected ';' after statement, found {describe(token)}",
                token.line,
                token.column,
            )
        self.advance()

    # -- grammar ----------------------------------------------------------
    def parse_program(self) -> Circuit:
        self.parse_header()
        while True:
            token = self.peek()
            if token.kind == "EOF":
                break
            if token.kind != "IDENT":
                raise ParseError(
                    f"expected a statement, found {describe(token)}",
                    token.line,
                    token.column,
                )
            if token.text == "include":
                self.parse_include()
            elif token.text in ("qreg", "creg"):
                self.parse_register_decl()
            elif token.text in _UNSUPPORTED:
                raise ParseError(_UNSUPPORTED[token.text], token.line, token.column)
            elif token.text in _BUILTINS:
                raise ParseError(
                    f"builtin '{token.text}' is not supported; "
                    "use the qelib1 gate names (h x y z s sdg t tdg rx ry rz "
                    "cx cz swap)",
                    token.line,
                    token.column,
                )
            elif token.text == "measure":
                self.parse_measure()
            elif token.text == "barrier":
                self.parse_barrier()
            elif token.text in GATE_ARITY:
                self.parse_gate()
            else:
                raise ParseError(
                    f"unknown gate '{token.text}'", token.line, token.column
                )
        num_qubits = self.qreg[1] if self.qreg else 0
        num_bits = self.creg[1] if self.creg else 0
        return Circuit(num_qubits=num_qubits, num_bits=num_bits, gates=self.gates)

    def parse_header(self) -> None:
        token = self.peek()
        if token.kind != "IDENT" or token.text != "OPENQASM":
            raise ParseError(
                f"expected 'OPENQASM 2.0;' header, found {describe(token)}",
                token.line,
                token.column,
            )
        self.advance()
        version = self.peek()
        if version.kind != "NUMBER" or version.text != "2.0":
            raise ParseError(
                f"only OPENQASM 2.0 is supported, found {describe(version)}",
                version.line,
                version.column,
            )
        self.advance()
        self.end_statement()

    def parse_include(self) -> None:
        self.advance()  # 'include'
        token = self.expect("STRING", "a file name string after 'include'")
        if token.text != '"qelib1.inc"':
            raise ParseError(
                f'only include "qelib1.inc" is supported, found {token.text}',
                token.line,
                token.column,
            )
        self.end_statement()

    def parse_register_decl(self) -> None:
        keyword = self.advance()  # 'qreg' or 'creg'
        is_qreg = keyword.text == "qreg"
        if (self.qreg if is_qreg else self.creg) is not None:
            raise ParseError(
                f"only a single {keyword.text} is supported",
                keyword.line,
                keyword.column,
            )
        name_token = self.expect("IDENT", f"a register name after '{keyword.text}'")
        other = self.creg if is_qreg else self.qreg
        if other is not None and other[0] == name_token.text:
            raise ParseError(
                f"register '{name_token.text}' already declared",
                name_token.line,
                name_token.column,
            )
        self.expect("LBRACKET", f"'[' after register name '{name_token.text}'")
        size_token = self.peek()
        if size_token.kind != "NUMBER" or not size_token.text.isdigit():
            raise ParseError(
                f"register size must be an integer, found {describe(size_token)}",
                size_token.line,
                size_token.column,
            )
        size = int(size_token.text)
        if size < 1:
            raise ParseError(
                f"{keyword.text} size must be at least 1",
                size_token.line,
                size_token.column,
            )
        self.advance()
        self.expect("RBRACKET", "']' after register size")
        self.end_statement()
        if is_qreg:
            self.qreg = (name_token.text, size)
        else:
            self.creg = (name_token.text, size)

    def parse_gate(self) -> None:
        name_token = self.advance()
        name = name_token.text
        angle = self.parse_angle_clause(name)
        qubits = [self.parse_operand(quantum=True)]
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
            qubit = self.parse_operand(quantum=True)
            if qubit in qubits:
                raise ParseError(
                    "duplicate qubit operand "
                    f"'{operand_token.text}[{qubit}]'",
                    operand_token.line,
                    operand_token.column,
                )
            qubits.append(qubit)
        self.end_statement()
        self.gates.append(Gate(name, tuple(qubits), angle=angle))

    def parse_angle_clause(self, name: str) -> float | None:
        token = self.peek()
        if token.kind == "LPAREN":
            if name not in _ROTATIONS:
                raise ParseError(
                    f"gate '{name}' does not take an angle", token.line, token.column
                )
            self.advance()
            value, self.pos = parse_expression(self.tokens, self.pos)
            self.expect("RPAREN", "')' after angle")
            return value
        if name in _ROTATIONS:
            raise ParseError(
                f"gate '{name}' requires an angle, e.g. {name}(pi/2)",
                token.line,
                token.column,
            )
        return None

    def parse_measure(self) -> None:
        self.advance()  # 'measure'
        qubit = self.parse_operand(quantum=True)
        arrow = self.peek()
        if arrow.kind != "ARROW":
            raise ParseError(
                f"expected '->' after measured qubit, found {describe(arrow)}",
                arrow.line,
                arrow.column,
            )
        self.advance()
        bit = self.parse_operand(quantum=False)
        self.end_statement()
        self.gates.append(Gate("measure", (qubit,), bit=bit))

    def parse_barrier(self) -> None:
        self.advance()  # 'barrier'
        qubits = [self.parse_operand(quantum=True)]
        while self.peek().kind == "COMMA":
            self.advance()
            operand = self.peek()
            qubit = self.parse_operand(quantum=True)
            if qubit in qubits:
                raise ParseError(
                    f"duplicate qubit operand 'q[{qubit}]'", operand.line, operand.column
                )
            qubits.append(qubit)
        self.end_statement()
        self.gates.append(Gate("barrier", tuple(qubits)))

    def parse_operand(self, quantum: bool) -> int:
        kind_word = "qubit" if quantum else "bit"
        name_token = self.peek()
        if name_token.kind != "IDENT":
            raise ParseError(
                f"expected a {kind_word} operand like reg[0], "
                f"found {describe(name_token)}",
                name_token.line,
                name_token.column,
            )
        register = self.resolve_register(name_token, quantum)
        self.advance()
        bracket = self.peek()
        if bracket.kind != "LBRACKET":
            raise ParseError(
                f"expected '[' after register name '{name_token.text}' "
                "(whole-register operands are not supported)",
                bracket.line,
                bracket.column,
            )
        self.advance()
        index_token = self.peek()
        if index_token.kind != "NUMBER" or not index_token.text.isdigit():
            raise ParseError(
                f"{kind_word} index must be an integer, found {describe(index_token)}",
                index_token.line,
                index_token.column,
            )
        index = int(index_token.text)
        reg_name, reg_size = register
        if index >= reg_size:
            decl = "qreg" if quantum else "creg"
            raise ParseError(
                f"{kind_word} index {index} out of range for "
                f"{decl} {reg_name}[{reg_size}]",
                index_token.line,
                index_token.column,
            )
        self.advance()
        self.expect("RBRACKET", f"']' after {kind_word} index")
        return index

    def resolve_register(self, token: Token, quantum: bool) -> tuple[str, int]:
        wanted, other = (self.qreg, self.creg) if quantum else (self.creg, self.qreg)
        if wanted is not None and token.text == wanted[0]:
            return wanted
        if other is not None and token.text == other[0]:
            found = "classical register" if quantum else "qubit register"
            expected = "a qubit" if quantum else "a classical bit"
            raise ParseError(
                f"expected {expected} operand, found {found} '{token.text}'",
                token.line,
                token.column,
            )
        if not quantum and self.creg is None:
            raise ParseError(
                f"cannot resolve '{token.text}': no creg declared",
                token.line,
                token.column,
            )
        raise ParseError(f"unknown register '{token.text}'", token.line, token.column)

"""Tests for the safe angle-expression evaluator."""

import math

import pytest

from daedalus.angles import evaluate, format_angle
from daedalus.errors import DaedalusError, ParseError


class TestEvaluate:
    def test_plain_integer(self) -> None:
        assert evaluate("2") == 2.0

    def test_plain_float(self) -> None:
        assert evaluate("0.25") == 0.25

    def test_pi(self) -> None:
        assert evaluate("pi") == math.pi

    def test_pi_division(self) -> None:
        assert evaluate("pi/4") == math.pi / 4

    def test_pi_multiplication(self) -> None:
        assert evaluate("2*pi") == 2 * math.pi

    def test_negative_pi_division(self) -> None:
        assert evaluate("-pi/2") == -math.pi / 2

    def test_addition_and_subtraction(self) -> None:
        assert evaluate("pi/4 + pi/4") == pytest.approx(math.pi / 2)
        assert evaluate("pi - pi/2") == pytest.approx(math.pi / 2)

    def test_precedence(self) -> None:
        assert evaluate("1 + 2*3") == 7.0

    def test_parentheses(self) -> None:
        assert evaluate("(1 + 2)*3") == 9.0

    def test_nested_unary(self) -> None:
        assert evaluate("--2") == 2.0
        assert evaluate("+-2") == -2.0

    def test_mixed_pi_arithmetic(self) -> None:
        assert evaluate("3*pi/4") == pytest.approx(3 * math.pi / 4)


class TestEvaluateErrors:
    def test_empty(self) -> None:
        with pytest.raises(ParseError):
            evaluate("")

    def test_trailing_operator(self) -> None:
        with pytest.raises(ParseError):
            evaluate("pi/")

    def test_division_by_zero(self) -> None:
        with pytest.raises(ParseError, match="division by zero"):
            evaluate("pi/0")

    def test_unknown_identifier(self) -> None:
        with pytest.raises(ParseError, match="unknown identifier 'tau'") as exc:
            evaluate("2*tau")
        assert exc.value.column == 3

    def test_unclosed_paren(self) -> None:
        with pytest.raises(ParseError, match=r"expected '\)'"):
            evaluate("(pi")

    def test_trailing_garbage(self) -> None:
        with pytest.raises(ParseError):
            evaluate("1 2")

    def test_no_eval_of_python(self) -> None:
        # Quotes are not even lexable; identifiers are rejected by the parser.
        with pytest.raises(DaedalusError):
            evaluate("__import__('os')")
        with pytest.raises(ParseError, match="unknown identifier"):
            evaluate("__import__")


class TestFormatAngle:
    def test_quarter_pi(self) -> None:
        assert format_angle(math.pi / 4) == "pi/4"

    def test_pi(self) -> None:
        assert format_angle(math.pi) == "pi"

    def test_negative_half_pi(self) -> None:
        assert format_angle(-math.pi / 2) == "-pi/2"

    def test_two_pi(self) -> None:
        assert format_angle(2 * math.pi) == "2*pi"

    def test_three_quarter_pi(self) -> None:
        assert format_angle(3 * math.pi / 4) == "3*pi/4"

    def test_zero(self) -> None:
        assert format_angle(0.0) == "0"

    def test_plain_float_falls_back_to_repr(self) -> None:
        assert format_angle(0.7) == "0.7"

    def test_round_trip(self) -> None:
        for theta in (math.pi / 3, -math.pi / 8, 5 * math.pi / 6, 1.234):
            assert evaluate(format_angle(theta)) == pytest.approx(theta, abs=1e-15)

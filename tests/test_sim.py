"""Simulator tests against hand-computed amplitudes."""

import cmath
import math
import random

import pytest

from daedalus.ir import Circuit
from daedalus.parser import parse
from daedalus.sim import MAX_QUBITS, basis_state, random_state, simulate

INV_SQRT2 = 1 / math.sqrt(2)


def assert_state(actual: list[complex], expected: list[complex]) -> None:
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert a == pytest.approx(e, abs=1e-12)


class TestSingleQubit:
    def test_h_on_zero(self) -> None:
        state = simulate(parse("qubits 1\nh q0\n"))
        assert_state(state, [INV_SQRT2, INV_SQRT2])

    def test_h_on_one(self) -> None:
        state = simulate(parse("qubits 1\nh q0\n"), initial=basis_state(1, 1))
        assert_state(state, [INV_SQRT2, -INV_SQRT2])

    def test_x(self) -> None:
        state = simulate(parse("qubits 1\nx q0\n"))
        assert_state(state, [0, 1])

    def test_y_on_zero(self) -> None:
        state = simulate(parse("qubits 1\ny q0\n"))
        assert_state(state, [0, 1j])

    def test_z_on_one(self) -> None:
        state = simulate(parse("qubits 1\nz q0\n"), initial=basis_state(1, 1))
        assert_state(state, [0, -1])

    def test_s_t_phases(self) -> None:
        state = simulate(parse("qubits 1\ns q0\n"), initial=basis_state(1, 1))
        assert_state(state, [0, 1j])
        state = simulate(parse("qubits 1\nt q0\n"), initial=basis_state(1, 1))
        assert_state(state, [0, cmath.exp(1j * math.pi / 4)])

    def test_rz_phase(self) -> None:
        state = simulate(parse("qubits 1\nrz(pi/2) q0\n"), initial=basis_state(1, 1))
        assert_state(state, [0, cmath.exp(1j * math.pi / 4)])

    def test_rx_half_turn(self) -> None:
        state = simulate(parse("qubits 1\nrx(pi) q0\n"))
        assert_state(state, [0, -1j])

    def test_ry_quarter_turn(self) -> None:
        state = simulate(parse("qubits 1\nry(pi/2) q0\n"))
        assert_state(state, [INV_SQRT2, INV_SQRT2])


class TestMultiQubit:
    def test_bell_state(self) -> None:
        state = simulate(parse("qubits 2\nh q0\ncx q0, q1\n"))
        assert_state(state, [INV_SQRT2, 0, 0, INV_SQRT2])

    def test_ghz_state(self) -> None:
        state = simulate(parse("qubits 3\nh q0\ncx q0, q1\ncx q1, q2\n"))
        expected = [0.0] * 8
        expected[0] = expected[7] = INV_SQRT2
        assert_state(state, expected)

    def test_cx_control_is_first_operand(self) -> None:
        # q1 set, control is q0 (unset): nothing happens.
        state = simulate(parse("qubits 2\ncx q0, q1\n"), initial=basis_state(2, 2))
        assert_state(state, [0, 0, 1, 0])

    def test_cz_phase(self) -> None:
        state = simulate(parse("qubits 2\ncz q0, q1\n"), initial=basis_state(2, 3))
        assert_state(state, [0, 0, 0, -1])

    def test_swap(self) -> None:
        # |q1 q0> = |0 1> (index 1) -> |1 0> (index 2)
        state = simulate(parse("qubits 2\nswap q0, q1\n"), initial=basis_state(2, 1))
        assert_state(state, [0, 0, 1, 0])

    def test_measure_gates_are_ignored(self) -> None:
        with_measure = simulate(parse("qubits 1\nbits 1\nh q0\nmeasure q0 -> c0\n"))
        without = simulate(parse("qubits 1\nh q0\n"))
        assert_state(with_measure, without)


class TestHelpers:
    def test_basis_state(self) -> None:
        assert basis_state(2, 3) == [0, 0, 0, 1]

    def test_random_state_is_normalized_and_deterministic(self) -> None:
        a = random_state(3, random.Random(7))
        b = random_state(3, random.Random(7))
        assert a == b
        assert sum(abs(z) ** 2 for z in a) == pytest.approx(1.0)

    def test_qubit_limit(self) -> None:
        big = Circuit(num_qubits=MAX_QUBITS + 1, num_bits=0, gates=[])
        with pytest.raises(ValueError):
            simulate(big)

    def test_unitarity_preserved(self) -> None:
        src = "qubits 3\nh q0\ncx q0, q1\nrz(0.3) q1\nswap q1, q2\nt q2\n"
        state = simulate(parse(src), initial=random_state(3, random.Random(1)))
        assert sum(abs(z) ** 2 for z in state) == pytest.approx(1.0)

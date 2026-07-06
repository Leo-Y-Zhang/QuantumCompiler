"""Pure-stdlib statevector simulator (lists of complex, up to 10 qubits).

Conventions
-----------
Qubit ``k`` is bit ``k`` of the basis-state index, so qubit 0 is the least
significant bit: basis index 3 of a 2-qubit register means ``q1=1, q0=1``.

``measure`` operations are skipped: the simulator computes the
pre-measurement state, which is exactly what the equivalence checker
compares (optimization passes never move or alter measure gates).
"""

from __future__ import annotations

import cmath
import math
import random

from qforge.ir import Circuit, Gate

#: Hard cap: a statevector for n qubits has 2**n complex entries.
MAX_QUBITS = 10

_Matrix2 = tuple[complex, complex, complex, complex]


def basis_state(num_qubits: int, index: int) -> list[complex]:
    """Return the computational basis state ``|index>`` for *num_qubits*."""
    state = [0j] * (1 << num_qubits)
    state[index] = 1 + 0j
    return state


def random_state(num_qubits: int, rng: random.Random) -> list[complex]:
    """Return a normalized Haar-like random state drawn from *rng*."""
    amplitudes = [
        complex(rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)) for _ in range(1 << num_qubits)
    ]
    norm = math.sqrt(sum(abs(a) ** 2 for a in amplitudes))
    return [a / norm for a in amplitudes]


def simulate(circuit: Circuit, initial: list[complex] | None = None) -> list[complex]:
    """Apply *circuit* to *initial* (default ``|0...0>``) and return the state."""
    if circuit.num_qubits > MAX_QUBITS:
        raise ValueError(
            f"simulator supports at most {MAX_QUBITS} qubits, got {circuit.num_qubits}"
        )
    dimension = 1 << circuit.num_qubits
    state = basis_state(circuit.num_qubits, 0) if initial is None else [complex(a) for a in initial]
    if len(state) != dimension:
        raise ValueError(f"initial state must have {dimension} amplitudes, got {len(state)}")
    for gate in circuit.gates:
        if gate.name == "measure":
            continue
        if gate.name == "cx":
            _apply_cx(state, gate.qubits[0], gate.qubits[1])
        elif gate.name == "cz":
            _apply_cz(state, gate.qubits[0], gate.qubits[1])
        elif gate.name == "swap":
            _apply_swap(state, gate.qubits[0], gate.qubits[1])
        else:
            _apply_single(state, gate.qubits[0], _matrix(gate))
    return state


def _matrix(gate: Gate) -> _Matrix2:
    """Row-major 2x2 matrix (a, b, c, d) for a single-qubit gate."""
    name = gate.name
    if name == "h":
        s = 1 / math.sqrt(2)
        return (s, s, s, -s)
    if name == "x":
        return (0, 1, 1, 0)
    if name == "y":
        return (0, -1j, 1j, 0)
    if name == "z":
        return (1, 0, 0, -1)
    if name == "s":
        return (1, 0, 0, 1j)
    if name == "sdg":
        return (1, 0, 0, -1j)
    if name == "t":
        return (1, 0, 0, cmath.exp(1j * math.pi / 4))
    if name == "tdg":
        return (1, 0, 0, cmath.exp(-1j * math.pi / 4))
    half = (gate.angle or 0.0) / 2
    if name == "rx":
        return (math.cos(half), -1j * math.sin(half), -1j * math.sin(half), math.cos(half))
    if name == "ry":
        return (math.cos(half), -math.sin(half), math.sin(half), math.cos(half))
    if name == "rz":
        return (cmath.exp(-1j * half), 0, 0, cmath.exp(1j * half))
    raise ValueError(f"no single-qubit matrix for gate '{name}'")


def _apply_single(state: list[complex], qubit: int, m: _Matrix2) -> None:
    a, b, c, d = m
    bit = 1 << qubit
    for i in range(len(state)):
        if not i & bit:
            j = i | bit
            s0, s1 = state[i], state[j]
            state[i] = a * s0 + b * s1
            state[j] = c * s0 + d * s1


def _apply_cx(state: list[complex], control: int, target: int) -> None:
    cbit, tbit = 1 << control, 1 << target
    for i in range(len(state)):
        if i & cbit and not i & tbit:
            j = i | tbit
            state[i], state[j] = state[j], state[i]


def _apply_cz(state: list[complex], a: int, b: int) -> None:
    both = (1 << a) | (1 << b)
    for i in range(len(state)):
        if i & both == both:
            state[i] = -state[i]


def _apply_swap(state: list[complex], a: int, b: int) -> None:
    abit, bbit = 1 << a, 1 << b
    for i in range(len(state)):
        if i & abit and not i & bbit:
            j = (i ^ abit) | bbit
            state[i], state[j] = state[j], state[i]

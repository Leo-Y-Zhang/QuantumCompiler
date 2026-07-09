"""Commutation-aware cancellation of basis-diagonal gates across cx/cz.

Two independent commutation rules, one per basis:

**Z-basis (diagonal gates through cx controls / cz).** ``cx = P0 (x) I +
P1 (x) X`` in the (control, target) factorization, where ``P0``/``P1`` are
computational-basis projectors. Any gate diagonal in the computational basis on
the *control* qubit commutes with both projectors, hence with the whole cx.
``cz`` is itself diagonal, so diagonal gates commute through *either* of its
qubits. Diagonal gates: ``z s sdg t tdg rz``.

**X-basis (X-type gates through cx targets).** On the *target*, ``cx`` acts as
``X`` conditioned on the control, and ``X`` commutes with ``X``; concretely
``(I (x) X)`` and ``(I (x) rx(a))`` commute with ``cx``. So an ``x``/``rx`` on a
cx *target* slides through it. (``y`` is excluded: it anticommutes with the
target ``X``. ``cz`` is excluded: it is not X-diagonal.)

For each basis the pass scans every wire: a basis gate may slide forward across
"transparent" gates for that basis; if the first non-transparent gate it meets
is a matching partner it cancels (``z z``, ``s sdg``, ``t tdg``, ``x x``) or
merges (``rz rz``, ``rx rx``). Anything else blocks. The two bases touch
disjoint gate-name sets, so they are applied one after the other on the same
working list.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from daedalus.ir import Circuit, Gate
from daedalus.passes.merge_rotations import is_zero_mod_two_pi


@dataclass(frozen=True)
class _Basis:
    """One commutation rule: which gates are diagonal, transparent, and paired."""

    diagonal: frozenset[str]
    rotation: str
    inverse_pairs: frozenset[tuple[str, str]]
    transparent: Callable[[Gate, int], bool]


def _z_transparent(gate: Gate, q: int) -> bool:
    """A z-diagonal gate on *q* commutes through a cx control or a cz."""
    if gate.name == "cx":
        return gate.qubits[0] == q
    return gate.name == "cz" and q in gate.qubits


def _x_transparent(gate: Gate, q: int) -> bool:
    """An x-type gate on *q* commutes through a cx target."""
    return gate.name == "cx" and gate.qubits[1] == q


_Z_BASIS = _Basis(
    diagonal=frozenset({"z", "s", "sdg", "t", "tdg", "rz"}),
    rotation="rz",
    inverse_pairs=frozenset(
        {("z", "z"), ("s", "sdg"), ("sdg", "s"), ("t", "tdg"), ("tdg", "t")}
    ),
    transparent=_z_transparent,
)
_X_BASIS = _Basis(
    diagonal=frozenset({"x", "rx"}),
    rotation="rx",
    inverse_pairs=frozenset({("x", "x")}),
    transparent=_x_transparent,
)
_BASES = (_Z_BASIS, _X_BASIS)


class CommuteCancel:
    """Cancel/merge basis-diagonal gates separated only by transparent gates."""

    name = "commute-cancel"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* with commutation-enabled diagonal pairs reduced."""
        gates: list[Gate | None] = list(circuit.gates)
        wires = circuit.qubit_wires()
        changed = False
        for basis in _BASES:
            for q, wire in wires.items():
                for position in range(len(wire)):
                    first = gates[wire[position]]
                    if first is None or first.name not in basis.diagonal:
                        continue
                    if _try_reduce(basis, q, wire, position, gates):
                        changed = True
        if not changed:
            return circuit
        return circuit.replace_gates(g for g in gates if g is not None)


def _try_reduce(
    basis: _Basis, q: int, wire: list[int], position: int, gates: list[Gate | None]
) -> bool:
    """Slide the diagonal gate at ``wire[position]`` forward; reduce if possible."""
    i = wire[position]
    first = gates[i]
    assert first is not None
    for j in wire[position + 1 :]:
        second = gates[j]
        if second is None:
            continue
        if basis.transparent(second, q):
            continue
        if second.name in basis.diagonal:
            if first.name == basis.rotation and second.name == basis.rotation:
                total = (first.angle or 0.0) + (second.angle or 0.0)
                gates[j] = None
                gates[i] = None if is_zero_mod_two_pi(total) else replace(first, angle=total)
                return True
            if (first.name, second.name) in basis.inverse_pairs:
                gates[i] = gates[j] = None
                return True
        return False
    return False

"""Opt-in dead-code elimination (off by default; enable with ``--dce``).

Liveness is connectivity-based: a qubit is live iff it is connected to a
measured qubit through any chain of shared gates (union-find over qubits).
Gates whose qubits are all dead are removed; measures are always kept.

Caveat (why this is off by default): removing gates on unmeasured qubits
changes the unobserved part of the final statevector, so this pass is NOT
statevector-preserving and fails the full-state equivalence check whenever it
removes anything. It preserves measurement statistics on the measured qubits.
With no measurements at all, every gate is dead and the circuit empties.
"""

from __future__ import annotations

from quantum_compiler.ir import Circuit


class DeadCodeElimination:
    """Remove gates that cannot influence any measured qubit."""

    name = "dead-code"

    def run(self, circuit: Circuit) -> Circuit:
        """Return *circuit* without gates on qubits disconnected from measures."""
        parent = list(range(circuit.num_qubits))

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for gate in circuit.gates:
            if gate.name == "barrier":
                continue  # a fence is not a data interaction; do not connect wires
            root = find(gate.qubits[0])
            for q in gate.qubits[1:]:
                parent[find(q)] = root
        live_roots = {find(g.qubits[0]) for g in circuit.gates if g.name == "measure"}
        kept = [
            gate
            for gate in circuit.gates
            if gate.name == "measure" or any(find(q) in live_roots for q in gate.qubits)
        ]
        if len(kept) == len(circuit.gates):
            return circuit
        return circuit.replace_gates(kept)

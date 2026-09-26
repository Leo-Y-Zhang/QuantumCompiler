# What QuantumCompiler is for

Requirements, described from the shipped code at v1.2.0 rather than from a
plan that preceded it. Technical design: [TDD.md](TDD.md). The one visual
surface: [DESIGN_BRIEF.md](DESIGN_BRIEF.md).

## The claim nobody checks

Almost every teaching compiler — and a good number of research ones — *asserts*
that its optimizations preserve meaning. The rewrite rules look obviously
correct on a whiteboard, so nobody checks, and the bugs that do occur are the
subtle ones: a rotation merged with the wrong sign, a gate commuted past a
control it does not commute with, a router whose SWAP insertions permute the
qubits and quietly change the answer. In quantum circuits this is worse than
usual, because the output is a complex amplitude vector that a human cannot
eyeball — a wrong global phase is invisible and harmless, a wrong *relative*
phase is invisible and fatal.

So the problem being solved here is not "make quantum circuits smaller". It is
to **learn to build a compiler whose optimizations are checked rather than
claimed**, in a domain where the check is mechanically possible because the
semantics of a circuit is a finite matrix you can compute.

## Who it is for, and who it is not for

Two readers. The first is the author, learning compiler construction end to end
— lexer, recursive-descent parser, IR, pass manager, backend — and
quantum-circuit semantics at the same time, without leaning on Qiskit to do any
of the interesting parts. The second is someone reading the portfolio and
assessing whether the author can design a system, state its limits honestly and
prove its claims. That reader is technical, sceptical, and will open the code,
which makes overclaiming in the README the failure mode worth designing
against.

It is not for anyone with a quantum circuit they actually need compiled. Qiskit
and t|ket⟩ exist and are better at that in every respect.

## The sharpest decision in the project: phase

The equivalence oracle could have been written the cheap way, letting each
input state carry its own global phase. That version is *unsound*, and the
counterexample is embarrassingly small: it accepts `z` as equivalent to the
identity, because every computational basis state is an eigenvector of `z`.

The oracle therefore fixes one phase from the first input and requires every
subsequent input to agree under *that* phase, with seeded random — deliberately
non-basis — states included precisely to catch this case. The reasoning lives
in the `verify.py` module docstring, next to the code it constrains.

Everything else about the verification story follows from taking that seriously:

- Every optimization pass is re-verified against the unoptimized circuit, and
  the suite asserts it **per pass**, not once globally (`tests/test_pass_*.py`,
  525 tests in total).
- The oracle has an *exact* mode, not only a sampled one. For circuits up to
  seven qubits it builds both `2ⁿ×2ⁿ` unitaries and compares them, so at least
  some verdicts are genuine proofs (`unitary.py`, `PROOF_MAX_QUBITS = 7`).
- The compiler refuses to emit a circuit that fails verification. It exits
  non-zero rather than printing a warning — exit code `3`, in `cli.py`'s
  `_run_compile`, `_run_route` and `_run_equiv`.
- Routing, the part most likely to be silently wrong, is verified up to the
  qubit permutation its SWAPs induce, on every example across all five
  topologies and on random circuits (`verify.check_routing_equivalence`,
  `tests/test_route.py`).
- One real algorithm is proven end to end rather than a bag of toy identities:
  the 3-qubit QFT built from elementary gates equals the analytic 8-point DFT
  matrix up to global phase (`tests/test_examples.py`).

Two further marks of done, less dramatic but load-bearing: zero runtime
dependencies, standard library only, with every matrix, every complex number
and the SVG writer hand-rolled; and a README that states what the project is
*not* before a reader has to discover it.

## Requirements

**Must**

- A DSL with real diagnostics: parse errors carry `file:line:col` and name the
  unexpected token.
- An IR whose ordering constraints are per-qubit, so passes are written against
  wires rather than against a flat list by accident.
- Passes that are individually testable, run to a fixpoint, and provably
  terminate.
- An equivalence oracle that is sound about *relative* phase.
- Verification wired into the CLI as a gate, not as advice.

**Should**

- OpenQASM 2.0 import/export over a documented subset, so circuits can leave
  and re-enter the tool.
- ASCII and SVG circuit diagrams, because a circuit you cannot see is a circuit
  you cannot debug.
- A standalone `equiv` command exposing the oracle on any two circuits, with a
  counterexample witness and a delta-debugged minimal core when they differ.
- Resource analysis, including T-count — the metric that actually matters in
  fault-tolerant quantum computing.

## The boundary

**Being a useful quantum compiler** is outside it. The simulator caps at 10
qubits and the exact prover at 7. That is not a bug awaiting a fix; it is the
boundary that makes verification-by-simulation possible at all. Past roughly 30
qubits the whole method stops existing, and nothing in this design extends
beyond it.

**Hardware** is outside it: no backends, no device calibration data, no noise
models. So is the dynamic half of the gate set — classical control flow (`if`),
mid-circuit measurement collapse and `reset` are all unbuilt, and neither the
DSL nor the QASM importer supports user-defined gate declarations.

**Measurement semantics** are outside it. `measure` is a marker on a wire. The
simulator compares *pre-measurement* statevectors: no collapse, no sampling, no
shot counts. Every downstream statement inherits that convention, `equiv`'s
verdict included, so the tool prints a note whenever a `measure` is present
rather than handing back an unqualified verdict.

**Performance** is outside it. The IR is a Python list of frozen dataclasses
and the simulator is a list of Python complex numbers; `4ⁿ` work to prove a
7-qubit circuit is accepted without complaint.

**Optimality** is outside it. Both routers are heuristics. The greedy one
minimizes nothing at all, and the SABRE-lite one minimizes a swap-count
heuristic on 2–4 qubit circuits, which the README's own benchmark shows it
sometimes loses at on depth.

And there is no multi-user anything: no server, no database, no accounts, no
network.

## Trust boundary and blast radius

There is no personal data. The tool reads a circuit file and writes a circuit
file; it has no user model, no accounts, no persistence, no telemetry, and it
never opens a socket. Access control and revocation do not apply, because there
is nothing to grant — the process runs with the invoking user's own filesystem
permissions and reads only the paths named on the command line.

The real trust boundary is the input file. `.qf` and `.qasm` source is
untrusted text, and two decisions follow from saying so:

Angle expressions are evaluated by a whitelisted recursive-descent parser over
four operators and the single constant `pi` (`angles.py`). No `eval`, no
`exec`, no name lookup — `__import__('os')` is not even lexable, and a test
asserts it. This is the one place where a lazy implementation would have turned
a circuit file into arbitrary code execution.

SVG output is *generated* through `xml.etree` and never parsed. No untrusted
XML is processed anywhere in the project, so the usual XXE and billion-laughs
class does not arise.

The worst realistic outcome, if all this is wrong, is that the compiler emits a
circuit which is not equivalent to its input and a reader believes a false
claim of correctness. Nobody is harmed and no data leaks. The cost is entirely
to the project's credibility — which is exactly why the honest-limits framing
in the README is treated as a feature rather than as marketing copy to be
softened later.

## What was weighed and set aside

**Building on Qiskit or NumPy.** The parts a dependency would supply — the
simulator, the unitary construction, the transpiler — are precisely the parts
worth writing. Zero runtime dependencies also means the repo still runs
unchanged in five years, which a portfolio artefact benefits from more than it
benefits from speed.

**Symbolic equivalence checking**, via ZX-calculus or a SAT/SMT encoding. A
scope explosion. It would give proofs at sizes simulation cannot reach, but
building a ZX rewriting engine is a larger project than the compiler it would
verify. The honest consequence — proofs only up to 7 qubits — is stated in the
README instead of hidden.

**Dead-code elimination on by default.** Dropping gates on never-measured
qubits preserves measurement statistics but changes the unobserved statevector,
so it fails this project's own equivalence check the moment it removes
anything. Rather than weaken the oracle to accommodate the pass, the pass is
opt-in (`--dce`), runs *after* verification, and prints a warning saying it is
excluded from the guarantee. This is the one place where the guarantee could
have been quietly diluted, and deliberately was not.

**Full SABRE** is deferred rather than rejected. The decay factor and the
multiple reverse-traversal rounds are unimplemented, and the README says which
parts of the paper are present instead of citing it and implying all of it.

**A Greek-mythology project name**, dropped on 2026-08-03. The project was
called *Daedalus*, with a README line about the craftsman who built the
Labyrinth. It described nothing about the software. `QuantumCompiler` says what
the thing is.

Nothing is outstanding: the project is complete at v1.2.0, and the remaining
ideas sit under Roadmap in the README, none of them started.

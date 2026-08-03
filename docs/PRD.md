# PRD — QuantumCompiler

**Status:** built (written retrospectively) · **Date:** 2026-08-03
**Repo:** GreenPandaTech/QuantumCompiler (private) · **Related:** [TDD](TDD.md),
[Design Brief](DESIGN_BRIEF.md)

> Written after the fact, from the shipped code at v1.2.0. It records the
> decisions the code actually embodies, not an idealised plan. Where the
> original reasoning is not recoverable from the code or the CHANGELOG, this
> document says so instead of inventing it.

## Problem

Almost every teaching compiler — and a good number of research ones — *asserts*
that its optimizations preserve meaning. The rewrite rules look obviously
correct on a whiteboard, so nobody checks, and the bugs that do occur are the
subtle ones: a rotation merged with the wrong sign, a gate commuted past a
control it does not commute with, a router whose SWAP insertions permute the
qubits and quietly change the answer. In quantum circuits this is worse than
usual, because the output is a complex amplitude vector that a human cannot
eyeball — a wrong global phase is invisible and harmless, a wrong *relative*
phase is invisible and fatal.

The problem being solved here is not "make quantum circuits smaller". It is:
**learn to build a compiler whose optimizations are checked rather than
claimed**, using a domain where the check is mechanically possible because the
semantics of a circuit is a finite matrix you can compute.

## Who it is for

1. **The author**, as a way to learn compiler construction end to end (lexer,
   recursive-descent parser, IR, pass manager, backend) and quantum-circuit
   semantics at the same time, without leaning on Qiskit to do the interesting
   parts.
2. **A reader of the portfolio** — someone assessing whether the author can
   design a system, state its limits honestly, and prove its claims. The
   audience is technical and sceptical, and will read the code, so overclaiming
   in the README is the failure mode to avoid.

It is **not** for anyone with a quantum circuit they actually need compiled.
Qiskit and t|ket⟩ exist and are better at that in every respect.

## Success looks like

- [x] Every optimization pass is re-verified against the unoptimized circuit by
      an equivalence oracle, and the test suite asserts this per pass, not
      globally. (`tests/test_pass_*.py`, 493 tests total.)
- [x] The oracle has an *exact* mode, not just a sampled one: for circuits up to
      7 qubits it builds both `2ⁿ×2ⁿ` unitaries and compares them, so at least
      some verdicts are genuine proofs. (`unitary.py`, `PROOF_MAX_QUBITS = 7`.)
- [x] The compiler refuses to emit a circuit that fails verification, and exits
      non-zero rather than printing a warning. (Exit code `3`; `cli.py`
      `_run_compile`, `_run_route`, `_run_equiv`.)
- [x] Routing — the part most likely to be silently wrong — is verified up to
      the qubit permutation the SWAPs induce, on every example across all five
      topologies and on random circuits. (`verify.check_routing_equivalence`,
      `tests/test_route.py`.)
- [x] A real algorithm is proven end to end, not just toy identities: the
      3-qubit QFT built from elementary gates equals the analytic 8-point DFT
      matrix up to global phase. (`tests/test_examples.py`.)
- [x] Zero runtime dependencies; the standard library only. Every matrix,
       every complex number, and the SVG writer are hand-rolled.
- [x] The README states what the project is *not* before a reader has to
      discover it.

## Requirements

**Must**

- A DSL with real diagnostics: parse errors carry `file:line:col` and name the
  unexpected token.
- An IR whose ordering constraints are per-qubit, so passes are written against
  wires rather than against a flat list by accident.
- Passes that are individually testable, run to a fixpoint, and provably
  terminate.
- An equivalence oracle that is sound about *relative* phase — the common
  cheap version, allowing a fresh global phase per input, wrongly accepts `z`
  against the identity.
- Verification wired into the CLI as a gate, not as advice.

**Should**

- OpenQASM 2.0 import/export over a documented subset, so circuits can leave
  and re-enter the tool.
- ASCII and SVG circuit diagrams, because a circuit you cannot see is a circuit
  you cannot debug.
- A standalone `equiv` command exposing the oracle on any two circuits, with a
  counterexample witness and a delta-debugged minimal core when they differ.
- Resource analysis, including T-count, the metric that actually matters in
  fault-tolerant quantum computing.

**Won't (this time)**

- Hardware backends, device calibration data, or noise models.
- Classical control flow (`if`), mid-circuit measurement collapse, or
  reset.
- User-defined gate declarations in the DSL or in imported QASM.
- Any claim of optimality from either router.

## Explicitly out of scope

- **Being a useful quantum compiler.** The simulator caps at 10 qubits and the
  exact prover at 7. That is not a bug to be fixed later; it is the boundary
  that makes verification-by-simulation possible at all. Beyond ~30 qubits the
  whole method stops existing, and nothing in this design extends past it.
- **Measurement semantics.** `measure` is a marker on a wire. The simulator
  compares *pre-measurement* statevectors; no collapse, no sampling, no shot
  counts. Every downstream statement — including `equiv`'s verdict — inherits
  that convention, and the tool prints a note saying so whenever a `measure`
  is present rather than handing back an unqualified verdict.
- **Performance.** The IR is a Python list of frozen dataclasses; the simulator
  is a list of Python complex numbers. `4ⁿ` work to prove a 7-qubit circuit is
  accepted without complaint.
- **Optimality.** Both routers are heuristics. The greedy one minimizes nothing
  at all; the SABRE-lite one minimizes a swap-count heuristic on 2–4 qubit
  circuits, which the README's benchmark shows it sometimes loses at on depth.
- **Multi-user anything.** No server, no database, no accounts, no network.

## Safety and privacy

Most of this template's questions do not apply, and padding them would obscure
the two answers that do.

- **Personal data:** none. The tool reads a circuit file and writes a circuit
  file. It has no user model, no accounts, no persistence, no telemetry, and it
  never opens a socket.
- **Access control / revocation:** not applicable. There is nothing to grant
  and nothing to revoke — the process runs with the invoking user's own
  filesystem permissions and reads only paths given on the command line.
- **The real trust boundary** is the input file: `.qf` and `.qasm` source is
  untrusted text. Two decisions follow, and both are enforced in code:
  - Angle expressions are evaluated by a whitelisted recursive-descent parser
    over four operators and the single constant `pi` (`angles.py`). There is no
    `eval`, no `exec`, no name lookup — `__import__('os')` is not lexable, and
    a test asserts it. This is the one place where a lazy implementation would
    have turned a circuit file into arbitrary code execution.
  - SVG output is *generated* through `xml.etree`, never parsed. No untrusted
    XML is processed anywhere in the project, so the usual XXE/billion-laughs
    class does not arise.
- **Worst realistic outcome if it is wrong:** the compiler emits a circuit that
  is not equivalent to its input and a reader believes a false claim of
  correctness. Nobody is harmed and no data leaks; the cost is entirely to the
  project's credibility, which is why the honest-limits framing in the README
  is treated as a feature and not as marketing copy to be softened.

## Open questions

None outstanding. The project is complete at v1.2.0; the remaining ideas are
listed under Roadmap in the README and none is started.

## Not doing / rejected alternatives

- **Build on Qiskit / NumPy.** Rejected. The parts a dependency would supply —
  the simulator, the unitary construction, the transpiler — are precisely the
  parts worth writing. Zero runtime dependencies also means the repo still runs
  unchanged in five years, which a portfolio artefact benefits from more than
  it benefits from speed.
- **Symbolic equivalence checking (ZX-calculus, or a SAT/SMT encoding).**
  Rejected as a scope explosion. It would give proofs at sizes simulation
  cannot reach, but building a ZX rewriting engine is a larger project than
  the compiler it would be verifying. The honest consequence — proofs only up
  to 7 qubits — is stated in the README rather than hidden.
- **A fresh global phase per input in the equivalence check.** Rejected as
  *unsound*, and this is the sharpest design decision in the project. Allowing
  each input its own phase accepts `z` as equivalent to the identity, because
  every computational basis state is an eigenvector. The oracle therefore fixes
  one phase from the first input and requires every subsequent input to agree
  under *that* phase, with seeded random (non-basis) states included to catch
  exactly this case (`verify.py` module docstring).
- **Dead-code elimination on by default.** Rejected. Dropping gates on
  never-measured qubits preserves measurement statistics but changes the
  unobserved statevector, so it fails the project's own equivalence check the
  moment it removes anything. Rather than weaken the oracle to accommodate it,
  the pass is opt-in (`--dce`), runs *after* verification, and prints a warning
  saying it is excluded from the guarantee. This is the one place where the
  guarantee could have been quietly diluted, and it deliberately was not.
- **Full SABRE.** Deferred, not rejected: the decay factor and multiple
  reverse-traversal rounds are unimplemented, and the README says which parts
  of the paper are and are not present rather than citing it and implying all
  of it.
- **A Greek-mythology project name.** Dropped 2026-08-03. The project was
  called *Daedalus*, with a README line about the craftsman who built the
  Labyrinth. It described nothing about the software. `QuantumCompiler` says
  what the thing is.

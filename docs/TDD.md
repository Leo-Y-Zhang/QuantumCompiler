# TDD — QuantumCompiler

**Status:** built (written retrospectively from the v1.2.0 code) ·
**Date:** 2026-08-03 · **PRD:** [PRD.md](PRD.md) ·
**Repo:** GreenPandaTech/QuantumCompiler

> Derived by reading `src/quantum_compiler/`, not the README. Where the two
> disagree, this document follows the code and the README is corrected in the
> same commit.

## Approach

A single-process, dependency-free Python package with the shape of a real
compiler: `lexer → recursive-descent parser → IR → pass manager → backend`.
The distinctive part is not the pipeline but the oracle bolted across it. A
*statevector simulator* built on plain Python `complex` lists gives the IR a
computable denotation, and everything that rewrites a circuit is required to
prove it did not change that denotation — the optimizer, the router, and, via
the `equiv` subcommand, any two circuits a user hands in. Verification is a
gate, not a report: when a check fails the CLI emits nothing and exits `3`.

There is no server, no database, no persistent state and no network access.
The whole system is "argv and stdin/stdout plus files named on the command
line", which is why several sections of the standard template collapse to a
single honest sentence below rather than being padded out.

## Data model

No database. The entire model is two frozen/plain dataclasses in `ir.py`:

| Type | Field | Type | Meaning / constraints |
|---|---|---|---|
| `Gate` (frozen) | `name` | `str` | one of `h x y z s sdg t tdg rx ry rz cx cz swap measure barrier` |
| | `qubits` | `tuple[int, ...]` | operands, ordered; for `cx` this is `(control, target)` |
| | `angle` | `float \| None` | set **only** for `rx`/`ry`/`rz`; `None` everywhere else |
| | `bit` | `int \| None` | set **only** for `measure` |
| `Circuit` | `num_qubits` | `int` | register size |
| | `num_bits` | `int` | classical register size; `0` is legal |
| | `gates` | `list[Gate]` | program order |

Two invariants carry the design:

1. **The flat gate list is one topological order of a DAG, not the semantics.**
   Two gates must keep their relative order iff they share a qubit; gates on
   disjoint qubits commute trivially as tensor factors. Passes are therefore
   written against `Circuit.qubit_wires()` (per qubit, the indices of the gates
   touching it, in order) rather than against list adjacency. This is what makes
   `commute-cancel` and the router's dependency front layer expressible at all.
2. **`Circuit` is rewritten by replacement, never mutated.** `replace_gates`
   returns a new `Circuit` with the same registers. `Gate` is frozen, so a pass
   physically cannot corrupt the input it is being compared against — which
   matters, because the input is the reference the oracle checks against.

`measure` and `barrier` participate as ordinary order-blocking nodes on their
wires and are skipped by the simulator. There is no classical value model: a
measure records *which* classical bit it targets and nothing more.

## Interfaces

### Public Python API (`quantum_compiler.__all__`, 24 names)

The contract-bearing ones:

```python
parse(source: str) -> Circuit                # raises LexError / ParseError
parse_qasm(source: str) -> Circuit           # documented subset only
emit_qasm(circuit: Circuit) -> str
simulate(circuit: Circuit, initial: list[complex] | None = None) -> list[complex]
circuit_unitary(circuit: Circuit) -> list[list[complex]]    # ValueError above 7 qubits
prove_equivalence(a, b, *, num_random=4, seed=..., atol=1e-9) -> ProofResult
check_equivalence(a, b, ...) -> EquivalenceResult
check_routing_equivalence(original, routed, final_layout, *, initial_layout=None, ...)
route(circuit: Circuit, coupling: CouplingMap, strategy="greedy") -> RoutingResult
find_witness(a, b, ...) -> Witness | None
shrink_counterexample(a, b, ...) -> ShrinkResult
analyze(circuit: Circuit) -> CircuitMetrics
to_dot(circuit: Circuit) -> str
```

Contracts worth stating explicitly, because they are the ones a caller can get
wrong:

- **`prove_equivalence` is the oracle.** It dispatches: at ≤ 7 qubits
  (`PROOF_MAX_QUBITS`) it materialises both `2ⁿ×2ⁿ` unitaries and returns
  `method="exact-unitary"` with an aligned Frobenius difference norm and a
  process fidelity — a genuine up-to-global-phase proof. Above that it falls
  back to `check_equivalence` and returns `method="randomized"`. The caller is
  expected to surface which one it got; `ProofResult.summary()` does, and the
  randomized branch says "circuit too large for an exact unitary proof" in the
  line it prints.
- **The verdict is up to *global* phase only, and one phase for all inputs.**
  `check_equivalence` fixes the phase from the largest-magnitude amplitude of
  the *first* input and requires every later input to agree under that same
  phase. A per-input phase would accept `z` as equal to the identity (every
  basis state is an eigenvector); the seeded random states exist to close that
  hole. Anyone loosening this loosens the project's only real claim.
- **The randomized battery is exhaustive only to 3 qubits.** `_test_inputs`
  returns *all* `2ⁿ` basis states for `n ≤ 3`, plus 4 seeded random states.
  For `n ≥ 4` it returns only `{|0…0⟩, |1…1⟩, the n weight-one states}` plus the
  4 random states. So at `n ≤ 3` agreement under one shared phase settles the
  question; at `n ≥ 4` it is strong evidence, not proof — which is why
  `prove_equivalence` prefers the unitary path up to 7 qubits.
- **`check_routing_equivalence` needs both layouts.** `final_layout[l]` is the
  physical qubit carrying logical `l` at the end; `initial_layout` says where it
  started, and `None` means the trivial layout. The greedy router always starts
  trivially so it may omit it; **the sabre router chooses its own initial
  placement and must pass it**. Omitting it for a sabre result silently
  compares the wrong thing — the routers return `RoutingResult.initial_layout`
  precisely so callers do not have to remember which is which.
- **`route` raises**, it does not return a failure value: `ValueError` when the
  circuit needs more qubits than the coupling map has, or on an unknown
  strategy name.
- **Parsers do not know the filename.** `parse`/`parse_qasm` take source text
  only; `LexError`/`ParseError` carry 1-based `line`/`column`, and the caller
  supplies the path via `exc.format(path)` to get the gcc-style
  `file:line:col: error: …`. Any other front end must do the same or its
  diagnostics will read `<input>`.

### CLI (`quantum-compiler`, also `python -m quantum_compiler`)

```
quantum-compiler compile FILE [--opt] [--emit ir|ascii|svg|qasm|dot] [--verify] [--proof] [--dce] [--out FILE]
quantum-compiler route   FILE --coupling line|ring|full[:N]|grid:RxC [--strategy greedy|sabre] [--emit …] [--verify] [--out FILE]
quantum-compiler equiv   FILE_A FILE_B [--no-shrink] [--json]
quantum-compiler analyze FILE [--json]
quantum-compiler stats   FILE [--dce]
```

`.qasm` inputs are parsed as OpenQASM 2.0; anything else as the DSL. Diagnostics
and verification lines go to **stderr**, the emitted artefact to **stdout** (or
`--out`), so `compile … --emit qasm > out.qasm` is safe.

**Exit codes are the API.** `0` success · `1` I/O error (unreadable file, or a
non-UTF-8 file — `UnicodeDecodeError` is caught alongside `OSError` so a binary
input reports cleanly instead of raising) · `2` usage or syntax error, with
`file:line:col` · `3` **verification failed** — `--verify`/`--proof` rejected a
circuit, or `equiv` proved the pair inequivalent.

### The one deliberate ordering decision in the CLI

In `_run_compile` the order is: optimize → verify → **then** dead-code
elimination. `--dce` requires `--opt` (else exit `2`), runs after the oracle has
passed, and prints a warning when combined with `--verify`/`--proof` saying it
"is excluded from the equivalence guarantee". This is because DCE is genuinely
*not* statevector-preserving: it preserves measurement statistics on measured
qubits but changes the unobserved state, so it fails the project's own check
whenever it removes anything. The alternative — weakening the oracle to a
measured-qubits-only comparison so DCE could run inside the guarantee — was
rejected; see the PRD.

## Access control

**Not applicable, and stating that precisely is the point.** There is no
server, no database, no RLS, no authentication, no security-definer function,
no `anon`/`public` grant, and no network I/O anywhere in the package (no
`socket`, `urllib`, `requests`, or `subprocess` import in `src/`). The process
runs as the invoking user and touches only the paths given on the command line
plus `--out`.

The single trust boundary is **input text**, and it is defended in two places:

| Boundary | Threat | Control |
|---|---|---|
| `.qf` / `.qasm` angle expressions | arbitrary code execution via `eval` | `angles.py` is a recursive-descent parser over `NUMBER`, `pi`, `+ - * /`, unary sign and parentheses. No `eval`/`exec`, no identifier lookup. `__import__('os')` is not even lexable; `tests/test_angles.py::test_no_eval_of_python` asserts it. |
| SVG output | XXE / entity expansion | the SVG tree is **generated** with `xml.etree.ElementTree`, never parsed. No untrusted XML enters the process. |

Resource exhaustion is bounded rather than unbounded: `simulate` raises above
`MAX_QUBITS = 10` and `circuit_unitary` above `PROOF_MAX_QUBITS = 7`, so a
hostile input file cannot ask for a `2⁶⁴` allocation. It *can* still ask for a
10-qubit circuit with a million gates and be slow; that is accepted for a local
developer tool.

## Migrations

None. No database, no persisted schema, no on-disk format the project owns
across versions. `.qf` and OpenQASM 2.0 are the only file formats, both are
read-only inputs or freshly written outputs, and neither has ever changed
shape.

## Failure modes

| What breaks | Who notices | How we detect it | How we undo it |
|---|---|---|---|
| A pass changes circuit semantics | the user, at `--verify`/`--proof` | the oracle: exact unitary ≤ 7 qubits, sampled battery above | **the compiler refuses to emit** and exits `3`; nothing wrong is written. The per-pass tests in `tests/test_pass_*.py` catch it before release |
| Routing permutes qubits wrongly | same | `check_routing_equivalence` with both layouts | exit `3`, nothing emitted |
| Sabre layout passed to the oracle without `initial_layout` | nobody — it silently compares the wrong pair | not detectable at runtime; only by reading the call site | the routers return `initial_layout` in `RoutingResult`; `tests/test_route.py` exercises both strategies on all five topologies |
| Pass manager fails to reach a fixpoint | the user, as a crash | `max_iterations = 1000` defensive bound | `RuntimeError("pass manager failed to reach a fixpoint")`. Termination is argued in the module docstring by a lexicographic measure `(len(gates), #special-angle rotations)`; the bound exists in case that argument is wrong |
| Circuit too large to simulate | the user | `simulate` / `circuit_unitary` size checks | `ValueError` naming the cap (10 / 7 qubits) |
| Circuit needs more qubits than the coupling map | the user | `route` precondition | `ValueError` naming both counts |
| Unparseable source | the user | lexer/parser | `file:line:col: error: …` on stderr, exit `2` |
| Binary or non-UTF-8 input file | the user | `_read_source` catches `UnicodeDecodeError` with `OSError` | one clean message, exit `1`, no traceback |
| Two circuits genuinely inequivalent under `equiv` | the user | the oracle | exit `3`, plus a counterexample witness and a ddmin-shrunk 1-minimal pair explaining *why* |

There is no monitoring and no alerting, because there is no deployment: the
only detector is CI (`pytest`, `ruff check .`, `mypy src` strict, gitleaks, all
with 15-minute timeouts) and the user's own exit code.

## Rollback

Nothing this project does is irreversible. It writes exactly one artefact, to
stdout or to `--out`, and only after every requested check has passed.

- **A bad release:** `git revert` and `pip install -e ".[dev]"`. There is no
  state to migrate back, no cache to invalidate, no client to be out of step.
- **A bad emitted circuit:** the input file is untouched; delete the output.
- **The 2026-08-03 rename**, the only change with a blast radius beyond this
  repo: it is a pure rename of the distribution, the import package, the
  console script and one exception class. Undoing it is `git revert` of that
  commit plus a reinstall. The one non-obvious consequence — and the reason the
  CHANGELOG says it in bold — is that an **existing editable install keeps
  pointing at `src/daedalus`, which no longer exists**, so every import fails
  until `pip install -e ".[dev]"` is re-run. That is the whole cost, and it is
  local to each checkout.

## Test plan

493 tests, `pytest -q`, ~2s. The structure that matters:

- **Positive, per pass.** Each `tests/test_pass_*.py` applies exactly one pass
  and re-verifies the result against the input with the oracle. A pass is not
  tested by "the whole pipeline still works".
- **Negative, per pass.** Each pass is tested to be *blocked by a `barrier`* —
  the fence has to hold for every rewrite, not on average
  (`tests/test_barrier.py`).
- **Boundary — the two oracles must agree.**
  `tests/test_unitary.py::TestProveCircuitEquivalence::test_agrees_with_randomized_oracle`
  runs both methods over the same circuits, correct and corrupted, and requires
  the same verdict. That agreement is what makes the randomized fallback at 8+
  qubits worth trusting; `tests/test_verify.py` separately pins the dispatch
  (`method == "exact-unitary"` below the cap, `"randomized"` above it).
- **Boundary — a real algorithm.** `tests/test_examples.py` builds the 3-qubit
  QFT's unitary from elementary gates and proves it equals the analytic 8-point
  DFT matrix up to global phase. This is the test that would catch a plausible
  but wrong rotation convention, which no amount of self-consistency testing
  would.
- **Property, not fixture, for the shrinker.** The ddmin tests assert
  *1-minimality* — the shrunk pair still disagrees, and removing any single
  remaining gate makes it agree — rather than hardcoding an expected gate list.
  A hardcoded list would have to be rewritten every time the search order
  changed, and would stop testing the property.
- **Round-trip.** Every example, original and optimized, goes out to QASM, comes
  back, and is re-proven equivalent.
- **CLI end to end**, including a real subprocess run of `python -m
  quantum_compiler` and the exit codes.

## Build order (as executed)

The `docs/superpowers/specs/to-the-max.md` spec, Steps 0–8, all complete
(2026-07-09), then v1.1.0 sabre routing (2026-07-30) and v1.2.0 `equiv`
(2026-07-31). See `SESSION_HANDOFF.md`.

## Open questions

None. The Roadmap items in the README (full SABRE decay factor and multiple
reverse-traversal rounds, directed coupling maps, controlled-phase fusion) are
unstarted ideas, not open design questions — each has an obvious place to go in
`route.py` and `passes/`.

---

## Documents deliberately not written

**App Flow — not applicable.** The template describes screens, states,
transitions, unauthorised access and offline behaviour. This is a
non-interactive, single-shot CLI: it reads argv, reads a file, writes one
artefact, and exits. There are no screens, no sessions, no persistence, no
partial states to resume, and nothing to be signed out of. The complete
"transition model" is the exit-code table above, which belongs here. Writing an
App Flow document for it would mean inventing states the program does not have.

**Design Brief — written**, but scoped tightly: see
[DESIGN_BRIEF.md](DESIGN_BRIEF.md). The project has one genuine visual surface
(the ASCII and SVG circuit diagrams), and the notation choices in it are real
design decisions with real consequences for whether the output is readable.

# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **Project renamed `Daedalus` → `QuantumCompiler`** (2026-08-03). No compiler
  behaviour changed; only names did. The mapping:

  | was | is |
  |---|---|
  | GitHub repo `Leo-Y-Zhang/Daedalus` | `Leo-Y-Zhang/QuantumCompiler` |
  | distribution name `daedalus` | `quantum-compiler` |
  | import package `daedalus` | `quantum_compiler` |
  | console script `daedalus …` | `quantum-compiler …` |
  | `python -m daedalus` | `python -m quantum_compiler` |
  | exception base `DaedalusError` | `QuantumCompilerError` |

  **Existing checkouts must re-run `pip install -e ".[dev]"`.** The old editable
  install points at `src/daedalus`, which no longer exists, so every import
  fails until it is reinstalled.

  The release entries below are left exactly as they were written at the time,
  so they still say `daedalus`. Read them through the table above.

### Added

- `docs/PRD.md` and `docs/TDD.md`: retrospective product and technical design
  documents derived from the shipped code.

## [1.2.0] - 2026-07-31

The "equiv" release: the equivalence oracle becomes a standalone two-circuit
prover with counterexample witnesses and delta-debugged minimal cores.
456 -> 493 tests.

### Added

- **`daedalus equiv FILE_A FILE_B`** (`--no-shrink`, `--json`): proves two
  circuits equivalent up to global phase using the same oracle that certifies
  the optimizer and the router (exact unitary up to 7 qubits, randomized
  battery above). On failure it emits a **counterexample witness** — the first
  battery input where the circuits disagree, with the worst amplitude rows
  showing both the phase-aligned error `|B - phase*A|` and the raw `|B - A|`
  difference — and a **ddmin delta-debug shrink** (Zeller & Hildebrandt 2002)
  over the union of both gate lists down to a **1-minimal** core: removing any
  single remaining gate makes the pair equivalent (the tests assert that
  property, not a hardcoded outcome). Exit code 3 on proven non-equivalence,
  matching `--verify`/`--proof`.
- Public API: `find_witness`, `shrink_counterexample`, `Witness`,
  `ShrinkResult`, exported from `daedalus`.
- **Measurement caveat surfaced**: `equiv` compares pre-measurement
  statevectors (the simulator's documented semantics), so when either input
  contains a `measure` gate the report prints an explicit note and the JSON
  gains `"measure_ignored": true`. Circuits that differ only in *what they
  measure* are equivalent under this convention — the output now says so
  instead of handing back an unqualified verdict.
- Deterministic witness phase anchoring: the shared alignment phase anchors on
  the lowest amplitude index within `1e-9` of the first input's peak
  magnitude, so near-ties (e.g. the two `1/sqrt(2)` amplitudes of a GHZ state)
  cannot let platform rounding decide which rows the witness displays.
- Witness rows always include at least one visibly differing amplitude pair:
  the row with the largest raw `|B - A|` is appended whenever the top
  aligned-error rows would all show identical-looking amplitudes (a pure
  relative-phase disagreement).

### Fixed

- Non-UTF-8 input files now produce the clean one-line `error: cannot read`
  message and exit code 1 in every subcommand; previously a
  `UnicodeDecodeError` traceback escaped because only `OSError` was caught.
- The "no witness found" report no longer blames unsampled inputs
  unconditionally. Near the tolerance boundary (within about a `2**(n/2)`
  factor of `atol`) the exact engine's accumulated Frobenius norm can cross
  `atol` while no single amplitude of any battery input does — demonstrated at
  2 qubits by `rz(9.5e-10)` vs identity, where every basis state *is* sampled.
  The message and the `find_witness` docstring now state both causes and defer
  to the proof verdict.
- A degenerate alignment factor (e.g. `B` vanishes at the anchor where `A`
  peaks, making the ratio 0) is now labelled with its magnitude and the note
  that it is not a pure phase, instead of printing `shared phase
  +0.000000+0.000000j` without comment.

## [1.1.0] - 2026-07-30

The "sabre" release: a second, smarter routing strategy — still proven correct
on every circuit it routes. 398 -> 456 tests.

### Added

- **SABRE-lite routing strategy** (`route(..., strategy="sabre")`, CLI
  `route --strategy greedy|sabre`; greedy remains the default with byte-for-byte
  identical output): front layer of the dependency DAG, candidate SWAPs scored
  by summed BFS distance of the front layer plus a weighted lookahead window,
  and reverse-traversal initial-layout selection (one forward + one backward
  pass), after Li, Ding & Xie 2019. Deliberately *lite*: no decay factor, a
  single reverse-traversal round. Fully deterministic (fixed tie-break
  orderings, no randomness) with a greedy shortest-path fallback on stalls so
  routing always terminates. Every sabre-routed circuit is proven equivalent by
  the routing oracle; the test suite proves all example circuits on all five
  topologies.
- `check_routing_equivalence` accepts an optional `initial_layout` so the
  oracle can verify routers that choose a non-trivial starting placement
  (default stays the trivial layout — the greedy path is unchanged).
- `RoutingResult.initial_layout`: where each logical qubit starts (trivial for
  greedy; note this is a new second positional field).
- **Routing benchmark** (`bench.py`, `python -m daedalus.bench`): Markdown
  table of swaps added and depth delta, sabre vs greedy, over the committed
  examples on the five test topologies; the README table is its verbatim
  output, including the cases where sabre is not better.

### Fixed

- CHANGELOG 1.0.0 entry said "251 -> 395 tests"; the shipped 1.0.0 suite was
  398 tests.

## [1.0.0] - 2026-07-09

The "verified compiler" release: from a verified-rewrite demo to a small but
genuine optimizing quantum compiler where the optimizer, an exact proof engine,
and a router are each proven correct. 251 -> 398 tests.

### Added

- **Exact unitary proof engine** (`unitary.py`, `--proof`): builds the full
  `2**n` circuit unitary from the simulator and compares two circuits exactly up
  to global phase (Frobenius difference norm + process fidelity), a genuine
  proof for small circuits. `verify.prove_equivalence` picks the exact engine
  when small enough, else the randomized oracle. Implements the README `--proof`
  roadmap item.
- **Verified SWAP-insertion router** (`route.py`, `topology.py`, `route` CLI):
  coupling maps (`line`/`ring`/`grid`/`full`/custom) with BFS routing;
  `verify.check_routing_equivalence` proves the routed circuit equals the
  original up to the induced qubit permutation, exact for small circuits and
  checked on random circuits across five topologies.
- **New optimization passes** (all proven): `canonicalize-rotations`
  (special-angle rotations -> named Clifford+T), `control-flip`
  (`h h cx h h -> cx` reversed), and an x-basis rule for `commute-cancel`
  (`x`/`rx` through cx targets).
- **`barrier`** optimization fence in the DSL and OpenQASM subset (parsed, drawn,
  emitted, round-tripped); every pass is tested to respect it.
- **Resource analysis** (`analyze.py`, `analyze` CLI, `--json`): depth, gate
  histogram, two-qubit count, T-count; a depth line in `stats`; `--emit dot`
  Graphviz export of the dependency DAG.
- Examples: `qft3.qf` (a 3-qubit QFT proven to equal the DFT matrix),
  `routed_line.qf` (routing demo), `clifford_t.qf` (canonicalization demo).
- `ruff` + `mypy --strict` dev gate and a CI lint job.
- Peephole pass: additional Hadamard-conjugation identities `h y h -> y` and the
  basis-change rotation rewrites `h rz(a) h -> rx(a)`, `h rx(a) h -> rz(a)`,
  `h ry(a) h -> ry(-a)`.
- gitleaks secret-scanning job in CI (gitleaks/gitleaks-action@v2).

## [0.2.0] - 2026-07-07

### Added

- OpenQASM 2.0 emitter (`daedalus.emit_qasm`, CLI `--emit qasm`): qelib1
  gate names, `q`/`c` registers, angles as plain floats.
- OpenQASM 2.0 importer (`daedalus.parse_qasm`) for a documented subset:
  single qreg + optional single creg (any names), the qelib1 gates
  h x y z s sdg t tdg rx ry rz cx cz swap, indexed operands only,
  `measure q[i] -> c[j]`, pi-arithmetic angle expressions, `//` comments.
  Unsupported constructs (user-defined gates, `if`, `barrier`, `opaque`,
  `reset`, `U`/`CX` builtins, whole-register operands, multiple registers)
  are rejected with precise line:column diagnostics.
- CLI: files ending in `.qasm` are auto-parsed as OpenQASM 2.0 for both
  `compile` and `stats`.
- Tests: exact emitter output, structural + statevector-equivalence
  roundtrips for all example programs (original and optimized), importer
  error positions, and CLI end-to-end QASM-in/QASM-out (54 new tests,
  244 total).

## [0.1.0] - 2026-07-06

### Added

- Line-based quantum-circuit DSL: `qubits`/`bits` declarations, 15 gates
  (h, x, y, z, s, sdg, t, tdg, rx, ry, rz, cx, cz, swap, measure).
- Safe angle-expression evaluator with `pi` arithmetic (no `eval`).
- Hand-written lexer and recursive-descent parser with line/column error
  positions.
- Gate-list IR with per-qubit wire ordering (implicit dependency DAG).
- Pass manager that runs passes to fixpoint and records per-pass statistics.
- Optimization passes: adjacent inverse-pair cancellation, rotation merging,
  peephole identities (h x h -> z, h z h -> x), commutation-aware
  cancellation across cx controls, and opt-in dead-code elimination.
- Pure-stdlib statevector simulator (up to 10 qubits) and an equivalence
  checker (up to global phase) used for semantic verification of every pass.
- ASCII circuit diagrams and dependency-free SVG rendering.
- `daedalus` CLI (`compile`, `stats`) with `--opt`, `--emit ir|ascii|svg`,
  `--verify`, `--dce`, `--out`, plus `python -m daedalus`.
- Example programs with before/after SVG renderings.

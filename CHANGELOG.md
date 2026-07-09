# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-07-09

The "verified compiler" release: from a verified-rewrite demo to a small but
genuine optimizing quantum compiler where the optimizer, an exact proof engine,
and a router are each proven correct. 251 -> 395 tests.

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

# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Peephole pass: additional Hadamard-conjugation identities `h y h -> y`
  (equal up to global phase) and the basis-change rotation rewrites
  `h rz(a) h -> rx(a)`, `h rx(a) h -> rz(a)`, `h ry(a) h -> ry(-a)`,
  completing the family alongside the existing `h x h -> z` / `h z h -> x`.
  Each is proven semantics-preserving by the statevector equivalence checker
  (7 new tests, 251 total).
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

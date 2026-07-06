# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
- `qforge` CLI (`compile`, `stats`) with `--opt`, `--emit ir|ascii|svg`,
  `--verify`, `--dce`, `--out`, plus `python -m qforge`.
- Example programs with before/after SVG renderings.

# QForge

**A toy educational quantum-circuit compiler with *verified* optimization
passes. Pure Python stdlib — zero runtime dependencies.**

QForge compiles a small quantum-circuit DSL through a real compiler pipeline
(lexer -> recursive-descent parser -> IR -> pass manager) and then *proves*
its optimizations did not change the circuit's meaning, using a built-in
statevector simulator and an up-to-global-phase equivalence check.

> **Honest framing:** this is a toy compiler for learning and portfolio
> purposes. It demonstrates genuine compiler architecture and genuinely
> verified rewrites, but it is not a production quantum compiler (no
> hardware backends, no routing, no noise models — see Limitations).

## Why it is interesting

Most toy compilers *claim* their optimizations are correct. QForge checks:
every optimized circuit is re-simulated against the original on a set of
deterministic basis states and seeded pseudo-random inputs, and must match
up to global phase. The test suite uses the same machinery to prove each
pass is semantics-preserving.

```
$ qforge compile examples/rotations.qf --opt --emit ascii --verify
verify: equivalent up to global phase (max error 2.483e-16, 8 inputs)
BEFORE:
q0: -[RZ(pi/4)]--[RZ(pi/4)]---o---[RZ(-pi/2)]-----------------------
                              |
q1: -------------------------(+)--[RX(pi/2)]---[RX(-pi/2)]--[M->c0]-

AFTER:
q0: --o-----------
      |
q1: -(+)--[M->c0]-

gates: 7 -> 2
```

Seven gates collapse to two: the adjacent `rz(pi/4)` pair merges to
`rz(pi/2)`, which *commutes through the cx control* and cancels against
`rz(-pi/2)`; the `rx` pair merges to `rx(0)` and evaporates.

## The DSL

```
# Bell pair with a redundant x x pair the optimizer removes.
qubits 2
bits 2
h q0
x q1
x q1
cx q0, q1
measure q0 -> c0
measure q1 -> c1
```

Gates: `h x y z s sdg t tdg rx(a) ry(a) rz(a) cx cz swap measure`.
Angles support pi arithmetic (`pi/4`, `-pi/2`, `2*pi`) via a tiny safe
expression evaluator — no `eval`. Parse errors carry line and column:

```
bad.qf:2:1: error: unknown gate 'foo'
```

## Optimization passes

| pass | what it does |
|---|---|
| `cancel-inverses` | removes adjacent self-inverse pairs (`h h`, `x x`, `cx cx`, `s sdg`, `t tdg`, ...) |
| `merge-rotations` | fuses adjacent same-axis rotations, drops angles that are 0 mod 2pi |
| `peephole` | algebraic identities: `h x h -> z`, `h z h -> x` |
| `commute-cancel` | commutes z-diagonal gates through cx controls to expose cancellations |
| `dead-code` | *(off by default, `--dce`)* drops gates on never-measured qubits; documented as observably unsafe if you inspect the full state |

The pass manager runs passes to a fixpoint and reports per-pass statistics:

```
$ qforge stats examples/bell.qf
pass               iter  before  after  removed
cancel-inverses       1       6      4        2
merge-rotations       1       4      4        0
...
total: 6 -> 4 gates (33.3% reduction)
```

## Install & run

Requires Python 3.10+ (developed on 3.13). Zero runtime dependencies;
`pytest` is the only dev dependency.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
# .venv/bin/python -m pip install -e ".[dev]"          # Linux/macOS

.venv/Scripts/python.exe -m pytest -q                  # 190 tests
```

CLI (also runnable as `python -m qforge`):

```
qforge compile FILE [--opt] [--emit ir|ascii|svg] [--verify] [--dce] [--out FILE]
qforge stats FILE
```

Exit codes: `0` success (and verification passed), `1` compile/verify
failure, `2` usage errors.

SVG diagrams (committed under `examples/`, regenerable with
`qforge compile examples/bell.qf --opt --emit svg --out ...`):

| before | after `--opt` |
|---|---|
| ![bell before](examples/bell.before.svg) | ![bell after](examples/bell.after.svg) |
| ![rotations before](examples/rotations.before.svg) | ![rotations after](examples/rotations.after.svg) |

## Architecture

```
src/qforge/
  lexer.py       tokenizer with line/column tracking
  parser.py      recursive-descent parser -> Circuit IR
  angles.py      safe pi-arithmetic expression evaluator (no eval)
  ir.py          Circuit/Gate IR; per-qubit dependency chains (a DAG
                 linearized in program order)
  passes/        one module per optimization pass + the fixpoint manager
  sim.py         pure-stdlib statevector simulator (complex lists, <=10 qubits)
  verify.py      up-to-global-phase equivalence checker (basis + seeded
                 pseudo-random inputs)
  draw_ascii.py  aligned-column ASCII circuit diagrams
  draw_svg.py    hand-rolled SVG writer (no deps)
  cli.py         argparse CLI
tests/           190 pytest tests: parser errors by position, every pass,
                 hand-computed amplitudes (Bell/GHZ), equivalence checker
                 positive AND negative cases, SVG well-formedness, CLI e2e
```

Why the IR is "effectively a DAG": gates are stored in program order, but
each gate only constrains gates that share a qubit; per-qubit chains are the
DAG edges, and passes exploit commutation within them.

## Safety & privacy

Runs fully offline; no network, no telemetry. The angle evaluator is a
whitelisted mini-parser, not `eval`. All examples are synthetic.

## Limitations

- Statevector simulation is exponential; the simulator refuses >10 qubits.
- Measurement is modelled as a marker, not a collapse: the simulator
  compares *pre-measurement* statevectors and passes never move or alter
  `measure` gates. There is no classical control flow.
- Verification samples inputs (8 per check) — overwhelming evidence, not a
  formal proof.
- No hardware backends, transpilation targets, routing, or noise models.
- The commutation pass only handles z-diagonal gates through cx controls —
  intentionally the simplest genuinely useful case.

## Roadmap

- QASM 2.0 import/export.
- Controlled-phase fusion and a T-count report.
- A `--proof` mode emitting the unitary difference norm for small circuits.
- Gate-count-vs-depth pareto stats.

## License

MIT. Copyright (c) 2026 GreenPandaTech. See `LICENSE`.

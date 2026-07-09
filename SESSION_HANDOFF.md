# Session handoff — Daedalus "to the max" (v1.0.0)

Program: repo max-upgrades #3 (after Hephaestus, Helios). Spec:
`docs/superpowers/specs/to-the-max.md` (self-approved). Branch:
`feature/to-the-max`. Baseline v0.2.0 = 251 tests green.

## Build order (spec steps) — status
- [x] Step 0 — Tooling gate: ruff + mypy + CI lint job
- [x] Step 1 — Exact unitary proof engine (`unitary.py`, `--proof`)
- [x] Step 2 — New verified passes (canonicalize-rotations, commute x-basis, control-flip)
- [x] Step 3 — Topology + verified routing (crown jewel) + route CLI
- [x] Step 4 — Resource analysis + DAG export (analyze.py, dot.py, --emit dot, `analyze`)
- [x] Step 5 — `barrier` optimization fence (parse/dump/sim/draw/qasm + all passes respect it)
- [x] Step 6 — Showcase / examples / README overhaul + CHANGELOG + version 1.0.0
- [x] Step 7 — Adversarial 3-lens review (Workflow): 3 findings, all confirmed + fixed
- [ ] Step 8 — merge --no-ff to main, tag v1.0.0, push, CI green

Tests: 251 baseline -> 398 now. Default pipeline order: cancel-inverses,
merge-rotations, peephole, control-flip, commute-cancel, canonicalize-rotations.
New modules: unitary.py, topology.py, route.py, analyze.py, dot.py.
CLI subcommands: compile, stats, route, analyze. barrier is a fence gate.
Review fixes: router now preserves multi-qubit barriers; +DCE/route barrier tests.

## Exact next step
Step 8: merge --no-ff to main, tag v1.0.0, push, confirm CI green.

## Verify commands
```
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src
```

## Rules
Commit identity GreenPandaTech noreply only; repo stays PRIVATE. Push after every
green increment. Keep every optimization pass semantics-preserving (proven).

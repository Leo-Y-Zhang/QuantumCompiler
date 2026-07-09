# Session handoff — Daedalus "to the max" (v1.0.0)

Program: repo max-upgrades #3 (after Hephaestus, Helios). Spec:
`docs/superpowers/specs/to-the-max.md` (self-approved). Branch:
`feature/to-the-max`. Baseline v0.2.0 = 251 tests green.

## Build order (spec steps) — status
- [x] Step 0 — Tooling gate: ruff + mypy + CI lint job
- [x] Step 1 — Exact unitary proof engine (`unitary.py`, `--proof`)
- [x] Step 2 — New verified passes (canonicalize-rotations, commute x-basis, control-flip)
- [ ] Step 3 — Topology + verified routing (crown jewel)
- [ ] Step 4 — Resource analysis + DAG export
- [ ] Step 5 — `barrier` optimization fence
- [ ] Step 6 — Showcase / examples / README overhaul
- [ ] Step 7 — Adversarial 3-lens review (Workflow) + fix confirmed
- [ ] Step 8 — merge --no-ff to main, tag v1.0.0, push, CI green

Tests: 251 baseline -> 312 now. Default pipeline order: cancel-inverses,
merge-rotations, peephole, control-flip, commute-cancel, canonicalize-rotations.

## Exact next step
Begin Step 3: topology.py (CouplingMap) + route.py (SWAP-insertion router) +
verify.check_routing_equivalence (permutation-aware). TDD (tests first).

## Verify commands
```
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src
```

## Rules
Commit identity GreenPandaTech noreply only; repo stays PRIVATE. Push after every
green increment. Keep every optimization pass semantics-preserving (proven).

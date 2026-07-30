# Session handoff — Daedalus

## PROJECT STATUS: v1.0.0 COMPLETE — DO NOT RE-EXECUTE ANY STEP BELOW

The "to the max" program (spec: `docs/superpowers/specs/to-the-max.md`) is
**finished**. Step 8 (merge --no-ff to main, tag v1.0.0, push) was **executed
on 2026-07-09** — the merge commit `b61482a` ("Merge Daedalus to-the-max:
verified quantum compiler v1.0.0") is on `main` and pushed. Any older copy of
this file listing Step 8 as "the exact next step" is EXPIRED. There is nothing
left of that program to resume.

## Current state (2026-07-30): v1.1.0 sabre routing round

- Feature round complete on `main`: SABRE-lite routing strategy
  (`route --strategy sabre`), `check_routing_equivalence` initial-layout
  support, `bench.py` sabre-vs-greedy benchmark, README/CHANGELOG updated,
  version bumped to 1.1.0.
- Gates at the end of the round: 456 pytest green, `ruff check .` clean,
  `mypy src` (strict) clean.
- **Committed locally, NOT pushed** — pushing was out of scope for the round.
  Next step for a resuming session: push `main` after the operator confirms.

## Historical record — "to the max" build order (all done)
- [x] Step 0 — Tooling gate: ruff + mypy + CI lint job
- [x] Step 1 — Exact unitary proof engine (`unitary.py`, `--proof`)
- [x] Step 2 — New verified passes (canonicalize-rotations, commute x-basis, control-flip)
- [x] Step 3 — Topology + verified routing (crown jewel) + route CLI
- [x] Step 4 — Resource analysis + DAG export (analyze.py, dot.py, --emit dot, `analyze`)
- [x] Step 5 — `barrier` optimization fence (parse/dump/sim/draw/qasm + all passes respect it)
- [x] Step 6 — Showcase / examples / README overhaul + CHANGELOG + version 1.0.0
- [x] Step 7 — Adversarial 3-lens review (Workflow): 3 findings, all confirmed + fixed
- [x] Step 8 — merge --no-ff to main, tag v1.0.0, push, CI green (DONE 2026-07-09)

## Verify commands
```
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src
```

## Rules
Commit identity GreenPandaTech noreply only; repo stays PRIVATE. Push after every
green increment. Keep every optimization pass semantics-preserving (proven).

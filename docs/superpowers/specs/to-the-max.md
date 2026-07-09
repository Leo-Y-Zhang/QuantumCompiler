# Daedalus "to the max" — spec

Status: **self-approved** (2026-07-09), autonomous execution.
Target release: **v1.0.0**. Baseline: v0.2.0 / 251 tests green.

## The one-line thesis

Daedalus today is a *toy verified-rewrite demo*: a real compiler front-end
(lexer → parser → IR → pass manager) whose five optimization passes are checked
by a **randomized** statevector equivalence oracle. The distinctive idea — the
moat — is **"optimizations proven correct by simulation."**

"To the max" = grow it into a **small but genuine optimizing quantum compiler
where every stage is proven correct**, and *upgrade the proof itself* from
randomized evidence to an **exact unitary proof** for small circuits. Every new
capability is paired with verification; nothing is added that the equivalence
oracle cannot certify. It stays proudly, explicitly a *teaching* compiler — no
false claims of hardware backends, noise models, or production readiness.

This mirrors the calibration bar set by Hephaestus (one-way melt → bidirectional
thermodynamics sandbox, conserved-energy ledger) and Helios (path tracer →
production render engine, physics guardrails kept throughout): **deep, cohesive,
distinctive, fully test-guarded — not uniform polish.**

## What makes this distinctive (avoid AI-tell)

The whole build is organized around ONE spine — *verification* — rather than a
scattershot of unrelated features. Each cluster below either (a) makes the
proof stronger, or (b) adds a genuine compiler stage that is then *proven*
correct by that stronger proof. A reviewer should see a single coherent thesis,
hand-shaped to this project, not a checklist of generic "add more passes / add a
web UI" polish.

The crown jewel is **verified routing**: the README explicitly disclaims routing
as a limitation; adding a real SWAP-insertion router whose output is proven
equivalent to the input *up to the qubit permutation it induces* is exactly the
"most ambitious genuinely-coherent version" of a verified quantum compiler.

## Guardrails kept throughout (the moat — never regress these)

1. **Every optimization/lowering pass stays semantics-preserving** and is proven
   so by the equivalence oracle on every increment (existing invariant).
2. **The exact proof and the randomized check must agree** wherever both apply
   (small n) — a cross-check test enforces this on random circuits.
3. **A deliberately-wrong pass must be caught** by both oracles (negative tests).
4. **Pure Python stdlib, zero runtime deps** — unchanged. `pytest` dev-only;
   add `ruff` + `mypy` as dev-only lint/type gate.
5. **Determinism**: all sampling seeded; identical inputs → identical output.
6. **Honest framing**: caveats stay accurate; new features documented with their
   exact scope and limits.

## Build order (each step: TDD, committed + pushed green, resumable)

### Step 0 — Tooling gate (CI parity with Helios/Hephaestus)
- Add `ruff` (lint) + `mypy` (type-check, the package is already fully typed)
  as dev deps and `[tool.ruff]` / `[tool.mypy]` config in `pyproject.toml`.
- Add a `lint` CI job (ruff check + mypy) alongside the test matrix.
- Fix every finding. This is the "int/ruff+mypy equivalent to CI" mandate.

### Step 1 — Exact unitary proof engine (headline verification upgrade)
Implements the README roadmap item *"a `--proof` mode emitting the unitary
difference norm for small circuits."*
- New `unitary.py`: build the full 2ⁿ×2ⁿ circuit unitary by simulating each
  computational-basis input (columns of U); exact, reuses `sim.simulate`.
- `unitary_equivalence(a, b)` → exact up-to-global-phase check: align a single
  global phase from the max-magnitude entry, return Frobenius diff norm and
  process fidelity `|Tr(U_b† U_a)| / dim`. Exact — no sampling.
- Cap at `PROOF_MAX_QUBITS` (≈7); above it, callers fall back to the randomized
  oracle with an honest note.
- `verify.py`: add `prove_equivalence(...)` returning a richer result that runs
  the exact engine when small enough, else randomized.
- CLI: `--proof` on `compile` (and surfaced in `--verify` output) prints the
  exact difference norm / fidelity, or the honest randomized fallback.
- Guardrail tests: exact engine matches hand-computed unitaries (H, CX, S, Bell);
  exact and randomized agree on 100+ random circuits; exact catches a wrong pass;
  global-phase-only differences accepted; relative-phase differences rejected.

### Step 2 — New verified passes (real compiler theory, each proven)
- `canonicalize_rotations.py` — special-angle rotations → named Clifford+T:
  `rz(±pi/2)→s/sdg`, `rz(pi)→z`, `rz(±pi/4)→t/tdg`, `rx(pi)→x`, `ry(pi)→y`,
  `rz(0)`→drop (all up to global phase, all proven). Canonical, tolerance-based.
- Extend `commute_cancel` with the **x-basis rule**: an `x`/`rx` on the *target*
  of a `cx` commutes through it (X⊗-antidiagonal commutes with CX target),
  enabling target-side cancellations/merges — soundness proven by exact unitary.
- `control_flip.py` — the verified template `h a; h b; cx a,b; h a; h b → cx b,a`
  (Hadamard sandwich reverses a CX), and its mirror; exposes further cancellation.
  Only fires when the five gates are the exact consecutive window on both wires.

### Step 3 — Topology + verified routing (the crown jewel)
- `topology.py`: `CouplingMap` for `line`, `ring`, `grid(r,c)`, `full`, or an
  explicit edge list; BFS distance matrix, neighbours, connectivity check.
- `route.py`: SWAP-insertion router. Trivial initial layout + a greedy
  distance-reducing SWAP chooser (SABRE-lite): for each 2-qubit gate whose
  operands are not adjacent, insert SWAPs along a shortest path to bring them
  together, updating the running logical→physical permutation; single-qubit
  gates and measures follow the current mapping. Returns
  `(routed_circuit, final_layout, swaps_added)`.
- `verify.py`: `check_routing_equivalence(original, routed, final_layout)` —
  proves the routed circuit equals the original **up to the induced qubit
  permutation**, exact for small n (permute the statevector by `final_layout`),
  randomized above. This *is* the feature: routing is only trustworthy because
  it is proven. Direction of the permutation nailed down by exact tests on
  hand-worked 3-qubit line examples.
- CLI: `daedalus route FILE --coupling line|ring|grid:RxC|full [--emit ...]
  [--verify]`, reporting added SWAPs, pre/post depth, and the final layout.
- Honest scope: abstract coupling maps only — no device calibration, no noise.

### Step 4 — Resource analysis & DAG export
- `analyze.py`: circuit **depth** (moment count via the existing greedy
  scheduler), gate histogram, two-qubit-gate count, **T-count** (T/Tdg — the
  fault-tolerant cost metric), per-wire depth, qubit count.
- `daedalus analyze FILE` prints the report; JSON via `--json`.
- `--emit dot`: Graphviz DOT of the dependency DAG (the IR module already frames
  itself as "effectively a DAG" — this makes it literal and visual).
- `stats` gains a **gates-vs-depth** before/after line (the roadmap's pareto).

### Step 5 — `barrier` as a verified optimization fence
- DSL + QASM: `barrier q0, q1, ...` (and QASM `barrier`) — parsed, drawn,
  emitted, round-tripped. Skipped by the simulator (like `measure`).
- Every pass **respects the fence**: no rewrite may move a gate across a barrier
  on a shared wire. Proven by tests that a fence blocks an otherwise-firing
  optimization while the same circuit without the fence still optimizes.
- QASM importer upgrades `barrier` from *rejected* to *supported* (subset grows).

### Step 6 — Showcase, examples, README
- New example programs: `qft3.qf` (a recognizable 3-qubit QFT), a routing demo
  (`routed_line.qf`), a Clifford+T canonicalization demo. Regenerate all SVGs.
- README overhaul: new architecture map, verified-routing section with a real
  routed before/after, exact-proof section, analysis/T-count section, barrier,
  honest expanded Limitations, updated roadmap. Keep the honest-framing banner.
- CHANGELOG 1.0.0 entry. Bump version to 1.0.0.

### Step 7 — Adversarial multi-lens review (Workflow)
- Three independent lenses in parallel, each finding → adversarially verified
  (default to "refuted if uncertain"), only CONFIRMED findings fixed:
  1. **Quantum-correctness lens** — matrices, phase conventions, permutation
     direction, tolerance choices, proof soundness.
  2. **Compiler-soundness lens** — pass termination/fixpoint, barrier fence
     completeness across *all* passes, routing layout bookkeeping, IR invariants.
  3. **Code-quality & honesty lens** — dead code, over-claims vs. actual scope,
     doc/code drift, test gaps, AI-tell uniformity.
- Re-run full suite + ruff + mypy green after fixes.

### Step 8 — Land it
- `merge --no-ff` to `main`, tag `v1.0.0`, push, confirm CI green, delete branch.
- Update `project_repo_max_upgrades` memory; keep `SESSION_HANDOFF.md` current.

## Explicit non-goals (kept honest, avoids scope-creep AI-tell)
- No real hardware backends, pulse/calibration, or noise/error models.
- No classical control flow / mid-circuit measurement collapse (still markers).
- No general controlled-phase/multi-controlled gate zoo — the gate set grows by
  exactly one non-unitary directive (`barrier`); routing reuses `swap`.
- Simulator/proof stay exponential and capped; this is a teaching tool.

## Definition of done
- ~90–130 net new tests (bar: Hephaestus +113, Helios +67), all green.
- ruff + mypy clean in CI; test matrix green.
- Every pass, the router, and the proof engine each guarded by real
  quantum/compiler-validated tests (not smoke tests).
- README honest and accurate; examples regenerated; v1.0.0 tagged; CI green.

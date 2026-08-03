# Design Brief — circuit diagrams (ASCII and SVG)

**Date:** 2026-08-03 · **PRD:** [PRD.md](PRD.md) · **TDD:** [TDD.md](TDD.md)
**Scope:** `draw_ascii.py`, `draw_svg.py`, and the layout they share.

> This is the project's only designed surface. There is no application UI and
> no interactive flow — see the note at the end of the TDD for why no App Flow
> document exists. Sections of the standard template that describe screens,
> breakpoints, hover states and touch targets are cut rather than answered with
> "n/a", because there is nothing on the other side of them.

## Intent

A circuit diagram here should read like a **circuit schematic in a textbook**:
quiet, dense, and unambiguous about what is connected to what. Its whole job is
to let someone answer "did the optimizer change what this computes?" by eye,
side by side, in a terminal.

It must never feel like a *visualisation*. No colour coding by gate family, no
gradients, no rounded pastel blocks, no legend to consult. The moment the
diagram has visual opinions of its own, a reader starts reading the decoration
instead of the circuit — and this project's entire claim is that you can check
the rewrite yourself.

## Who is looking at it

Someone with the *before* and *after* diagrams stacked in a terminal, scanning
for the difference. Usually the author mid-debug; occasionally a reader of the
README who has never seen this DSL and is deciding in about ten seconds whether
the tool is serious. Both are reading a wall of monospace and want the change to
be the thing that jumps out.

## Precedents

- **Qiskit's `circuit.draw()` text output** — for the wire-per-row, moment-per
  -column grid and the `─■─` / `─⊕─` connector idiom. The specific thing it gets
  right is that a two-qubit gate is drawn as a *line between rows*, so
  connectivity survives being read at speed.
- **Standard quantum-circuit notation** (Nielsen & Chuang) — the filled dot for
  a control and the ⊕ for a `cx` target. Deviating from this would cost every
  reader who already knows the notation, and buy nothing.
- **gcc/clang diagnostics** — not for the diagram but for the same house style
  applied to errors: `file:line:col: error: message`, no colour required, no box
  drawing, greppable. The diagram and the diagnostics come out of the same
  program and should feel like the same program.

## Anti-patterns for this project

Specific enough to be enforceable in review:

- **No colour as a channel of meaning.** The ASCII renderer has no colour at
  all, and the SVG uses exactly one ink. If a fact is only visible in colour, it
  is invisible in the primary renderer.
- **No Unicode box-drawing or non-ASCII symbols** in the ASCII renderer. `(+)`,
  `o`, `x`, `:` and `|` survive copy-paste into a commit message, an issue, a
  code-block in a README, and a Windows console. `⊕` does not, reliably.
- **No re-implemented layout in the SVG.** Both renderers call the same
  `column_layout()`. If the SVG ever computed its own columns, the two views of
  the same circuit could disagree, which is worse than either being ugly.
- **No wrapping and no truncation.** A wide circuit produces a wide line. The
  terminal's own horizontal scroll is a better answer than a diagram that lies
  by omission.
- **No animation, no interactivity, no JavaScript.** The SVG is a static
  document that renders in a README and in an offline browser.

## Layout

One shared algorithm, in `column_layout()`: **greedy span-blocking moment
scheduling**. Each gate goes in the earliest column that is free on every wire
in its qubit *span* (`min..max`), not merely on the wires it touches.

This is the load-bearing decision. Blocking the whole span is what guarantees a
vertical connector never crosses an unrelated gate box, so a `cx` between `q0`
and `q3` can be traced with a finger. The cost is honest and documented: it
inflates the reported depth relative to a true dependency-DAG depth, and the
README's routing benchmark reports depth deltas under exactly this metric and
says so, rather than quoting a friendlier number.

Rows are `2n - 1` for `n` qubits: even rows are wires (filled with `-`), odd
rows are connector gutters (filled with spaces). Columns are padded to the
widest cell plus two, and cell content is centred, so gate boxes line up in
columns even when labels differ in width.

## Symbol vocabulary

| Meaning | ASCII | SVG |
|---|---|---|
| wire | `-` run, labelled `q0: ` | 1px horizontal line, label `q0` at left |
| single-qubit gate | `[H]`, `[RZ(pi/4)]` | white box, `rx=3`, 1px stroke, centred label |
| control | `o` | filled circle, `r=4` |
| `cx` target | `(+)` | open circle `r=9` + crosshair, 1.5px |
| `swap` end | `x` | crossed strokes |
| measure | `[M->c0]` | box, same as a gate, naming the target bit |
| barrier | `:` on each named wire | dashed vertical line, `4 3` |
| multi-qubit link | `\|` in the gutter rows | 1.5px vertical line |

Two rules keep this readable rather than cute: **angles are rendered
symbolically** (`RZ(pi/4)`, not `RZ(0.7853981633974483)`) via `format_angle`'s
rational-multiple-of-pi recovery, and **gate names are upper-cased in the
diagram only** — the DSL, the IR and the QASM output stay lower-case, so nothing
downstream has to parse a display convention.

## Colour (SVG only)

Roles, then values. There are three.

| Role | Value | Contrast on surface |
|---|---|---|
| surface | `#ffffff` | — |
| ink — wires, boxes, text, controls, targets | `#1f2430` | **15.52:1** |
| muted — barrier fence only | `#8a94a6` | **3.06:1** |

Ink is a near-black with a slight blue cast rather than `#000000`, which reads
as less harsh at 12px on white without costing any contrast.

The muted grey clears the 3:1 floor for a non-text UI boundary by 0.06, which is
tighter than it should be for a value chosen by eye. It is acceptable only
because **colour is not the only signal**: the barrier is also the one dashed
element in the drawing, so it remains identifiable in greyscale, at low contrast,
and to a reader who never sees the SVG at all (the ASCII renderer draws it as
`:`). If that pairing is ever revisited, darken the grey rather than relying on
the dash alone.

**Known limitation, stated rather than hidden:** the SVG hard-codes a white
background rect, so it does not adapt to a dark-mode README. It will render as a
white card on a dark page. Fixing that properly means either a `prefers-color
-scheme` media block inside the SVG or dropping the background rect and using
`currentColor` — neither is done, and the diagrams in the README are the
committed light-mode files.

## Type

One family: **monospace**, 12px, single weight, in both renderers. Not a
stylistic choice — the ASCII renderer's column alignment is only true in a
monospace cell grid, and using the same family in the SVG keeps a gate label the
same shape in both views. Line length is unbounded by design (see
anti-patterns).

## States

The renderers are pure functions of a `Circuit`; there is no hover, focus,
loading, or disabled state to design. The two states that do exist:

- **Empty circuit** (`qubits n` with no gates): still draws `n` labelled wires,
  each a short `-----` run. It renders as an empty staff, not as an empty
  string — "the circuit is empty" and "the renderer failed" must not look
  alike. Covered by `test_draw_ascii.py::test_empty_circuit` and
  `test_draw_svg.py::test_empty_circuit_renders`.
- **Zero qubits:** unreachable from the DSL — the parser rejects `qubits 0`
  with `qubit count must be at least 1`. Constructed directly through the
  Python API, `render_svg(Circuit(0, 0))` still emits a valid one-wire document
  (`max(num_qubits, 1)`), but `render_ascii(Circuit(0, 0))` returns the empty
  string, because its row loop is driven by `num_qubits` rather than by that
  same clamp. Stated here rather than papered over; it is a two-line
  inconsistency between the renderers, not a user-facing defect, and fixing it
  is a code change outside the scope of this document.

## Accessibility floor

Only the applicable items; the rest of the standard checklist is about
interactive web UI that does not exist here.

- **Contrast:** ink 15.52:1 (needs 4.5:1), muted 3.06:1 (needs 3:1). Both
  computed from the actual hex values above, not assumed.
- **Colour is never the only signal:** every element is distinguished by shape
  or stroke pattern first. The ASCII renderer proves this by having no colour.
- **The ASCII renderer is the accessible fallback**, and it is the default for
  `--emit ascii`. It is plain text: selectable, greppable, screen-reader
  readable in the sense that any monospace text is, and it survives being pasted
  anywhere.
- **Zoom:** the SVG carries a `viewBox` alongside its `width`/`height`, so it is
  resolution-independent and stays sharp at any zoom level rather than
  resampling like a raster export.
- **Not addressed:** the SVG has no `<title>`/`<desc>` and no ARIA roles, so a
  screen reader announces it as an unlabelled image. For a diagram whose content
  is a spatial arrangement this is a real gap; the mitigation today is that the
  same circuit is always available as text via `--emit ascii`.

## Done means

- [x] Both renderers share one column layout — no second implementation.
- [x] ASCII output is 7-bit ASCII only.
- [x] Empty and zero-qubit circuits render as something, and are tested.
- [x] Contrast computed from the real hex values, and the tight pair called out
      rather than rounded up.
- [x] Angles display symbolically; display casing never leaks into the IR,
      the DSL round-trip, or the QASM output.

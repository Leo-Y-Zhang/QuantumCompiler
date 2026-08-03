"""Command-line interface for quantum_compiler.

Exit codes
----------
- ``0`` success
- ``1`` I/O error (e.g. input file not readable)
- ``2`` usage error or source syntax error (position printed to stderr)
- ``3`` verification failed: ``--verify``/``--proof`` rejected a circuit, or
  ``equiv`` proved the two circuits are not equivalent
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from quantum_compiler import __version__
from quantum_compiler.analyze import analyze, format_report, metrics_to_dict
from quantum_compiler.dot import to_dot
from quantum_compiler.draw_ascii import column_layout, render_ascii
from quantum_compiler.draw_svg import render_svg
from quantum_compiler.equiv import (
    ShrinkResult,
    Witness,
    find_witness,
    format_basis,
    shrink_counterexample,
)
from quantum_compiler.errors import QuantumCompilerError
from quantum_compiler.ir import Circuit, dump
from quantum_compiler.parser import parse
from quantum_compiler.passes import DeadCodeElimination, PassManager, PassStats, default_passes
from quantum_compiler.qasm import emit_qasm, parse_qasm
from quantum_compiler.route import RoutingResult, route
from quantum_compiler.topology import CouplingMap
from quantum_compiler.verify import (
    DEFAULT_ATOL,
    ProofResult,
    check_equivalence,
    check_routing_equivalence,
    prove_equivalence,
)

_DCE_WARNING = (
    "warning: dead-code elimination changes unobserved state; "
    "it runs after --verify and is excluded from the equivalence guarantee"
)

_MEASURE_NOTE = (
    "note: measure gates are ignored - the verdict compares pre-measurement "
    "statevectors, so circuits measuring different qubits can still be equivalent here"
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with both subcommands."""
    parser = argparse.ArgumentParser(
        prog="quantum-compiler",
        description="Toy educational quantum-circuit DSL compiler (stdlib only).",
    )
    parser.add_argument("--version", action="version", version=f"quantum-compiler {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    compile_parser = subcommands.add_parser(
        "compile", help="parse, optionally optimize, and emit a circuit"
    )
    compile_parser.add_argument(
        "file", help="source file (.qasm is parsed as OpenQASM 2.0, else DSL)"
    )
    compile_parser.add_argument(
        "--opt", "-O", action="store_true", help="run the optimization pipeline"
    )
    compile_parser.add_argument(
        "--emit",
        choices=("ir", "ascii", "svg", "qasm", "dot"),
        default="ascii",
        help="output format (default: ascii; dot = Graphviz dependency DAG)",
    )
    compile_parser.add_argument(
        "--verify",
        action="store_true",
        help="check optimized-vs-original equivalence up to global phase (randomized)",
    )
    compile_parser.add_argument(
        "--proof",
        action="store_true",
        help="prove equivalence exactly via the full unitary when small enough, "
        "else randomized; reports the difference norm and process fidelity",
    )
    compile_parser.add_argument(
        "--dce",
        action="store_true",
        help="also run dead-code elimination (requires --opt; see caveat in docs)",
    )
    compile_parser.add_argument("--out", help="write output to FILE instead of stdout")

    stats_parser = subcommands.add_parser(
        "stats", help="show gate counts before/after each optimization pass"
    )
    stats_parser.add_argument(
        "file", help="source file (.qasm is parsed as OpenQASM 2.0, else DSL)"
    )
    stats_parser.add_argument(
        "--dce", action="store_true", help="include dead-code elimination in the pipeline"
    )

    route_parser = subcommands.add_parser(
        "route", help="insert SWAPs so every 2-qubit gate obeys a coupling map"
    )
    route_parser.add_argument(
        "file", help="source file (.qasm is parsed as OpenQASM 2.0, else DSL)"
    )
    route_parser.add_argument(
        "--coupling",
        default="line",
        help="target topology: line[:N] | ring[:N] | full[:N] | grid:RxC "
        "(N defaults to the circuit's qubit count)",
    )
    route_parser.add_argument(
        "--strategy",
        choices=("greedy", "sabre"),
        default="greedy",
        help="routing strategy: greedy (default) inserts SWAPs along shortest "
        "paths in program order; sabre adds lookahead SWAP scoring and "
        "reverse-traversal initial-layout selection",
    )
    route_parser.add_argument(
        "--emit",
        choices=("ir", "ascii", "svg", "qasm", "dot"),
        default="ascii",
        help="output format for the routed circuit (default: ascii)",
    )
    route_parser.add_argument(
        "--verify",
        action="store_true",
        help="prove the routed circuit equals the original up to the final layout",
    )
    route_parser.add_argument("--out", help="write the routed circuit to FILE")

    analyze_parser = subcommands.add_parser(
        "analyze", help="report circuit resources: depth, gate mix, T-count"
    )
    analyze_parser.add_argument(
        "file", help="source file (.qasm is parsed as OpenQASM 2.0, else DSL)"
    )
    analyze_parser.add_argument(
        "--json", action="store_true", help="emit metrics as JSON instead of a report"
    )

    equiv_parser = subcommands.add_parser(
        "equiv",
        help="prove two circuits equivalent up to global phase; on failure "
        "emit a counterexample witness and a delta-debugged minimal form",
        description="Prove two circuits equivalent up to global phase; on "
        "failure emit a counterexample witness and a delta-debugged minimal "
        "form. Measure gates are ignored: the comparison is between "
        "pre-measurement statevectors, so two circuits that differ only in "
        "what they measure are reported as equivalent (with a note).",
    )
    equiv_parser.add_argument(
        "file_a", help="first circuit (.qasm is parsed as OpenQASM 2.0, else DSL)"
    )
    equiv_parser.add_argument(
        "file_b", help="second circuit (.qasm is parsed as OpenQASM 2.0, else DSL)"
    )
    equiv_parser.add_argument(
        "--no-shrink",
        action="store_true",
        help="on failure, report the witness but skip the delta-debug shrink",
    )
    equiv_parser.add_argument(
        "--json",
        action="store_true",
        help="emit the verdict (plus any witness and shrink) as JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_arg_parser().parse_args(argv)
    if args.command == "equiv":
        return _run_equiv(args)
    source = _read_source(args.file)
    if source is None:
        return 1
    parser_fn = parse_qasm if args.file.lower().endswith(".qasm") else parse
    try:
        circuit = parser_fn(source)
    except QuantumCompilerError as exc:
        print(exc.format(args.file), file=sys.stderr)
        return 2
    if args.command == "stats":
        return _run_stats(circuit, dce=args.dce)
    if args.command == "route":
        return _run_route(args, circuit)
    if args.command == "analyze":
        return _run_analyze(circuit, as_json=args.json)
    return _run_compile(args, circuit)


def _read_source(path: str) -> str | None:
    """Read a UTF-8 source file; print a clean error and return None on failure.

    ``UnicodeDecodeError`` is caught alongside ``OSError`` so a binary or
    wrongly-encoded input yields the same one-line message and exit code 1
    instead of a traceback (it is a ``ValueError`` subclass, so it would
    otherwise escape).
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
        print(f"error: cannot read '{path}': {reason}", file=sys.stderr)
        return None


def _run_compile(args: argparse.Namespace, original: Circuit) -> int:
    if args.dce and not args.opt:
        print("error: --dce requires --opt", file=sys.stderr)
        return 2
    optimized = original
    if args.opt:
        optimized, _ = PassManager(default_passes()).run(original)
    if args.proof:
        proof = prove_equivalence(original, optimized)
        print(proof.summary(), file=sys.stderr)
        if not proof.equivalent:
            print("refusing to emit a non-equivalent circuit", file=sys.stderr)
            return 3
    elif args.verify:
        result = check_equivalence(original, optimized)
        if not result.equivalent:
            print(
                f"verify: not equivalent (max error {result.max_error:.3e}); "
                "refusing to emit",
                file=sys.stderr,
            )
            return 3
        print(
            f"verify: equivalent up to global phase "
            f"(max error {result.max_error:.3e}, {result.inputs_checked} inputs)",
            file=sys.stderr,
        )
    if args.dce:
        if args.verify or args.proof:
            print(_DCE_WARNING, file=sys.stderr)
        optimized = DeadCodeElimination().run(optimized)
    try:
        output = _emit(args, original, optimized)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return _write_output(output, args.out)


def _emit(args: argparse.Namespace, original: Circuit, optimized: Circuit) -> str:
    if args.emit == "ascii" and args.opt:
        return (
            "BEFORE:\n"
            + render_ascii(original)
            + "\n\nAFTER:\n"
            + render_ascii(optimized)
            + f"\n\ngates: {len(original.gates)} -> {len(optimized.gates)}\n"
        )
    return _emit_circuit(args.emit, optimized)


def _run_stats(circuit: Circuit, dce: bool) -> int:
    optimized, stats = PassManager(default_passes(dce=dce)).run(circuit)
    depths = (_depth(circuit), _depth(optimized))
    print(_format_stats(stats, len(circuit.gates), len(optimized.gates), depths), end="")
    return 0


def _format_stats(
    stats: list[PassStats], before: int, after: int, depths: tuple[int, int]
) -> str:
    lines = [f"{'pass':<18} {'iter':>4} {'before':>7} {'after':>6} {'removed':>8}"]
    for entry in stats:
        removed = entry.gates_before - entry.gates_after
        lines.append(
            f"{entry.name:<18} {entry.iteration:>4} {entry.gates_before:>7} "
            f"{entry.gates_after:>6} {removed:>8}"
        )
    reduction = 100.0 * (before - after) / before if before else 0.0
    lines.append(f"total: {before} -> {after} gates ({reduction:.1f}% reduction)")
    lines.append(f"depth: {depths[0]} -> {depths[1]}")
    return "\n".join(lines) + "\n"


def _run_route(args: argparse.Namespace, original: Circuit) -> int:
    try:
        coupling = _parse_coupling(args.coupling, original.num_qubits)
        result = route(original, coupling, strategy=args.strategy)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _report_routing(original, result, coupling, strategy=args.strategy)
    if args.verify:
        check = check_routing_equivalence(
            original,
            result.circuit,
            result.final_layout,
            initial_layout=result.initial_layout,
        )
        if not check.equivalent:
            print(
                f"verify: routing changed semantics (max error {check.max_error:.3e}); "
                "refusing to emit",
                file=sys.stderr,
            )
            return 3
        print(
            f"verify: routed circuit equivalent up to the final layout "
            f"(max error {check.max_error:.3e}, {check.inputs_checked} inputs)",
            file=sys.stderr,
        )
    try:
        output = _emit_circuit(args.emit, result.circuit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return _write_output(output, args.out)


def _report_routing(
    original: Circuit, result: RoutingResult, coupling: CouplingMap, *, strategy: str
) -> None:
    print(
        f"routed onto a {coupling.num_qubits}-qubit coupling map: "
        f"{result.swaps_added} swap(s) added, "
        f"depth {_depth(original)} -> {_depth(result.circuit)}",
        file=sys.stderr,
    )
    if strategy == "sabre":
        # The greedy strategy always starts from the trivial layout, so the
        # line is only printed when sabre has actually chosen a placement.
        print(
            f"initial layout (logical -> physical): {result.initial_layout}",
            file=sys.stderr,
        )
    print(f"final layout (logical -> physical): {result.final_layout}", file=sys.stderr)


def _depth(circuit: Circuit) -> int:
    """Circuit depth = number of moments in the greedy schedule."""
    return max(column_layout(circuit), default=-1) + 1


def _parse_coupling(spec: str, num_qubits: int) -> CouplingMap:
    """Build a coupling map from a ``kind[:arg]`` spec string."""
    kind, _, arg = spec.partition(":")
    kind = kind.lower()
    if kind == "grid":
        parts = arg.lower().split("x")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"invalid grid dimensions '{arg}', expected RxC like 2x3")
        coupling = CouplingMap.grid(int(parts[0]), int(parts[1]))
    elif kind in ("line", "ring", "full"):
        if arg and not arg.isdigit():
            raise ValueError(f"invalid size '{arg}' for {kind} coupling")
        size = int(arg) if arg else num_qubits
        builder = {"line": CouplingMap.line, "ring": CouplingMap.ring, "full": CouplingMap.full}
        coupling = builder[kind](size)
    else:
        raise ValueError(f"unknown coupling '{spec}'; use line, ring, full, or grid:RxC")
    if coupling.num_qubits < num_qubits:
        raise ValueError(
            f"coupling map has {coupling.num_qubits} qubits but the circuit needs {num_qubits}"
        )
    return coupling


def _emit_circuit(emit: str, circuit: Circuit) -> str:
    """Serialize a single circuit in the requested format."""
    if emit == "ir":
        return dump(circuit)
    if emit == "svg":
        return render_svg(circuit)
    if emit == "qasm":
        return emit_qasm(circuit)
    if emit == "dot":
        return to_dot(circuit)
    return render_ascii(circuit) + "\n"


def _run_equiv(args: argparse.Namespace) -> int:
    """Prove file_a and file_b equivalent; witness + shrink on failure."""
    circuits: list[Circuit] = []
    for path in (args.file_a, args.file_b):
        source = _read_source(path)
        if source is None:
            return 1
        parser_fn = parse_qasm if path.lower().endswith(".qasm") else parse
        try:
            circuits.append(parser_fn(source))
        except QuantumCompilerError as exc:
            print(exc.format(path), file=sys.stderr)
            return 2
    a, b = circuits
    measure_ignored = any(
        gate.name == "measure" for circuit in circuits for gate in circuit.gates
    )
    try:
        proof = prove_equivalence(a, b)
        witness = None if proof.equivalent else find_witness(a, b)
        shrink: ShrinkResult | None = None
        if not proof.equivalent and not args.no_shrink and a.num_qubits == b.num_qubits:
            shrink = shrink_counterexample(a, b)
    except ValueError as exc:  # circuits beyond the simulator's qubit cap
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(_equiv_json(proof, witness, shrink, measure_ignored), indent=2))
    else:
        _print_equiv_report(proof, witness, shrink, measure_ignored=measure_ignored)
    return 0 if proof.equivalent else 3


def _print_equiv_report(
    proof: ProofResult,
    witness: Witness | None,
    shrink: ShrinkResult | None,
    *,
    measure_ignored: bool,
) -> None:
    print(proof.summary())
    if measure_ignored:
        print(_MEASURE_NOTE)
    if proof.equivalent:
        return
    if proof.detail == "qubit counts differ":
        print("no witness: the circuits have different qubit counts")
        return
    if witness is None:
        print(
            "no witness found: every sampled battery input agrees to within "
            "the per-amplitude tolerance (the difference is spread across the "
            "full unitary below that tolerance, or lies beyond the sampled "
            "inputs); the proof verdict above is the authority"
        )
    else:
        print(
            f"counterexample witness: input {witness.label()} "
            f"(battery input {witness.input_index})"
        )
        print(
            "  disagreeing amplitudes (error = |B - phase*A|, raw = |B - A|, "
            f"shared phase {_format_amplitude(witness.phase)}):"
        )
        if abs(abs(witness.phase) - 1) > 1e-6:
            print(
                f"  (alignment factor magnitude {abs(witness.phase):.3f} - not a "
                "pure phase, because B already differs from A at the anchor "
                "amplitude; the raw column is the convention-free comparison)"
            )
        for row in _witness_rows(witness):
            print(row)
    if shrink is not None:
        print(
            f"delta-debug shrink: {shrink.gates_before} -> {shrink.gates_after} "
            f"gates across the pair ({shrink.oracle_calls} oracle calls)"
        )
        print("1-minimal: removing any single remaining gate makes the pair equivalent")
        for name, circuit in (("A", shrink.circuit_a), ("B", shrink.circuit_b)):
            print(f"  {name} ({len(circuit.gates)} gate(s)):")
            lines = _gate_lines(circuit)
            for line in lines:
                print(f"    {line}")
            if not lines:
                print("    (no gates)")


def _witness_rows(witness: Witness) -> list[str]:
    """Text rows for the worst disagreeing amplitudes, largest error first.

    Each row shows both the phase-aligned error and the raw ``|B - A|``
    difference, so a relative-phase disagreement (aligned error large, raw
    difference zero) is visibly distinct from an amplitude mismatch.
    """
    num_qubits = len(witness.output_a).bit_length() - 1
    return [
        f"    {format_basis(index, num_qubits)}: "
        f"A {_format_amplitude(amp_a)}  B {_format_amplitude(amp_b)}  "
        f"error {error:.3e}  raw {raw:.3e}"
        for error, raw, index, amp_a, amp_b in _ranked_disagreements(witness)
    ]


def _format_amplitude(amplitude: complex) -> str:
    return f"{amplitude.real:+.6f}{amplitude.imag:+.6f}j"


def _equiv_json(
    proof: ProofResult,
    witness: Witness | None,
    shrink: ShrinkResult | None,
    measure_ignored: bool,
) -> dict[str, object]:
    """Strict-JSON view of the verdict (non-finite errors become null).

    ``measure_ignored`` is true when either input contains a measure gate,
    flagging that the verdict compares pre-measurement statevectors only.
    """
    num_qubits = len(witness.output_a).bit_length() - 1 if witness else 0
    witness_data: dict[str, object] | None = None
    if witness is not None:
        witness_data = {
            "input": witness.label(),
            "battery_index": witness.input_index,
            "basis_index": witness.basis_index,
            "max_error": witness.max_error,
            "phase": [witness.phase.real, witness.phase.imag],
            "disagreements": [
                {
                    "state": format_basis(index, num_qubits),
                    "a": [amp_a.real, amp_a.imag],
                    "b": [amp_b.real, amp_b.imag],
                    "error": error,
                    "raw_error": raw,
                }
                for error, raw, index, amp_a, amp_b in _ranked_disagreements(witness)
            ],
        }
    shrink_data: dict[str, object] | None = None
    if shrink is not None:
        shrink_data = {
            "gates_before": shrink.gates_before,
            "gates_after": shrink.gates_after,
            "oracle_calls": shrink.oracle_calls,
            "a": dump(shrink.circuit_a),
            "b": dump(shrink.circuit_b),
        }
    return {
        "equivalent": proof.equivalent,
        "method": proof.method,
        "max_error": proof.max_error if math.isfinite(proof.max_error) else None,
        "process_fidelity": proof.process_fidelity,
        "detail": proof.detail,
        "measure_ignored": measure_ignored,
        "witness": witness_data,
        "shrink": shrink_data,
    }


def _ranked_disagreements(
    witness: Witness, limit: int = 4
) -> list[tuple[float, float, int, complex, complex]]:
    """The *limit* worst (error, raw, index, amp A, amp B) rows of a witness.

    Errors use the witness's shared alignment phase; ``raw`` is the unaligned
    ``|B - A|``. Rows are ranked by aligned error (ties break on the lower
    amplitude index so the ordering is deterministic). When the amplitude pair
    with the largest raw difference is not already among the rows it is
    appended, so the display never consists solely of rows whose printed
    amplitudes look identical while a visibly differing pair goes unshown.
    """
    ranked = sorted(
        (
            (abs(bb - witness.phase * aa), abs(bb - aa), index, aa, bb)
            for index, (aa, bb) in enumerate(
                zip(witness.output_a, witness.output_b, strict=True)
            )
        ),
        key=lambda item: (-item[0], item[2]),
    )
    rows = [row for row in ranked[:limit] if row[0] > DEFAULT_ATOL]
    raw_worst = max(ranked, key=lambda item: (item[1], -item[2]))
    if raw_worst[1] > DEFAULT_ATOL and all(row[2] != raw_worst[2] for row in rows):
        rows.append(raw_worst)
    return rows


def _gate_lines(circuit: Circuit) -> list[str]:
    """The gate statements of *circuit* in DSL syntax, register headers dropped."""
    return [
        line
        for line in dump(circuit).splitlines()
        if line and not line.startswith(("qubits ", "bits "))
    ]


def _run_analyze(circuit: Circuit, as_json: bool) -> int:
    metrics = analyze(circuit)
    if as_json:
        print(json.dumps(metrics_to_dict(metrics), indent=2))
    else:
        print(format_report(metrics), end="")
    return 0


def _write_output(output: str, out_path: str | None) -> int:
    """Write *output* to *out_path* or stdout; return the process exit code."""
    if out_path:
        try:
            Path(out_path).write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write '{out_path}': {exc.strerror or exc}", file=sys.stderr)
            return 1
    else:
        print(output, end="")
    return 0

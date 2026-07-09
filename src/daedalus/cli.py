"""Command-line interface for daedalus.

Exit codes
----------
- ``0`` success
- ``1`` I/O error (e.g. input file not readable)
- ``2`` usage error or source syntax error (position printed to stderr)
- ``3`` ``--verify`` failed: optimized circuit is not equivalent
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from daedalus import __version__
from daedalus.analyze import analyze, format_report, metrics_to_dict
from daedalus.dot import to_dot
from daedalus.draw_ascii import column_layout, render_ascii
from daedalus.draw_svg import render_svg
from daedalus.errors import DaedalusError
from daedalus.ir import Circuit, dump
from daedalus.parser import parse
from daedalus.passes import DeadCodeElimination, PassManager, PassStats, default_passes
from daedalus.qasm import emit_qasm, parse_qasm
from daedalus.route import RoutingResult, route
from daedalus.topology import CouplingMap
from daedalus.verify import check_equivalence, check_routing_equivalence, prove_equivalence

_DCE_WARNING = (
    "warning: dead-code elimination changes unobserved state; "
    "it runs after --verify and is excluded from the equivalence guarantee"
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with both subcommands."""
    parser = argparse.ArgumentParser(
        prog="daedalus",
        description="Toy educational quantum-circuit DSL compiler (stdlib only).",
    )
    parser.add_argument("--version", action="version", version=f"daedalus {__version__}")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_arg_parser().parse_args(argv)
    try:
        source = Path(args.file).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read '{args.file}': {exc.strerror or exc}", file=sys.stderr)
        return 1
    parser_fn = parse_qasm if args.file.lower().endswith(".qasm") else parse
    try:
        circuit = parser_fn(source)
    except DaedalusError as exc:
        print(exc.format(args.file), file=sys.stderr)
        return 2
    if args.command == "stats":
        return _run_stats(circuit, dce=args.dce)
    if args.command == "route":
        return _run_route(args, circuit)
    if args.command == "analyze":
        return _run_analyze(circuit, as_json=args.json)
    return _run_compile(args, circuit)


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
        result = route(original, coupling)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _report_routing(original, result, coupling)
    if args.verify:
        check = check_routing_equivalence(original, result.circuit, result.final_layout)
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


def _report_routing(original: Circuit, result: RoutingResult, coupling: CouplingMap) -> None:
    print(
        f"routed onto a {coupling.num_qubits}-qubit coupling map: "
        f"{result.swaps_added} swap(s) added, "
        f"depth {_depth(original)} -> {_depth(result.circuit)}",
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

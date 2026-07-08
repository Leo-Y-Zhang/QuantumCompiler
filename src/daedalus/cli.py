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
import sys
from pathlib import Path
from typing import Sequence

from daedalus import __version__
from daedalus.draw_ascii import render_ascii
from daedalus.draw_svg import render_svg
from daedalus.errors import DaedalusError
from daedalus.ir import Circuit, dump
from daedalus.parser import parse
from daedalus.passes import DeadCodeElimination, PassManager, PassStats, default_passes
from daedalus.qasm import emit_qasm, parse_qasm
from daedalus.verify import check_equivalence

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
        choices=("ir", "ascii", "svg", "qasm"),
        default="ascii",
        help="output format (default: ascii)",
    )
    compile_parser.add_argument(
        "--verify",
        action="store_true",
        help="check optimized-vs-original equivalence up to global phase",
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
    return _run_compile(args, circuit)


def _run_compile(args: argparse.Namespace, original: Circuit) -> int:
    if args.dce and not args.opt:
        print("error: --dce requires --opt", file=sys.stderr)
        return 2
    optimized = original
    if args.opt:
        optimized, _ = PassManager(default_passes()).run(original)
    if args.verify:
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
        if args.verify:
            print(_DCE_WARNING, file=sys.stderr)
        optimized = DeadCodeElimination().run(optimized)
    try:
        output = _emit(args, original, optimized)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.out:
        try:
            Path(args.out).write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write '{args.out}': {exc.strerror or exc}", file=sys.stderr)
            return 1
    else:
        print(output, end="")
    return 0


def _emit(args: argparse.Namespace, original: Circuit, optimized: Circuit) -> str:
    if args.emit == "ir":
        return dump(optimized)
    if args.emit == "svg":
        return render_svg(optimized)
    if args.emit == "qasm":
        return emit_qasm(optimized)
    if args.opt:
        return (
            "BEFORE:\n"
            + render_ascii(original)
            + "\n\nAFTER:\n"
            + render_ascii(optimized)
            + f"\n\ngates: {len(original.gates)} -> {len(optimized.gates)}\n"
        )
    return render_ascii(optimized) + "\n"


def _run_stats(circuit: Circuit, dce: bool) -> int:
    optimized, stats = PassManager(default_passes(dce=dce)).run(circuit)
    print(_format_stats(stats, len(circuit.gates), len(optimized.gates)), end="")
    return 0


def _format_stats(stats: list[PassStats], before: int, after: int) -> str:
    lines = [f"{'pass':<18} {'iter':>4} {'before':>7} {'after':>6} {'removed':>8}"]
    for entry in stats:
        removed = entry.gates_before - entry.gates_after
        lines.append(
            f"{entry.name:<18} {entry.iteration:>4} {entry.gates_before:>7} "
            f"{entry.gates_after:>6} {removed:>8}"
        )
    reduction = 100.0 * (before - after) / before if before else 0.0
    lines.append(f"total: {before} -> {after} gates ({reduction:.1f}% reduction)")
    return "\n".join(lines) + "\n"

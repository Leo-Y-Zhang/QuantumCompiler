"""Benchmark table tests: real numbers, deterministic output, honest columns."""

from quantum_compiler import bench
from quantum_compiler.parser import parse
from quantum_compiler.route import route
from quantum_compiler.topology import CouplingMap


class TestBenchmarkTable:
    def test_covers_every_example_and_topology(self) -> None:
        table = bench.benchmark_table()
        for name in ["bell", "ghz", "rotations", "qft3", "clifford_t", "routed_line"]:
            assert name in table
        for label in ["line:4", "ring:4", "grid:2x2", "grid:2x3", "full:4"]:
            assert label in table

    def test_deterministic(self) -> None:
        assert bench.benchmark_table() == bench.benchmark_table()

    def test_row_numbers_match_a_direct_route_call(self) -> None:
        # Cross-check one row against the routing API so the table cannot drift
        # from what the router actually does.
        source = (bench.EXAMPLES_DIR / "routed_line.qf").read_text(encoding="ascii")
        original = parse(source)
        coupling = CouplingMap.line(4)
        greedy = route(original, coupling)
        sabre = route(original, coupling, strategy="sabre")
        depth = bench._depth(original)
        row = bench._format_row(
            "routed_line",
            "line:4",
            greedy.swaps_added,
            sabre.swaps_added,
            bench._depth(greedy.circuit) - depth,
            bench._depth(sabre.circuit) - depth,
        )
        assert row in bench.benchmark_table()

    def test_main_prints_the_table(self, capsys) -> None:
        assert bench.main() == 0
        out = capsys.readouterr().out
        assert "| circuit" in out
        assert "routed_line" in out

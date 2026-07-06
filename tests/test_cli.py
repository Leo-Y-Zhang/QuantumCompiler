"""CLI tests: in-process argument handling plus true subprocess end-to-end runs."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qforge import cli
from qforge.verify import EquivalenceResult

PROGRAM = """\
qubits 2
bits 2
h q0
x q1
x q1
cx q0, q1
measure q0 -> c0
measure q1 -> c1
"""


@pytest.fixture()
def program(tmp_path: Path) -> Path:
    path = tmp_path / "bell.qf"
    path.write_text(PROGRAM, encoding="ascii")
    return path


class TestCompile:
    def test_ascii_before_after(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program), "--opt"]) == 0
        out = capsys.readouterr().out
        assert "BEFORE" in out
        assert "AFTER" in out
        assert "[H]" in out

    def test_plain_compile_draws_circuit(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program)]) == 0
        out = capsys.readouterr().out
        assert "[H]" in out
        assert "AFTER" not in out

    def test_emit_ir(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program), "-O", "--emit", "ir"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("qubits 2")
        assert "x q1" not in out  # the x x pair was cancelled

    def test_emit_svg_to_file(self, program: Path, tmp_path: Path, capsys) -> None:
        out_file = tmp_path / "circuit.svg"
        code = cli.main(["compile", str(program), "--emit", "svg", "--out", str(out_file)])
        assert code == 0
        root = ET.fromstring(out_file.read_text(encoding="ascii"))
        assert root.tag.endswith("svg")
        assert capsys.readouterr().out == ""

    def test_verify_reports_equivalent(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program), "-O", "--verify"]) == 0
        assert "equivalent" in capsys.readouterr().err

    def test_verify_failure_exits_3(self, program: Path, capsys, monkeypatch) -> None:
        failed = EquivalenceResult(equivalent=False, max_error=1.0, inputs_checked=5)
        monkeypatch.setattr(cli, "check_equivalence", lambda *a, **k: failed)
        assert cli.main(["compile", str(program), "-O", "--verify"]) == 3
        assert "not equivalent" in capsys.readouterr().err

    def test_dce_verify_warns(self, program: Path, capsys) -> None:
        code = cli.main(["compile", str(program), "-O", "--dce", "--verify"])
        assert code == 0
        assert "dead-code" in capsys.readouterr().err


class TestErrors:
    def test_syntax_error_exit_2_with_position(self, tmp_path: Path, capsys) -> None:
        bad = tmp_path / "bad.qf"
        bad.write_text("qubits 1\nh q9\n", encoding="ascii")
        assert cli.main(["compile", str(bad)]) == 2
        err = capsys.readouterr().err
        assert "bad.qf:2:3: error:" in err

    def test_missing_file_exit_1(self, tmp_path: Path, capsys) -> None:
        assert cli.main(["compile", str(tmp_path / "nope.qf")]) == 1
        assert "error" in capsys.readouterr().err


class TestStats:
    def test_stats_table(self, program: Path, capsys) -> None:
        assert cli.main(["stats", str(program)]) == 0
        out = capsys.readouterr().out
        assert "cancel-inverses" in out
        assert "total" in out

    def test_stats_shows_reduction(self, program: Path, capsys) -> None:
        cli.main(["stats", str(program)])
        out = capsys.readouterr().out
        assert "6 -> 4" in out


class TestSubprocessEndToEnd:
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "qforge", *args],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_compile_verify_end_to_end(self, program: Path) -> None:
        result = self.run_cli("compile", str(program), "-O", "--verify")
        assert result.returncode == 0
        assert "BEFORE" in result.stdout
        assert "equivalent" in result.stderr

    def test_stats_end_to_end(self, program: Path) -> None:
        result = self.run_cli("stats", str(program))
        assert result.returncode == 0
        assert "total" in result.stdout

    def test_version(self) -> None:
        result = self.run_cli("--version")
        assert result.returncode == 0
        assert "qforge 0.1.0" in result.stdout

    def test_usage_error_exit_2(self) -> None:
        result = self.run_cli()
        assert result.returncode == 2

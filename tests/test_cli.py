"""CLI tests: in-process argument handling plus true subprocess end-to-end runs."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from daedalus import cli
from daedalus.verify import EquivalenceResult

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

    def test_proof_reports_exact_unitary(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program), "-O", "--proof"]) == 0
        err = capsys.readouterr().err
        assert "exact unitary" in err
        assert "process fidelity" in err

    def test_proof_failure_exits_3(self, program: Path, capsys, monkeypatch) -> None:
        from daedalus.verify import ProofResult

        failed = ProofResult(
            equivalent=False, method="exact-unitary", max_error=1.0, inputs_checked=4
        )
        monkeypatch.setattr(cli, "prove_equivalence", lambda *a, **k: failed)
        assert cli.main(["compile", str(program), "-O", "--proof"]) == 3
        assert "refusing to emit" in capsys.readouterr().err

    def test_dce_proof_warns(self, program: Path, capsys) -> None:
        code = cli.main(["compile", str(program), "-O", "--dce", "--proof"])
        assert code == 0
        assert "dead-code" in capsys.readouterr().err


class TestRoute:
    @pytest.fixture()
    def far(self, tmp_path: Path) -> Path:
        path = tmp_path / "far.qf"
        path.write_text("qubits 3\nh q0\ncx q0, q2\n", encoding="ascii")
        return path

    def test_route_line_inserts_swap_and_verifies(self, far: Path, capsys) -> None:
        assert cli.main(["route", str(far), "--coupling", "line", "--verify"]) == 0
        out = capsys.readouterr()
        assert "1 swap(s) added" in out.err
        assert "equivalent up to the final layout" in out.err
        assert "final layout" in out.err
        assert "[X]" in out.out or "(+)" in out.out

    def test_route_full_needs_no_swaps(self, far: Path, capsys) -> None:
        assert cli.main(["route", str(far), "--coupling", "full"]) == 0
        assert "0 swap(s) added" in capsys.readouterr().err

    def test_route_grid_spec(self, far: Path, capsys) -> None:
        assert cli.main(["route", str(far), "--coupling", "grid:2x2"]) == 0
        assert "swap(s) added" in capsys.readouterr().err

    def test_route_emit_qasm_to_file(self, far: Path, tmp_path: Path) -> None:
        out_file = tmp_path / "routed.qasm"
        code = cli.main(
            ["route", str(far), "--coupling", "line", "--emit", "qasm", "--out", str(out_file)]
        )
        assert code == 0
        assert out_file.read_text(encoding="ascii").startswith("OPENQASM 2.0;")

    def test_route_bad_coupling_exit_2(self, far: Path, capsys) -> None:
        assert cli.main(["route", str(far), "--coupling", "banana"]) == 2
        assert "unknown coupling" in capsys.readouterr().err

    def test_route_too_small_map_exit_2(self, far: Path, capsys) -> None:
        assert cli.main(["route", str(far), "--coupling", "line:2"]) == 2
        assert "qubits" in capsys.readouterr().err

    def test_route_verify_failure_exits_3(self, far: Path, capsys, monkeypatch) -> None:
        from daedalus.verify import EquivalenceResult

        failed = EquivalenceResult(equivalent=False, max_error=1.0, inputs_checked=8)
        monkeypatch.setattr(cli, "check_routing_equivalence", lambda *a, **k: failed)
        assert cli.main(["route", str(far), "--coupling", "line", "--verify"]) == 3
        assert "changed semantics" in capsys.readouterr().err


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

    def test_stats_shows_depth(self, program: Path, capsys) -> None:
        cli.main(["stats", str(program)])
        assert "depth:" in capsys.readouterr().out


class TestAnalyze:
    def test_report(self, program: Path, capsys) -> None:
        assert cli.main(["analyze", str(program)]) == 0
        out = capsys.readouterr().out
        assert "qubits: 2" in out
        assert "depth:" in out
        assert "T-count" in out

    def test_json(self, program: Path, capsys) -> None:
        import json as _json

        assert cli.main(["analyze", str(program), "--json"]) == 0
        data = _json.loads(capsys.readouterr().out)
        assert data["num_qubits"] == 2
        assert data["two_qubit_count"] == 1


class TestDotEmit:
    def test_compile_emit_dot(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program), "--emit", "dot"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("digraph")
        assert "->" in out


BELL_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
x q[1];
x q[1];
cx q[0],q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


@pytest.fixture()
def qasm_program(tmp_path: Path) -> Path:
    path = tmp_path / "bell.qasm"
    path.write_text(BELL_QASM, encoding="ascii")
    return path


class TestQasm:
    def test_emit_qasm(self, program: Path, capsys) -> None:
        assert cli.main(["compile", str(program), "--emit", "qasm"]) == 0
        out = capsys.readouterr().out
        assert out == BELL_QASM

    def test_qasm_input_auto_detected(self, qasm_program: Path, capsys) -> None:
        assert cli.main(["compile", str(qasm_program), "--emit", "ir"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("qubits 2")
        assert "measure q0 -> c0" in out

    def test_qasm_input_opt_verify(self, qasm_program: Path, capsys) -> None:
        assert cli.main(["compile", str(qasm_program), "-O", "--verify"]) == 0
        assert "equivalent" in capsys.readouterr().err

    def test_qasm_stats(self, qasm_program: Path, capsys) -> None:
        assert cli.main(["stats", str(qasm_program)]) == 0
        assert "total" in capsys.readouterr().out

    def test_qasm_syntax_error_position(self, tmp_path: Path, capsys) -> None:
        bad = tmp_path / "bad.qasm"
        bad.write_text(
            'OPENQASM 2.0;\nqreg q[1];\nbarrier q;\n', encoding="ascii"
        )
        assert cli.main(["compile", str(bad)]) == 2
        err = capsys.readouterr().err
        assert "bad.qasm:3:1: error:" in err
        assert "barrier" in err

    def test_emit_qasm_zero_qubits_exit_2(self, tmp_path: Path, capsys) -> None:
        empty = tmp_path / "empty.qf"
        empty.write_text("", encoding="ascii")
        assert cli.main(["compile", str(empty), "--emit", "qasm"]) == 2
        assert "error" in capsys.readouterr().err


class TestSubprocessEndToEnd:
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "daedalus", *args],
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

    def test_qasm_in_qasm_out_end_to_end(self, qasm_program: Path, tmp_path: Path) -> None:
        out_file = tmp_path / "roundtrip.qasm"
        result = self.run_cli(
            "compile", str(qasm_program), "-O", "--verify",
            "--emit", "qasm", "--out", str(out_file),
        )
        assert result.returncode == 0
        assert "equivalent" in result.stderr
        text = out_file.read_text(encoding="ascii")
        assert text.startswith("OPENQASM 2.0;")
        assert "x q[1];" not in text  # the x x pair was cancelled
        assert "measure q[0] -> c[0];" in text

    def test_version(self) -> None:
        result = self.run_cli("--version")
        assert result.returncode == 0
        assert "daedalus 0.2.0" in result.stdout

    def test_usage_error_exit_2(self) -> None:
        result = self.run_cli()
        assert result.returncode == 2

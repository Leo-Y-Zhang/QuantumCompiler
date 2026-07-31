"""CLI tests: in-process argument handling plus true subprocess end-to-end runs."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from daedalus import cli
from daedalus.equiv import Witness
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

    def test_non_utf8_input_exits_1_cleanly(self, tmp_path: Path, capsys) -> None:
        # A binary/wrongly-encoded file must produce the one-line I/O error,
        # not a UnicodeDecodeError traceback.
        bad = tmp_path / "bin.qf"
        bad.write_bytes(b"\xff\xfe\x00binary")
        assert cli.main(["compile", str(bad)]) == 1
        err = capsys.readouterr().err
        assert "cannot read" in err
        assert "Traceback" not in err

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

    def test_route_strategy_sabre_verifies_and_reports_initial_layout(
        self, far: Path, capsys
    ) -> None:
        code = cli.main(
            ["route", str(far), "--coupling", "line", "--strategy", "sabre", "--verify"]
        )
        assert code == 0
        err = capsys.readouterr().err
        assert "initial layout (logical -> physical):" in err
        assert "final layout (logical -> physical):" in err
        assert "equivalent up to the final layout" in err

    def test_route_default_strategy_output_has_no_initial_layout_line(
        self, far: Path, capsys
    ) -> None:
        # Back-compat: the greedy path (still the default) is unchanged.
        assert cli.main(["route", str(far), "--coupling", "line", "--verify"]) == 0
        err = capsys.readouterr().err
        assert "initial layout" not in err

    def test_route_strategy_greedy_matches_default(self, far: Path, capsys) -> None:
        assert cli.main(["route", str(far), "--coupling", "line"]) == 0
        default_out = capsys.readouterr()
        assert cli.main(["route", str(far), "--coupling", "line", "--strategy", "greedy"]) == 0
        explicit_out = capsys.readouterr()
        assert explicit_out.out == default_out.out
        assert explicit_out.err == default_out.err


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
            'OPENQASM 2.0;\nqreg q[1];\nreset q[0];\n', encoding="ascii"
        )
        assert cli.main(["compile", str(bad)]) == 2
        err = capsys.readouterr().err
        assert "bad.qasm:3:1: error:" in err
        assert "reset" in err

    def test_emit_qasm_zero_qubits_exit_2(self, tmp_path: Path, capsys) -> None:
        empty = tmp_path / "empty.qf"
        empty.write_text("", encoding="ascii")
        assert cli.main(["compile", str(empty), "--emit", "qasm"]) == 2
        assert "error" in capsys.readouterr().err


class TestEquiv:
    @pytest.fixture()
    def equal_pair(self, tmp_path: Path) -> tuple[Path, Path]:
        a = tmp_path / "a.qf"
        a.write_text("qubits 1\nh q0\nh q0\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 1\n", encoding="ascii")
        return a, b

    @pytest.fixture()
    def unequal_pair(self, tmp_path: Path) -> tuple[Path, Path]:
        a = tmp_path / "a.qf"
        a.write_text("qubits 1\nx q0\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 1\nz q0\n", encoding="ascii")
        return a, b

    def test_equivalent_pair_exits_0(self, equal_pair: tuple[Path, Path], capsys) -> None:
        a, b = equal_pair
        assert cli.main(["equiv", str(a), str(b)]) == 0
        out = capsys.readouterr().out
        assert "equivalent up to global phase" in out
        assert "exact unitary" in out

    def test_unequal_pair_exits_3_with_witness_and_shrink(
        self, unequal_pair: tuple[Path, Path], capsys
    ) -> None:
        a, b = unequal_pair
        assert cli.main(["equiv", str(a), str(b)]) == 3
        out = capsys.readouterr().out
        assert "NOT equivalent" in out
        assert "counterexample witness" in out
        assert "delta-debug shrink" in out
        assert "1-minimal" in out

    def test_no_shrink_flag_skips_the_shrink(
        self, unequal_pair: tuple[Path, Path], capsys
    ) -> None:
        a, b = unequal_pair
        assert cli.main(["equiv", str(a), str(b), "--no-shrink"]) == 3
        out = capsys.readouterr().out
        assert "counterexample witness" in out
        assert "delta-debug shrink" not in out

    def test_json_verdict_not_equivalent(
        self, unequal_pair: tuple[Path, Path], capsys
    ) -> None:
        import json as _json

        a, b = unequal_pair
        assert cli.main(["equiv", str(a), str(b), "--json"]) == 3
        data = _json.loads(capsys.readouterr().out)
        assert data["equivalent"] is False
        assert data["method"] == "exact-unitary"
        assert data["witness"]["basis_index"] == 0
        assert data["witness"]["max_error"] > 0.9
        assert data["shrink"]["gates_after"] < data["shrink"]["gates_before"]
        assert data["shrink"]["a"].startswith("qubits 1")

    def test_json_verdict_equivalent(self, equal_pair: tuple[Path, Path], capsys) -> None:
        import json as _json

        a, b = equal_pair
        assert cli.main(["equiv", str(a), str(b), "--json"]) == 0
        data = _json.loads(capsys.readouterr().out)
        assert data["equivalent"] is True
        assert data["witness"] is None
        assert data["shrink"] is None

    def test_qubit_count_mismatch_exits_3(self, tmp_path: Path, capsys) -> None:
        a = tmp_path / "a.qf"
        a.write_text("qubits 1\nh q0\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 2\nh q0\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 3
        out = capsys.readouterr().out
        assert "qubit counts" in out

    def test_missing_file_exits_1(self, tmp_path: Path, capsys) -> None:
        a = tmp_path / "a.qf"
        a.write_text("qubits 1\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(tmp_path / "nope.qf")]) == 1
        assert "error" in capsys.readouterr().err

    def test_syntax_error_names_the_offending_file(self, tmp_path: Path, capsys) -> None:
        a = tmp_path / "a.qf"
        a.write_text("qubits 1\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 1\nfoo q0\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 2
        assert "b.qf:2:1: error:" in capsys.readouterr().err

    def test_too_many_qubits_exits_2(self, tmp_path: Path, capsys) -> None:
        a = tmp_path / "a.qf"
        a.write_text("qubits 11\nh q0\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 11\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 2
        assert "at most 10" in capsys.readouterr().err

    def test_qasm_inputs_accepted(self, program: Path, qasm_program: Path, capsys) -> None:
        # The DSL bell program and its QASM twin are the same circuit.
        assert cli.main(["equiv", str(program), str(qasm_program)]) == 0
        assert "equivalent" in capsys.readouterr().out

    def test_measure_only_difference_prints_the_caveat(
        self, tmp_path: Path, capsys
    ) -> None:
        # Two circuits that differ only in WHICH qubit they measure compare
        # equal on pre-measurement statevectors; the verdict must say so
        # explicitly instead of an unqualified green.
        a = tmp_path / "a.qf"
        a.write_text("qubits 2\nbits 1\nh q0\nmeasure q0 -> c0\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 2\nbits 1\nh q0\nmeasure q1 -> c0\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 0
        out = capsys.readouterr().out
        assert "equivalent up to global phase" in out
        assert "measure gates are ignored" in out
        assert "pre-measurement" in out

    def test_no_measure_means_no_caveat(
        self, equal_pair: tuple[Path, Path], capsys
    ) -> None:
        a, b = equal_pair
        assert cli.main(["equiv", str(a), str(b)]) == 0
        assert "measure gates are ignored" not in capsys.readouterr().out

    def test_json_measure_ignored_field(self, tmp_path: Path, capsys) -> None:
        import json as _json

        a = tmp_path / "a.qf"
        a.write_text("qubits 1\nbits 1\nmeasure q0 -> c0\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 1\nbits 1\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b), "--json"]) == 0
        data = _json.loads(capsys.readouterr().out)
        assert data["equivalent"] is True
        assert data["measure_ignored"] is True

    def test_json_measure_ignored_false_without_measure(
        self, equal_pair: tuple[Path, Path], capsys
    ) -> None:
        import json as _json

        a, b = equal_pair
        assert cli.main(["equiv", str(a), str(b), "--json"]) == 0
        assert _json.loads(capsys.readouterr().out)["measure_ignored"] is False

    def test_non_utf8_input_exits_1_cleanly(self, tmp_path: Path, capsys) -> None:
        bad = tmp_path / "bin.qf"
        bad.write_bytes(b"\xff\xfe\x00binary")
        ok = tmp_path / "ok.qf"
        ok.write_text("qubits 1\n", encoding="ascii")
        assert cli.main(["equiv", str(bad), str(ok)]) == 1
        err = capsys.readouterr().err
        assert "cannot read" in err
        assert "Traceback" not in err

    def test_witness_rows_show_raw_difference(
        self, unequal_pair: tuple[Path, Path], capsys
    ) -> None:
        a, b = unequal_pair
        assert cli.main(["equiv", str(a), str(b)]) == 3
        out = capsys.readouterr().out
        assert "raw = |B - A|" in out
        assert " raw 1.000e+00" in out

    def test_degenerate_alignment_factor_is_labelled(
        self, tmp_path: Path, capsys
    ) -> None:
        # Bell vs Bell-then-x: B vanishes at |00> where A peaks, so the anchor
        # ratio is 0 - a magnitude-0 number must not be presented as a phase
        # without comment.
        a = tmp_path / "a.qf"
        a.write_text("qubits 2\nh q0\ncx q0, q1\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 2\nh q0\ncx q0, q1\nx q0\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 3
        out = capsys.readouterr().out
        assert "shared phase +0.000000+0.000000j" in out
        assert "alignment factor magnitude 0.000" in out
        assert "not a pure phase" in out

    def test_unit_magnitude_phase_gets_no_degenerate_note(
        self, tmp_path: Path, capsys
    ) -> None:
        # Bell preparation ending t vs tdg anchors on |00> where both agree,
        # so the shared phase is a genuine unit-magnitude phase - no note.
        prep = "qubits 2\nh q0\ncx q0, q1\n"
        a = tmp_path / "a.qf"
        a.write_text(prep + "t q1\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text(prep + "tdg q1\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 3
        out = capsys.readouterr().out
        assert "shared phase +1.000000+0.000000j" in out
        assert "alignment factor magnitude" not in out

    def test_no_witness_message_is_honest_about_the_metric(
        self, tmp_path: Path, capsys
    ) -> None:
        # The 2-qubit near-tolerance pair (see test_equiv.py): oracle says NOT
        # equivalent on the accumulated Frobenius norm, yet no single sampled
        # amplitude errs above atol. The old message blamed unsampled inputs,
        # which is false here - every basis state IS sampled at 2 qubits.
        a = tmp_path / "a.qf"
        a.write_text("qubits 2\n", encoding="ascii")
        b = tmp_path / "b.qf"
        b.write_text("qubits 2\nrz(0.00000000095) q0\n", encoding="ascii")
        assert cli.main(["equiv", str(a), str(b)]) == 3
        out = capsys.readouterr().out
        assert "no witness found" in out
        assert "per-amplitude tolerance" in out
        assert "the proof verdict above is the authority" in out


class TestWitnessRendering:
    def test_largest_raw_row_is_appended_when_not_in_top_aligned(self) -> None:
        # Aligned-error ranking alone can show only rows whose raw amplitudes
        # look identical (a pure relative-phase disagreement); the row with the
        # largest raw |B - A| must be appended so a visibly differing amplitude
        # pair is always on display.
        witness = Witness(
            input_index=0,
            basis_index=0,
            input_state=[1 + 0j] + [0j] * 7,
            output_a=[0.5 + 0j, 0.4 + 0j, 0.35 + 0j, 0.3 + 0j, 0.5 + 0j, 0j, 0j, 0j],
            output_b=[0.5 + 0j, 0.4 + 0j, 0.35 + 0j, 0.3 + 0j, -0.5 + 0.1j, 0j, 0j, 0j],
            phase=-1 + 0j,
            max_error=1.0,
            worst_index=0,
        )
        rows = cli._ranked_disagreements(witness)
        assert [row[2] for row in rows] == [0, 1, 2, 3, 4]
        assert rows[-1][1] > 0.9  # the appended row really is the raw-worst one
        rendered = cli._witness_rows(witness)
        assert len(rendered) == 5
        assert all(" raw " in line for line in rendered)


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

    def test_equiv_end_to_end_exit_codes(self, program: Path, tmp_path: Path) -> None:
        same = self.run_cli("equiv", str(program), str(program))
        assert same.returncode == 0
        assert "equivalent up to global phase" in same.stdout
        broken = tmp_path / "broken.qf"
        broken.write_text(PROGRAM + "z q0\n", encoding="ascii")
        differs = self.run_cli("equiv", str(program), str(broken))
        assert differs.returncode == 3
        assert "counterexample witness" in differs.stdout

    def test_version(self) -> None:
        result = self.run_cli("--version")
        assert result.returncode == 0
        assert "daedalus 1.2.0" in result.stdout

    def test_usage_error_exit_2(self) -> None:
        result = self.run_cli()
        assert result.returncode == 2

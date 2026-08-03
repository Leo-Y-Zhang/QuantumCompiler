"""Resource analysis: depth, gate histogram, two-qubit count, T-count."""

import json

from quantum_compiler.analyze import analyze, format_report, metrics_to_dict
from quantum_compiler.parser import parse


class TestMetrics:
    def test_empty_circuit(self) -> None:
        m = analyze(parse("qubits 2\n"))
        assert m.num_qubits == 2
        assert m.operations == 0
        assert m.depth == 0
        assert m.two_qubit_count == 0
        assert m.t_count == 0

    def test_bell_metrics(self) -> None:
        m = analyze(parse("qubits 2\nbits 2\nh q0\ncx q0, q1\nmeasure q0 -> c0\n"))
        assert m.num_qubits == 2
        assert m.num_bits == 2
        assert m.operations == 3
        assert m.two_qubit_count == 1
        assert m.single_qubit_count == 1  # h; measure is neither
        assert m.gate_histogram == {"cx": 1, "h": 1, "measure": 1}

    def test_depth_counts_moments(self) -> None:
        # h q0 and h q1 share a moment; cx is a second moment.
        m = analyze(parse("qubits 2\nh q0\nh q1\ncx q0, q1\n"))
        assert m.depth == 2

    def test_depth_serial_on_one_wire(self) -> None:
        m = analyze(parse("qubits 1\nh q0\nx q0\nh q0\n"))
        assert m.depth == 3

    def test_t_count(self) -> None:
        m = analyze(parse("qubits 1\nt q0\ntdg q0\nt q0\ns q0\n"))
        assert m.t_count == 3  # t, tdg, t -- s is Clifford, not counted

    def test_two_qubit_count_includes_cz_swap(self) -> None:
        m = analyze(parse("qubits 3\ncx q0, q1\ncz q1, q2\nswap q0, q2\n"))
        assert m.two_qubit_count == 3

    def test_per_qubit_gate_counts(self) -> None:
        m = analyze(parse("qubits 2\nh q0\ncx q0, q1\nx q1\n"))
        # q0 touched by h, cx; q1 by cx, x.
        assert m.qubit_gate_counts == [2, 2]


class TestReport:
    def test_report_mentions_key_metrics(self) -> None:
        report = format_report(analyze(parse("qubits 2\nh q0\ncx q0, q1\nt q1\n")))
        assert "qubits" in report
        assert "depth" in report
        assert "T-count" in report
        assert "cx" in report

    def test_json_roundtrips(self) -> None:
        m = analyze(parse("qubits 2\nh q0\ncx q0, q1\n"))
        data = json.loads(json.dumps(metrics_to_dict(m)))
        assert data["num_qubits"] == 2
        assert data["two_qubit_count"] == 1
        assert data["gate_histogram"]["cx"] == 1

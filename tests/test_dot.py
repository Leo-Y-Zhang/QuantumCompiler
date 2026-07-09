"""Graphviz DOT export of the dependency DAG."""

from daedalus.dot import to_dot
from daedalus.parser import parse


class TestDot:
    def test_header_and_nodes(self) -> None:
        dot = to_dot(parse("qubits 2\nh q0\ncx q0, q1\n"))
        assert dot.startswith("digraph")
        assert 'n0 [label="h q0"]' in dot
        assert 'n1 [label="cx q0,q1"]' in dot
        assert dot.rstrip().endswith("}")

    def test_wire_dependency_edges(self) -> None:
        # h q0 -> cx (shared q0); cx -> x q1 (shared q1).
        dot = to_dot(parse("qubits 2\nh q0\ncx q0, q1\nx q1\n"))
        assert "n0 -> n1;" in dot
        assert "n1 -> n2;" in dot

    def test_no_edge_between_independent_wires(self) -> None:
        # Gates on disjoint qubits have no dependency edge.
        dot = to_dot(parse("qubits 2\nh q0\nx q1\n"))
        assert "->" not in dot

    def test_measure_and_angle_labels(self) -> None:
        dot = to_dot(parse("qubits 1\nbits 1\nrz(pi/4) q0\nmeasure q0 -> c0\n"))
        assert 'label="rz(pi/4) q0"' in dot
        assert 'label="measure q0->c0"' in dot

    def test_shared_two_qubit_edge_not_duplicated(self) -> None:
        # cx cx share both wires but produce a single dependency edge.
        dot = to_dot(parse("qubits 2\ncx q0, q1\ncx q0, q1\n"))
        assert dot.count("n0 -> n1;") == 1

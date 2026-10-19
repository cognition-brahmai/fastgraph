"""Storage contracts, scoped identities, and mutation regression tests."""

import gc
import threading
import weakref
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given, settings, strategies as st

from fastgraph import (
    ClosedGraphError,
    FastGraph,
    NodeNotFoundError,
    StaleReferenceError,
    ValidationError,
)


def test_native_backend_and_duplicate_upsert():
    graph = FastGraph()
    graph.add_nodes_batch([("a", {}), ("b", {})])
    graph.add_edge("a", "b", "knows", since=2020)
    edge = graph.add_edge("a", "b", "knows", since=2026)
    assert graph.stats()["backend"] == "rust"
    assert graph.edge_count == 1
    assert graph.has_edge("a", "b", "knows")
    assert graph.degree("a") == (1, 0, 1)
    assert len(graph.neighbors_out("a")) == 1
    assert edge.attrs["since"] == 2026
    assert graph.remove_edge("a", "b", "knows") == 1
    assert graph.get_edge("a", "b", "knows") is None
    assert graph.neighbors_out("a") == []
    assert not graph.has_edge("a", "b", "knows")


def test_endpoint_and_relation_predicates_are_independent():
    graph = FastGraph()
    graph.add_nodes_batch([(nid, {}) for nid in "abcd"])
    graph.add_edges_batch([(src, dst, "r") for src in "ac" for dst in "bd"])
    assert [edge.key() for edge in graph.find_edges("a", "b", "r")] == [("a", "b", "r")]
    assert graph.remove_edge("a", "b", "r") == 1
    assert graph.edge_count == 3
    assert graph.remove_edge() == 3
    assert graph.edge_count == 0


def test_detached_properties_and_immutable_edge_identity():
    graph = FastGraph()
    node = graph.add_node("a", values=[1], label="old")
    graph.add_node("b")
    graph.add_edge("a", "b", "r", payload={"x": [1]})
    attrs = graph.get_node("a")
    attrs["values"].append(2)
    node.attrs["values"].append(3)
    graph.graph["nodes"]["a"]["label"] = "changed"
    assert graph.get_node("a") == {"values": [1], "label": "old"}
    edge = graph.get_edge("a", "b", "r")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        edge.dst = "a"
    with pytest.raises(TypeError):
        edge.attrs["new"] = True
    edge.attrs["payload"]["x"].append(2)
    assert graph.get_edge("a", "b", "r").attrs["payload"] == {"x": [1]}
    graph.update_node("a", label="new")
    assert graph.get_node("a") == {"values": [1], "label": "new"}
    graph.add_node("a", replaced=True)
    assert graph.get_node("a") == {"replaced": True}


def test_batches_validate_before_any_write():
    graph = FastGraph()
    graph.add_node("original", x=1)
    revision = graph.revision
    with pytest.raises(ValidationError):
        graph.add_nodes_batch([("good", {}), ("bad", {"value": object()})])
    assert graph.node_ids() == ("original",)
    assert graph.revision == revision
    graph.add_node("b")
    with pytest.raises(NodeNotFoundError):
        graph.add_edges_batch([("original", "b", "r"), ("b", "missing", "r")])
    assert graph.edge_count == 0
    with pytest.raises(ValidationError):
        graph.add_edges_batch([("original", "b", "r"), ("b", "original", "s", {"x": {1}})])
    assert graph.edge_count == 0


def test_indexes_updates_batches_and_typed_null_semantics():
    graph = FastGraph()
    graph.add_nodes_batch(
        [
            ("missing", {}),
            ("null", {"p": None}),
            ("bool", {"p": True}),
            ("int", {"p": 1}),
            ("float", {"p": 1.0}),
            ("text", {"p": "1"}),
        ]
    )
    before = {value: [nid for nid, _ in graph.find_nodes(p=value)] for value in (None, "1")}
    graph.build_node_index("p")
    assert [nid for nid, _ in graph.find_nodes(p=None)] == before[None] == ["null"]
    assert [nid for nid, _ in graph.find_nodes(p="1")] == before["1"] == ["text"]
    assert [nid for nid, _ in graph.find_nodes(p=True)] == ["bool"]
    assert [nid for nid, _ in graph.find_nodes(p=1)] == ["int"]
    assert [nid for nid, _ in graph.find_nodes(p=1.0)] == ["float"]
    assert [nid for nid, _ in graph.find_nodes(p__exists=False)] == ["missing"]
    graph.add_nodes_batch([("int", {"p": 2})])
    assert graph.find_nodes(p=1) == []
    assert [nid for nid, _ in graph.find_nodes(p=2)] == ["int"]
    graph.remove_node("int")
    assert graph.find_nodes(p=2) == []


def test_filters_ranges_collections_and_limits():
    graph = FastGraph()
    graph.add_nodes_batch(
        [
            ("a", {"age": 20, "name": "Alice", "tags": ["a", "b"]}),
            ("b", {"age": 30, "name": "Bob", "tags": ["b"]}),
            ("c", {"age": 40, "name": "Bobby"}),
        ]
    )
    assert [nid for nid, _ in graph.find_nodes(age__gte=30, age__lt=40)] == ["b"]
    assert [nid for nid, _ in graph.find_nodes(name__startswith="Bob")] == ["b", "c"]
    assert [nid for nid, _ in graph.find_nodes(tags__contains="a")] == ["a"]
    assert [nid for nid, _ in graph.find_nodes(age__in=[20, 40])] == ["a", "c"]
    assert graph.find_nodes(limit=0) == []
    assert len(graph.find_nodes(limit=1)) == 1
    with pytest.raises(ValidationError):
        graph.find_nodes(age__unknown=1)
    with pytest.raises(ValidationError):
        graph.find_nodes(age__exists=1)


def test_compound_nodes_are_lazy_scopes_with_qualified_identity():
    graph = FastGraph("world")
    company = graph.add_node("company", kind="organization")
    assert not company.is_compound
    assert company.enter(create=False) is None
    assert graph.stats(recursive=True)["nodes"] == 1
    people = company.graph
    assert company.is_compound
    assert people.path == ("company",)
    assert people.parent.path == ()
    assert people.owner == company
    alice = people.add_node("alice", age=30)
    other = graph.add_node("other").graph
    other_alice = other.add_node("alice", age=20)
    assert alice != other_alice
    assert alice.path == ("company", "alice")
    assert graph.resolve(("company", "alice")) == alice
    assert company["alice"] == alice
    assert graph.get_node("alice") is None
    assert graph.node_count == 2
    assert graph.stats(recursive=True)["nodes"] == 4
    assert [path for path, _ in graph.find_nodes(recursive=True, age__gte=25)] == [alice.path]
    assert people.node_count == 1


def test_cross_scope_relationships_and_recursive_deletion():
    graph = FastGraph()
    graph.add_node("company")
    graph.add_node("outside")
    child = graph["company"].graph
    alice = child.add_node("alice")
    dept = child.add_node("dept").graph
    inside = dept.add_node("inside")
    graph.add_edge("outside", alice, "knows")
    child.add_edge(alice, graph["outside"], "reports")
    child.add_edge(alice, inside, "contains")
    assert graph.edge_count == 1
    assert child.edge_count == 2
    assert graph.stats(recursive=True)["edges"] == 3
    graph.remove_node("company")
    assert graph.node_ids() == ("outside",)
    assert graph.stats(recursive=True)["edges"] == 0
    with pytest.raises(StaleReferenceError):
        child.add_node("stale")
    with pytest.raises(NodeNotFoundError):
        _ = inside.attrs
    graph.add_node("company")
    graph["company"].graph.add_node("alice")
    with pytest.raises(NodeNotFoundError):
        _ = alice.attrs


def test_transaction_commit_and_rollback_cover_all_scopes():
    graph = FastGraph()
    graph.add_node("root")
    with graph.transaction():
        graph["root"].graph.add_node("committed")
        graph.add_node("ok")
    assert graph.resolve(("root", "committed")).local_id == "committed"
    ref = graph["root"]
    with pytest.raises(RuntimeError):
        with graph.transaction():
            graph.add_node("failed")
            ref.graph.add_node("failedchild")
            raise RuntimeError("rollback")
    assert "failed" not in graph
    assert graph["root"].graph.node_ids() == ("committed",)
    with pytest.raises(StaleReferenceError):
        _ = ref.attrs
    with graph.transaction():
        with pytest.raises(ValidationError):
            with graph.transaction():
                pass


def test_close_no_threads_and_gc_retains_no_graphs():
    before = {thread.ident for thread in threading.enumerate()}
    graph = FastGraph()
    graph.add_node("n")
    child = graph["n"].graph
    ref = graph["n"]
    assert {thread.ident for thread in threading.enumerate()} == before
    root_ref = weakref.ref(graph)
    graph.close()
    graph.close()
    with pytest.raises(ClosedGraphError):
        child.add_node("bad")
    with pytest.raises(ClosedGraphError):
        graph.get_node("n")
    with pytest.raises(ClosedGraphError):
        _ = ref.attrs
    del graph
    gc.collect()
    assert root_ref() is None


def test_foreign_nodes_and_identifier_validation():
    graph = FastGraph()
    other = FastGraph()
    graph.add_node("a")
    foreign = other.add_node("b")
    with pytest.raises(ValidationError):
        graph.add_edge("a", foreign, "r")
    with pytest.raises(ValidationError):
        graph.add_node("")
    with pytest.raises(ValidationError):
        graph.add_node(1)


def test_mixed_local_and_cross_scope_batch_is_atomic_and_source_owned():
    graph = FastGraph()
    graph.add_nodes_batch([("a", {}), ("b", {}), ("owner", {})])
    child = graph["owner"].graph
    nested = child.add_node("a")
    ids = graph.add_edges_batch([("a", "b", "r"), ("b", nested, "r")])
    assert len(ids) == 2
    assert graph.edge_count == 2 and child.edge_count == 0
    with pytest.raises(NodeNotFoundError):
        graph.add_edges_batch([("a", nested, "new"), (nested, ("owner", "missing"), "new")])
    assert graph.edge_count == 2
    assert graph.get_edge("a", nested, "new") is None


def test_queries_are_consistent_with_and_without_unused_legacy_cache_settings():
    for size in (0, 128):
        graph = FastGraph(config={"memory": {"query_cache_size": size}})
        graph.add_node("a", kind="Person")
        assert graph.find_nodes(kind="Person") == [("a", {"kind": "Person"})]
        graph.update_node("a", kind="Company")
        assert graph.find_nodes(kind="Person") == []
        assert graph.find_nodes(kind="Company") == [("a", {"kind": "Company"})]


def test_relationship_property_queries_apply_all_predicates():
    graph = FastGraph()
    graph.add_nodes_batch([("a", {}), ("b", {}), ("c", {})])
    graph.add_edges_batch(
        [
            ("a", "b", "r", {"weight": 2}),
            ("a", "c", "r", {"weight": 3}),
            ("b", "c", "s", {"weight": 3}),
        ]
    )
    assert [edge.key() for edge in graph.find_edges(src="a", rel="r", weight__gte=3)] == [
        ("a", "c", "r")
    ]
    assert graph.remove_edge(rel="r", weight__lte=2) == 1
    assert graph.edge_count == 2


@given(
    st.lists(
        st.tuples(st.integers(0, 9), st.integers(0, 9), st.sampled_from(["r", "s"])), max_size=100
    )
)
@settings(max_examples=40, deadline=None)
def test_adjacency_matches_unique_edge_reference_model(edges):
    graph = FastGraph()
    graph.add_nodes_batch([(str(i), {}) for i in range(10)])
    graph.add_edges_batch([(str(src), str(dst), rel) for src, dst, rel in edges])
    expected = {(str(src), str(dst), rel) for src, dst, rel in edges}
    assert graph.edge_count == len(expected)
    for node in map(str, range(10)):
        assert {edge.key() for _, edge in graph.neighbors_out(node)} == {
            edge for edge in expected if edge[0] == node
        }
        assert graph.degree(node)[:2] == (
            sum(src == node for src, _, _ in expected),
            sum(dst == node for _, dst, _ in expected),
        )
    graph.remove_node("0")
    assert {edge.key() for edge in graph.find_edges()} == {
        edge for edge in expected if "0" not in edge[:2]
    }

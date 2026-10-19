"""Relationship identity is independent of the scope displaying it."""

import gc
import weakref

from fastgraph import FastGraph


def test_nested_relationship_identity_does_not_collapse_reused_local_names():
    graph = FastGraph()
    children = [graph.add_node(name).graph for name in ("first", "second")]
    edges = []
    for child in children:
        child.add_nodes_batch([("x", {}), ("y", {})])
        edges.append(child.add_edge("x", "y", "r"))
    assert edges[0].key() == edges[1].key()
    assert edges[0] != edges[1]
    assert len(set(edges)) == 2
    root_edge = graph.get_edge(("first", "x"), ("first", "y"), "r")
    assert root_edge == edges[0]
    assert hash(root_edge) == hash(edges[0])


def test_relationship_ids_from_different_stores_are_not_equal():
    graphs = [FastGraph(), FastGraph()]
    edges = []
    for graph in graphs:
        graph.add_nodes_batch([("x", {}), ("y", {})])
        edges.append(graph.add_edge("x", "y", "r"))
    assert edges[0].id == edges[1].id
    assert edges[0] != edges[1]


def test_detached_edge_identity_outlives_store_without_retaining_payload():
    graph = FastGraph()
    x, y = graph.add_nodes_batch([("x", {}), ("y", {})])
    edge = graph.add_edge(x, y, "r")
    identity = edge._identity[0]
    graph_ref = weakref.ref(graph)
    graph.close()
    del graph, x, y
    gc.collect()
    assert graph_ref() is None
    for _ in range(20):
        with FastGraph() as replacement:
            x, y = replacement.add_nodes_batch([("x", {}), ("y", {})])
            current = replacement.add_edge(x, y, "r")
            assert current._identity[0] is not identity
            assert current != edge


def test_batch_returns_compact_ids_without_property_hydration():
    graph = FastGraph()
    graph.add_nodes_batch([("x", {}), ("y", {})])
    ids = graph.add_edges_batch([("x", "y", "r", {"blob": "payload"})])
    assert len(ids) == 1 and type(ids[0]) is int
    assert graph.get_edge("x", "y", "r").id == ids[0]


def test_update_preserves_properties_named_like_endpoint_parameters():
    graph = FastGraph()
    x, y = graph.add_nodes_batch([("x", {}), ("y", {})])
    graph.add_edges_batch([(x, y, "r", {"src": "property", "dst": "property", "rel": "property"})])
    edge = graph.update_edge(x, y, "r", weight=2)
    assert dict(edge.attrs) == {
        "src": "property",
        "dst": "property",
        "rel": "property",
        "weight": 2,
    }

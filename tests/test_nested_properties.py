"""Differential properties for repeated local IDs and cross-scope topology."""

from hypothesis import given, settings, strategies as st

from fastgraph import FastGraph


@given(
    st.lists(
        st.tuples(
            st.integers(0, 3),
            st.integers(0, 2),
            st.integers(0, 3),
            st.integers(0, 2),
            st.sampled_from(["r", "s"]),
        ),
        max_size=80,
    )
)
@settings(max_examples=40, deadline=None)
def test_nested_topology_matches_qualified_reference_model(edges):
    graph = FastGraph()
    for owner in range(4):
        child = graph.add_node(f"p{owner}").graph
        child.add_nodes_batch([(f"n{local}", {}) for local in range(3)])

    expected = {
        ((f"p{src_scope}", f"n{src}"), (f"p{dst_scope}", f"n{dst}"), rel)
        for src_scope, src, dst_scope, dst, rel in edges
    }
    graph.add_edges_batch(list(expected))
    assert graph.edge_count == 0
    assert graph.stats(recursive=True)["nodes"] == 16
    assert {edge.key() for edge in graph.find_edges(recursive=True)} == expected
    for owner in range(4):
        child = graph[f"p{owner}"].graph
        assert child.edge_count == sum(src[0] == f"p{owner}" for src, _, _ in expected)
        for local in range(3):
            path = (f"p{owner}", f"n{local}")
            assert {node.path for node in graph.neighbor_nodes(path)} == {
                dst for src, dst, _ in expected if src == path
            }

    # Containment is a directed transition; entering a scope never implies exiting it.
    start = ("p0",)
    expected_arcs = {(src, dst) for src, dst, _ in expected}
    expected_arcs.update(
        ((f"p{owner}",), (f"p{owner}", f"n{local}")) for owner in range(4) for local in range(3)
    )
    reachable = {start}
    frontier = [start]
    while frontier:
        source = frontier.pop()
        for src, dst in expected_arcs:
            if src == source and dst not in reachable:
                reachable.add(dst)
                frontier.append(dst)
    assert {node.path for node in graph.bfs(start, nested=True).nodes} == reachable
    assert {node.path for node in graph.bfs(start).nodes} == {start}

    graph.remove_node("p0")
    remaining = {edge for edge in expected if edge[0][0] != "p0" and edge[1][0] != "p0"}
    assert {edge.key() for edge in graph.find_edges(recursive=True)} == remaining
    assert graph.stats(recursive=True)["nodes"] == 12
    graph.add_node("p0").graph.add_nodes_batch([(f"n{local}", {}) for local in range(3)])
    assert graph.stats(recursive=True)["nodes"] == 16
    assert {edge.key() for edge in graph.find_edges(recursive=True)} == remaining


def test_local_ids_are_opaque_and_tuple_paths_are_unambiguous():
    graph = FastGraph()
    compound = graph.add_node("with/slashes").graph
    node = compound.add_node("child/with/slash", value=1)
    assert graph.resolve(("with/slashes", "child/with/slash")) == node
    assert node.path == ("with/slashes", "child/with/slash")
    assert graph.get_node("with/slashes") == {}

"""Traversal correctness, lazy result storage, and induced selection contracts."""

import gc
import threading
import tracemalloc
import weakref
from collections import deque
from collections.abc import Mapping, Sequence

import pytest
from hypothesis import given, settings, strategies as st

from fastgraph import (
    ClosedGraphError,
    FastGraph,
    NodeNotFoundError,
    StaleReferenceError,
    SubgraphView,
    ValidationError,
)
from fastgraph.core import traversal
from fastgraph.core.traversal import TraversalOperations
from fastgraph.exceptions import TraversalError


@pytest.fixture
def graph():
    with FastGraph(config={}) as instance:
        yield instance


def paths(nodes):
    return tuple(node.path for node in nodes)


def locals_(nodes):
    return tuple(node.local_id for node in nodes)


def diamond(graph):
    graph.add_nodes_batch([(nid, {}) for nid in ("s", "a", "b", "t")])
    graph.add_edges_batch([("s", "a", "r"), ("s", "b", "r"), ("a", "t", "r"), ("b", "t", "r")])
    return graph.traversal_ops


def chain(graph, count):
    graph.add_nodes_batch([(str(i), {}) for i in range(count)])
    graph.add_edges_batch([(str(i), str(i + 1), "r") for i in range(count - 1)])


def test_directed_diamond_discovery_and_all_shortest_paths(graph):
    ops = diamond(graph)
    result = graph.bfs("s")
    assert isinstance(result.nodes, tuple)
    assert isinstance(result.edges, tuple)
    assert result.node_count == 4
    assert result.edge_count == 3
    assert result.depth == 2
    assert len(set(result.nodes)) == result.node_count
    assert {locals_(path) for path in ops.all_shortest_paths("s", "t")} == {
        ("s", "a", "t"),
        ("s", "b", "t"),
    }
    assert locals_(graph.shortest_path("s", "t")) in {("s", "a", "t"), ("s", "b", "t")}
    assert graph.shortest_path("t", "s") is None
    assert locals_(graph.shortest_path("t", "s", direction="in")) in {
        ("t", "a", "s"),
        ("t", "b", "s"),
    }
    assert locals_(result.path_to("t")) in {("s", "a", "t"), ("s", "b", "t")}
    assert result.node_paths == tuple(node.path for node in result.nodes)
    assert ops.all_shortest_paths("s", "t", max_depth=1) == []
    assert len(ops.all_shortest_paths("s", "t", max_paths=1)) == 1
    graph.add_node("disconnected")
    assert result.path_to("disconnected") is None


def test_all_shortest_paths_do_not_repeat_parallel_relationships(graph):
    ops = diamond(graph)
    graph.add_edge("s", "a", "second")
    graph.add_edge("a", "t", "second")
    found = [locals_(path) for path in ops.all_shortest_paths("s", "t")]
    assert len(found) == len(set(found)) == 2
    assert [locals_(path) for path in ops.all_shortest_paths("s", "t", rel="second")] == [
        ("s", "a", "t")
    ]


def test_duplicate_upsert_cannot_hide_a_cycle_in_topological_sort(graph):
    graph.add_nodes_batch([(nid, {}) for nid in ("s", "a", "b")])
    graph.add_edges_batch([("s", "a", "r"), ("s", "a", "r"), ("a", "b", "r"), ("b", "a", "r")])
    ops = graph.traversal_ops
    assert ops.topological_sort() is None
    assert ops.has_cycles()
    graph.remove_edge("b", "a", "r")
    order = ops.topological_sort()
    assert len(order) == len(set(order)) == 3
    assert locals_(order) == ("s", "a", "b")
    assert not ops.has_cycles()


def test_dfs_revisits_shorter_routes_with_a_depth_bound(graph):
    graph.add_nodes_batch([(nid, {}) for nid in ("s", "a", "b", "x", "y")])
    graph.add_edges_batch(
        [("s", "a", "r"), ("s", "x", "r"), ("a", "b", "r"), ("b", "x", "r"), ("x", "y", "r")]
    )
    result = graph.dfs("s", max_depth=3)
    assert set(locals_(result.nodes)) == {"s", "a", "b", "x", "y"}
    assert locals_(result.path_to("x")) == ("s", "x")
    assert locals_(result.path_to("y")) == ("s", "x", "y")
    assert result.depth == 2
    for node in result.nodes:
        path = result.path_to(node)
        assert len(path) - 1 == result._depths[node._id]
        assert len(path) <= 4
        assert len(set(path)) == len(path)


@pytest.mark.parametrize("method", ["bfs", "dfs"])
def test_traversal_depth_and_node_budgets(graph, method):
    chain(graph, 10)
    search = getattr(graph, method)
    assert locals_(search("0", max_depth=0).nodes) == ("0",)
    result = search("0", max_depth=3)
    assert set(locals_(result.nodes)) == {"0", "1", "2", "3"}
    assert result.depth == 3
    limited = search("0", max_nodes=2)
    assert limited.node_count == 2
    assert limited.edge_count == 1
    assert search("0", max_nodes=1).node_count == 1
    assert graph.shortest_path("0", "3", max_depth=2) is None
    assert len(graph.shortest_path("0", "3", max_depth=3)) == 4


@pytest.mark.parametrize("method", ["bfs", "dfs"])
@pytest.mark.parametrize(
    "options",
    [
        {"max_depth": -1},
        {"max_depth": True},
        {"max_depth": 1.5},
        {"max_nodes": 0},
        {"max_nodes": False},
        {"max_nodes": -1},
        {"direction": "sideways"},
        {"nested": 1},
        {"rel": 2},
        {"node_filter": 1},
        {"edge_filter": 1},
        {"filters": []},
    ],
)
def test_invalid_traversal_options_raise(graph, method, options):
    graph.add_node("s")
    with pytest.raises(ValueError):
        getattr(graph, method)("s", **options)


def test_bfs_chain_retains_only_predecessors_and_builds_paths_on_demand(graph, monkeypatch):
    count = 4096
    chain(graph, count)
    requested = []
    original = traversal._path_ids

    def track(predecessors, target):
        requested.append(target)
        return original(predecessors, target)

    monkeypatch.setattr(traversal, "_path_ids", track)
    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        result = graph.bfs("0")
        retained = tracemalloc.get_traced_memory()[0] - before
    finally:
        if not tracing:
            tracemalloc.stop()
    assert result.node_count == count
    assert result.edge_count == count - 1
    assert len(result._predecessors) == len(result._depths) == count
    assert retained < count * 3000
    assert requested == []
    lazy_paths = result.paths
    assert isinstance(lazy_paths, Sequence)
    assert not isinstance(lazy_paths, (list, tuple))
    assert len(lazy_paths) == result.path_count == count
    assert requested == []
    assert locals_(lazy_paths[0]) == ("0",)
    assert len(requested) == 1
    assert len(lazy_paths[-1]) == count
    assert len(requested) == 2
    assert [locals_(path) for path in lazy_paths[:2]] == [("0",), ("0", "1")]


def test_discovery_edges_copy_only_on_demand_and_cache_detached_values(graph, monkeypatch):
    chain(graph, 10)
    calls = []
    original = graph._edge_ref

    def hydrate(eid):
        calls.append(eid)
        return original(eid)

    monkeypatch.setattr(graph, "_edge_ref", hydrate)
    result = graph.bfs("0")
    assert calls == []
    assert result.edge_count == 9
    assert len(result.nodes) == 10
    assert calls == []
    copied = result.edges
    assert isinstance(copied, tuple)
    assert len(copied) == len(calls) == 9
    assert result.edges is copied
    assert len(calls) == 9
    graph.remove_edge("0", "1", "r")
    assert result.edges is copied
    assert result.edge_count == 9


def test_unread_discovery_edges_reject_a_changed_store(graph):
    chain(graph, 3)
    result = graph.bfs("0")
    graph.add_edge("0", "1", "r", changed=True)
    assert result.edge_count == 2
    with pytest.raises(TraversalError, match="changed"):
        _ = result.edges


def test_long_searches_and_path_enumeration_are_iterative(graph):
    count = 1200
    chain(graph, count)
    result = graph.dfs("0")
    assert result.depth == count - 1
    assert len(result.path_to(str(count - 1))) == count
    assert len(graph.traversal_ops.all_shortest_paths("0", str(count - 1))[0]) == count
    found = list(graph.traversal_ops.find_paths("0", str(count - 1), max_paths=1))
    assert len(found) == 1
    assert len(found[0]) == count


@pytest.mark.parametrize("method", ["bfs", "dfs"])
def test_nested_traversal_reaches_all_children_with_repeated_local_ids(graph, method):
    owner = graph.add_node("same")
    child = owner.graph
    repeated = child.add_node("same")
    child_leaf = child.add_node("leaf")
    grandchild = repeated.graph
    grand_repeat = grandchild.add_node("same")
    grand_leaf = grandchild.add_node("leaf")
    unrelated = graph.add_node("unrelated").graph.add_node("same")
    search = getattr(graph, method)
    assert search(owner).nodes == (owner,)
    result = search(owner, nested=True, rel="not-a-containment-type")
    assert set(result.nodes) == {owner, repeated, child_leaf, grand_repeat, grand_leaf}
    assert unrelated not in result.nodes
    assert len(set(result.node_paths)) == 5
    assert result.edge_count == 0
    assert result.depth == 2
    assert paths(result.path_to(grand_repeat)) == (
        ("same",),
        ("same", "same"),
        ("same", "same", "same"),
    )
    assert set(search(owner, nested=True, max_depth=1).nodes) == {owner, repeated, child_leaf}
    assert search(owner, nested=True, max_nodes=2).node_count == 2
    assert graph.shortest_path(owner, grand_leaf) is None
    assert paths(graph.shortest_path(owner, grand_leaf, nested=True)) == (
        ("same",),
        ("same", "same"),
        ("same", "same", "leaf"),
    )


def test_explicit_cross_scope_edges_work_without_implicit_descent(graph):
    outside = graph.add_node("outside")
    owner = graph.add_node("group")
    child = owner.graph
    inside, leaf = child.add_nodes_batch([("inside", {}), ("leaf", {})])
    graph.add_edge(outside, inside, "r")
    child.add_edge(inside, leaf, "r")
    result = graph.bfs(outside)
    assert result.nodes == (outside, inside, leaf)
    assert owner not in result.nodes
    assert paths(result.path_to(leaf)) == (("outside",), ("group", "inside"), ("group", "leaf"))
    assert paths(graph.shortest_path(outside, leaf)) == paths(result.path_to(leaf))
    assert graph.neighbors_out(outside)[0][0] == ("group", "inside")
    assert child.neighbors_in(inside)[0][0] == ("outside",)
    assert child.neighbors_out(inside)[0][0] == "leaf"
    assert graph.degree(outside) == (1, 0, 1)
    assert child.degree(inside) == (1, 1, 2)


def test_nested_direction_never_adds_an_unrequested_exit(graph):
    owner = graph.add_node("owner")
    outside = graph.add_node("outside")
    child = owner.graph
    x, y = child.add_nodes_batch([("x", {}), ("y", {})])
    child.add_edge(x, y, "r")
    graph.add_edge(owner, outside, "r")
    assert child.bfs(x, direction="in").nodes == (x,)
    assert set(child.bfs(x, nested=True, direction="out").nodes) == {x, y}
    assert set(child.bfs(x, nested=True, direction="in").nodes) == {x, owner}
    assert outside not in child.bfs(x, nested=True, direction="in").nodes
    assert set(child.bfs(x, nested=True, direction="both").nodes) == {x, y, owner, outside}
    assert child.shortest_path(x, outside, nested=True) is None
    assert child.shortest_path(x, owner, direction="in") is None
    assert child.shortest_path(x, owner, direction="in", nested=True) == [x, owner]


@pytest.mark.parametrize("method", ["bfs", "dfs"])
def test_filters_select_whole_store_and_callback_properties_are_detached(graph, method):
    start = graph.add_node("start", keep=False, values=[])
    owner = graph.add_node("owner", keep=False, values=[])
    child = owner.graph
    middle = child.add_node("middle", keep=True, values=[])
    end = graph.add_node("end", keep=True, values=[])
    blocked = graph.add_node("blocked", keep=False, values=[])
    graph.add_edges_batch([(start, middle, "r"), (middle, end, "r"), (start, blocked, "r")])
    seen = []

    def selected(key, attrs):
        seen.append(key)
        attrs["values"].append("detached")
        return attrs["keep"]

    result = getattr(graph, method)(start, node_filter=selected, filters={"keep": True})
    assert set(result.nodes) == {start, middle, end}
    assert ("owner", "middle") in seen
    assert "end" in seen
    assert owner not in result.nodes
    assert start.attrs["values"] == middle.attrs["values"] == end.attrs["values"] == []
    assert paths(result.path_to(end)) == (("start",), ("owner", "middle"), ("end",))
    assert graph.bfs(start, node_filter=lambda key, attrs: False).nodes == (start,)
    assert graph.shortest_path(start, end, filters={"keep": True}) == [start, middle, end]
    assert child.shortest_path(middle, end, filters={"keep": True}) == [middle, end]


def test_edge_callbacks_filter_real_edges_but_not_containment(graph):
    ops = diamond(graph)
    result = ops.bfs("s", edge_filter=lambda edge: edge.dst != "a")
    assert set(locals_(result.nodes)) == {"s", "b", "t"}
    assert result.edge_count == 2
    assert locals_(ops.shortest_path("s", "t", edge_filter=lambda edge: edge.dst != "a")) == (
        "s",
        "b",
        "t",
    )
    owner = graph.add_node("owner")
    child = owner.graph.add_node("child")
    assert set(ops.bfs(owner, nested=True, rel="absent", edge_filter=lambda edge: False).nodes) == {
        owner,
        child,
    }


def test_callback_failures_and_mutations_are_explicit(graph):
    diamond(graph)

    def failure(edge):
        raise RuntimeError("predicate failed")

    with pytest.raises(TraversalError, match="predicate failed"):
        graph.bfs("s", edge_filter=failure)

    def mutation(edge):
        graph.add_node("side-effect")
        return True

    with pytest.raises(TraversalError, match="changed"):
        graph.bfs("s", edge_filter=mutation)


def test_components_and_topology_are_restricted_to_scope(graph):
    a, b, owner = graph.add_nodes_batch([("a", {}), ("b", {}), ("owner", {})])
    inside = owner.graph.add_node("inside")
    graph.add_edges_batch([(a, inside, "r"), (inside, b, "r")])
    ops = graph.traversal_ops
    assert {frozenset(component) for component in ops.connected_components()} == {
        frozenset({a}),
        frozenset({b}),
        frozenset({owner}),
    }
    assert {
        frozenset(component)
        for component in ops.connected_components(edge_filter=lambda edge: True)
    } == {frozenset({a}), frozenset({b}), frozenset({owner})}
    assert {frozenset(component) for component in ops.connected_components(recursive=True)} == {
        frozenset({a, inside, b}),
        frozenset({owner}),
    }
    graph.add_edge(inside, a, "r")
    assert not ops.has_cycles()
    assert ops.has_cycles(recursive=True)
    assert ops.topological_sort(recursive=True) is None
    assert {frozenset(component) for component in ops.weakly_connected_components()} == {
        frozenset({a}),
        frozenset({b}),
        frozenset({owner}),
    }


def test_find_paths_returns_unique_simple_paths_and_honors_depth(graph):
    ops = diamond(graph)
    graph.add_edge("a", "s", "cycle")
    graph.add_edge("s", "a", "parallel")
    found = [locals_(path) for path in ops.find_paths("s", "t")]
    assert set(found) == {("s", "a", "t"), ("s", "b", "t")}
    assert len(found) == len(set(found)) == 2
    assert list(ops.find_paths("s", "t", max_depth=1)) == []
    assert len(list(ops.find_paths("s", "t", max_depth=2))) == 2
    assert list(ops.find_paths("s", "t", max_length=2)) == []
    assert len(list(ops.find_paths("s", "t", max_length=3))) == 2
    assert len(list(ops.find_paths("s", "t", max_paths=1))) == 1
    assert [locals_(path) for path in ops.find_paths("s", "s", max_depth=0)] == [("s",)]
    assert list(ops.find_paths("s", "s", max_length=0)) == []


@pytest.mark.parametrize("option", ["max_paths", "max_expansions"])
@pytest.mark.parametrize("invalid", [0, -1, False, 1.5, None])
def test_path_budgets_reject_invalid_values(graph, option, invalid):
    graph.add_node("s")
    with pytest.raises(ValueError):
        graph.traversal_ops.find_paths("s", "s", **{option: invalid})
    if option == "max_paths":
        with pytest.raises(ValueError):
            graph.traversal_ops.all_shortest_paths("s", "s", max_paths=invalid)


def test_path_expansion_budget_is_not_silently_treated_as_complete(graph):
    chain(graph, 5)
    with pytest.raises(TraversalError, match="expansion budget"):
        list(graph.traversal_ops.find_paths("0", "4", max_expansions=2))
    assert len(list(graph.traversal_ops.find_paths("0", "4", max_expansions=4))) == 1


def test_default_path_cap_bounds_exponential_output(graph):
    graph.add_node("s")
    previous = ["s"]
    for depth in range(11):
        current = [f"{depth}a", f"{depth}b"]
        graph.add_nodes_batch([(nid, {}) for nid in current])
        graph.add_edges_batch([(src, dst, "r") for src in previous for dst in current])
        previous = current
    graph.add_node("t")
    graph.add_edges_batch([(src, "t", "r") for src in previous])
    assert len(graph.traversal_ops.all_shortest_paths("s", "t")) == 1000
    assert len(list(graph.traversal_ops.find_paths("s", "t"))) == 1000


def test_path_generator_releases_lock_and_detects_inter_yield_mutation(graph):
    ops = diamond(graph)
    iterator = ops.find_paths("s", "t")
    assert len(next(iterator)) == 3
    completed = threading.Event()
    errors = []

    def mutate():
        try:
            graph.add_node("concurrent")
        except Exception as exc:
            errors.append(exc)
        finally:
            completed.set()

    worker = threading.Thread(target=mutate, daemon=True)
    worker.start()
    try:
        assert completed.wait(2), "find_paths retained the graph lock while suspended"
        assert errors == []
        with pytest.raises(TraversalError, match="changed"):
            next(iterator)
    finally:
        iterator.close()
        worker.join(2)
    assert not worker.is_alive()


def test_view_is_fixed_read_only_and_cannot_traverse_through_excluded_nodes(graph):
    a, b, excluded = graph.add_nodes_batch(
        [
            ("a", {"keep": True, "values": [1]}),
            ("b", {"keep": True}),
            ("excluded", {"keep": False}),
        ]
    )
    graph.add_edges_batch([(a, b, "r"), (a, excluded, "r"), (excluded, b, "r")])
    view = graph.create_subgraph_view("selection", keep=True)
    nodes = view.nodes
    assert isinstance(nodes, Mapping)
    assert set(nodes) == {"a", "b"}
    with pytest.raises(TypeError):
        nodes["new"] = {}
    nodes["a"]["values"].append(2)
    assert a.attrs["values"] == [1]
    assert view.node_count == 2
    assert view.edge_count == 1
    assert view.stats() == {"nodes": 2, "edges": 1, "avg_degree": 1.0, "density": 0.5}
    assert view.neighbors_out(a)[0][0] == "b"
    assert view.neighbors_in(b)[0][0] == "a"
    assert view.degree(a) == (1, 0, 1)
    assert view.bfs(a).nodes == (a, b)
    assert view.shortest_path(a, b) == [a, b]
    graph.update_node(a, keep=False)
    graph.update_node(excluded, keep=True)
    graph.add_node("newly-selected", keep=True)
    assert set(nodes) == set(view) == {"a", "b"}
    assert view.get_node(a)["keep"] is False
    assert len(view.get_edges_between(a, b)) == 1
    assert len(view.get_node_edges(a)) == 1
    assert view.get_neighbors(a) == ["b"]
    graph.remove_edge(a, b, "r")
    assert graph.shortest_path(a, b) == [a, excluded, b]
    assert view.shortest_path(a, b) is None
    assert view.bfs(a).nodes == (a,)
    with pytest.raises(NodeNotFoundError):
        view.bfs(excluded)
    with pytest.raises(NodeNotFoundError):
        view.shortest_path(a, excluded)


def test_view_counts_and_membership_follow_deletion_and_clear_without_reselecting(graph):
    a, b = graph.add_nodes_batch([("a", {"keep": True}), ("b", {"keep": True})])
    graph.add_edge(a, b, "r")
    view = graph.create_subgraph_view("selection", keep=True)
    mapping = view.nodes
    graph.remove_node(a)
    assert view.node_count == len(mapping) == len(view) == 1
    assert view.edge_count == 0
    assert not view.contains_node(a)
    assert not view.contains_node("a")
    assert view.contains_node(b)
    with pytest.raises(KeyError):
        _ = mapping["a"]
    replacement = graph.add_node("a", keep=True)
    assert replacement != a
    assert not view.contains_node(replacement)
    assert not view.contains_node("a")
    assert set(view) == {"b"}
    graph.clear()
    assert view.node_count == view.edge_count == len(mapping) == 0
    assert list(view) == []
    assert view.stats() == {"nodes": 0, "edges": 0, "avg_degree": 0.0, "density": 0.0}
    graph.add_node("b", keep=True)
    assert view.node_count == 0
    assert view.is_connected()
    assert view.find_components() == []


def test_nested_view_membership_forbids_implicit_and_explicit_exits(graph):
    owner = graph.add_node("owner")
    children = owner.graph
    child, sibling = children.add_nodes_batch([("child", {}), ("sibling", {})])
    grandchild = child.graph.add_node("child")
    graph.add_edge(child, sibling, "r")
    selection = {owner._id, child._id}
    view = SubgraphView(graph, selection)
    selection.clear()
    assert view.node_count == 2
    assert set(view.bfs(owner, nested=True).nodes) == {owner, child}
    assert view.shortest_path(owner, child, nested=True) == [owner, child]
    assert view.shortest_path(owner, child) is None
    assert not view.contains_node(grandchild)
    assert view.neighbors_out(child) == []
    assert view.is_connected() is False
    assert {frozenset(component) for component in view.find_components()} == {
        frozenset({"owner"}),
        frozenset({("owner", "child")}),
    }


def test_view_enumerates_only_selected_outgoing_adjacency(graph):
    graph.add_nodes_batch([(str(i), {}) for i in range(100)])
    graph.add_edges_batch([(str(i), str(i + 1), "r") for i in range(99)])
    selected = [graph["0"], graph["1"]]
    view = SubgraphView(graph, selected)
    original = graph._state.store
    called = []

    class AdjacencySpy:
        def neighbors(self, nid, *args, **kwargs):
            called.append(nid)
            return original.neighbors(nid, *args, **kwargs)

        def edge_ids(self, *args, **kwargs):
            raise AssertionError("A view must not enumerate all parent edges")

        def __getattr__(self, key):
            return getattr(original, key)

    graph._state.store = AdjacencySpy()
    try:
        assert [edge.key() for edge in view.edges] == [("0", "1", "r")]
        assert set(called) == {node._id for node in selected}
        assert view.edge_count == 1
    finally:
        graph._state.store = original


def test_view_weak_parent_does_not_retain_the_graph():
    parent = FastGraph(config={})
    parent.add_node("a")
    view = SubgraphView(parent, [parent["a"]])
    reference = weakref.ref(parent)
    del parent
    gc.collect()
    assert reference() is None
    with pytest.raises(TraversalError, match="garbage collected"):
        _ = view.node_count


def test_rollback_invalidates_result_node_handles_and_selection(graph):
    graph.add_node("a")
    result = graph.bfs("a")
    view = graph.create_subgraph_view("selection")
    with pytest.raises(RuntimeError):
        with graph.transaction():
            graph.add_node("rolled-back")
            raise RuntimeError("rollback")
    assert "rolled-back" not in graph
    with pytest.raises(StaleReferenceError):
        _ = result.nodes[0].attrs
    with pytest.raises(TraversalError, match="invalidated"):
        result.path_to("a")
    with pytest.raises(TraversalError, match="invalidated"):
        _ = view.node_count


def test_deleted_handles_and_closed_graphs_are_not_traversed(graph):
    chain(graph, 3)
    result = graph.bfs("0")
    removed = result.nodes[1]
    view = SubgraphView(graph, result.nodes)
    graph.remove_node(removed)
    with pytest.raises(NodeNotFoundError):
        _ = removed.attrs
    with pytest.raises(NodeNotFoundError):
        graph.bfs(removed)
    with pytest.raises(NodeNotFoundError):
        result.path_to("2")
    assert view.node_count == 2
    graph.close()
    with pytest.raises(ClosedGraphError):
        graph.bfs("0")
    with pytest.raises(ClosedGraphError):
        _ = view.node_count
    with pytest.raises(ClosedGraphError):
        _ = result.nodes[0].path


def test_load_invalidates_traversal_results_and_existing_view_mappings(graph, tmp_path):
    chain(graph, 3)
    result = graph.bfs("0")
    view = graph.create_subgraph_view("selection")
    mapping = view.nodes
    saved = graph.save(tmp_path / "graph.json", format="json", durable=False)
    graph.clear()
    assert view.node_count == 0
    graph.load(saved)
    assert graph.node_count == 3
    with pytest.raises(StaleReferenceError):
        _ = result.nodes[0].attrs
    with pytest.raises(TraversalError, match="invalidated"):
        result.path_to("2")
    with pytest.raises(TraversalError, match="invalidated"):
        _ = view.edge_count
    with pytest.raises(TraversalError, match="invalidated"):
        _ = mapping["0"]


def test_missing_and_foreign_endpoints_use_facade_exceptions(graph):
    graph.add_node("a")
    ops = TraversalOperations(graph)
    with pytest.raises(NodeNotFoundError):
        ops.neighbors_out("missing")
    with pytest.raises(NodeNotFoundError):
        ops.shortest_path("a", "missing")
    with pytest.raises(NodeNotFoundError):
        ops.all_shortest_paths("missing", "a")
    with pytest.raises(NodeNotFoundError):
        ops.find_paths("a", "missing")
    with FastGraph(config={}) as other:
        foreign = other.add_node("a")
        with pytest.raises(ValidationError):
            ops.bfs(foreign)


@given(
    edges=st.lists(st.tuples(st.integers(0, 7), st.integers(0, 7)), max_size=35),
    direction=st.sampled_from(["out", "in", "both"]),
    max_depth=st.integers(0, 7),
)
@settings(max_examples=40, deadline=None)
def test_bounded_dfs_and_bfs_match_reference_reachability(edges, direction, max_depth):
    adjacency = {nid: set() for nid in range(8)}
    for src, dst in edges:
        if direction in ("out", "both"):
            adjacency[src].add(dst)
        if direction in ("in", "both"):
            adjacency[dst].add(src)
    distances = {0: 0}
    queue = deque([0])
    while queue:
        current = queue.popleft()
        if distances[current] >= max_depth:
            continue
        for neighbor in adjacency[current]:
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    with FastGraph(config={}) as graph:
        graph.add_nodes_batch([(str(nid), {}) for nid in range(8)])
        graph.add_edges_batch([(str(src), str(dst), "r") for src, dst in edges])
        for search in (graph.bfs, graph.dfs):
            result = search("0", direction=direction, max_depth=max_depth)
            assert set(map(int, locals_(result.nodes))) == set(distances)
            for node in result.nodes:
                path = list(map(int, locals_(result.path_to(node))))
                assert path[0] == 0
                assert len(path) - 1 == distances[path[-1]] == result._depths[node._id]
                assert all(dst in adjacency[src] for src, dst in zip(path, path[1:]))

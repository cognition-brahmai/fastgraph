"""Direct extension boundary and malformed snapshot checks."""

import json

import pytest

from fastgraph._native import NativeStore


def test_native_batch_failures_leave_store_unchanged():
    store = NativeStore()
    a, b = store.add_nodes(0, [("a", {}), ("b", {})])
    before = store.snapshot()
    with pytest.raises((KeyError, ValueError)):
        store.add_edges([(a, b, "r", {}), (a, 9999, "r", {})])
    assert store.snapshot() == before
    with pytest.raises((ValueError, TypeError)):
        store.add_nodes(0, [("valid", {}), ("invalid", {"object": object()})])
    assert store.snapshot() == before


def test_native_properties_roundtrip_bool_int_float_and_signed_integer_limits():
    store = NativeStore()
    attrs = {
        "bool": True,
        "int": 1,
        "float": 1.0,
        "minimum": -(2**63),
        "maximum": 2**63 - 1,
        "nested": {"list": [None, False, "text", 1]},
    }
    (node,) = store.add_nodes(0, [("n", attrs)])
    loaded = NativeStore.from_snapshot(store.snapshot())
    result = loaded.get_node(node)
    assert result == attrs
    assert type(result["float"]) is float
    assert type(result["int"]) is int
    assert type(result["bool"]) is bool
    for value in (2**63, -(2**63) - 1, float("nan"), float("inf"), {1}, b"bytes"):
        with pytest.raises((ValueError, TypeError, OverflowError)):
            store.add_nodes(0, [("bad", {"value": value})])
    assert store.node_id(0, "bad") is None


def test_native_predecessors_are_linear_and_containment_is_not_a_fake_edge():
    store = NativeStore()
    (owner,) = store.add_nodes(0, [("owner", {})])
    scope = store.create_scope(owner)
    (child,) = store.add_nodes(scope, [("child", {})])
    result = store.bfs(owner, nested=True)
    nodes, parents, depths, edges = result
    assert nodes == [owner, child]
    assert parents == [None, owner]
    assert depths == [0, 1]
    assert edges == [None, None]
    assert store.edge_ids(0, recursive=True) == []
    assert store.bfs(child, direction="out", nested=True)[0] == [child]
    assert store.bfs(child, direction="in", nested=True)[0] == [child, owner]


def test_native_reused_names_never_reuse_stale_integer_identity():
    store = NativeStore()
    (old,) = store.add_nodes(0, [("n", {})])
    old_scope = store.create_scope(old)
    store.remove_node(old)
    (current,) = store.add_nodes(0, [("n", {})])
    current_scope = store.create_scope(current)
    assert current > old
    assert current_scope > old_scope
    loaded = NativeStore.from_snapshot(store.snapshot())
    loaded.remove_node(current)
    (future,) = loaded.add_nodes(0, [("n", {})])
    assert future > current


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(version=999),
        lambda data: data["nodes"].append(dict(data["nodes"][0])),
        lambda data: data["edges"][0].update(dst=999999),
        lambda data: data["nodes"][0].update(child_scope=999999),
        lambda data: data.update(next_node_id=0),
        lambda data: data["scopes"][0].update(owner=0),
        lambda data: data["scopes"].append({"id": 10, "owner": None, "indexes": []}),
    ],
)
def test_native_snapshot_rejects_invalid_references_and_hierarchy(mutate):
    store = NativeStore()
    a, b = store.add_nodes(0, [("a", {}), ("b", {})])
    store.add_edges([(a, b, "r", {})])
    data = json.loads(store.snapshot())
    mutate(data)
    with pytest.raises(ValueError):
        NativeStore.from_snapshot(json.dumps(data).encode())


def test_native_indexes_roundtrip_as_definitions_and_keep_maintaining():
    store = NativeStore()
    (a,) = store.add_nodes(0, [("a", {"type": "old"})])
    store.create_index(0, "type")
    loaded = NativeStore.from_snapshot(store.snapshot())
    loaded.add_nodes(0, [("a", {"type": "new"}), ("b", {"type": "new"})])
    assert loaded.find_nodes(0, [("type", "eq", "old")]) == []
    assert loaded.find_nodes(0, [("type", "eq", "new")])[0] == a
    assert len(loaded.find_nodes(0, [("type", "eq", "new")])) == 2

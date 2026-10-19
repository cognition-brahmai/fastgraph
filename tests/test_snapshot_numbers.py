"""Lexical JSON numbers retain the engine's typed property semantics."""

import json

import pytest

from fastgraph._native import NativeStore


@pytest.mark.parametrize(
    "literal,expected_type",
    [
        ("0", int),
        ("-0", int),
        ("0.0", float),
        ("-0.0", float),
        ("-0e0", float),
    ],
)
def test_json_zero_keeps_integer_and_float_types(literal, expected_type):
    store = NativeStore()
    (node,) = store.add_nodes(
        0, [("n", {"p": "TOKEN", "nested": {"values": ["TOKEN"]}, "text": "-0 stays text"})]
    )
    payload = store.snapshot().replace(json.dumps("TOKEN").encode(), literal.encode())
    loaded = NativeStore.from_snapshot(payload)
    attrs = loaded.get_node(node)
    assert type(attrs["p"]) is expected_type
    assert type(attrs["nested"]["values"][0]) is expected_type
    assert attrs["text"] == "-0 stays text"
    integer_ids = loaded.find_nodes(0, [("p", "eq", 0)])
    float_ids = loaded.find_nodes(0, [("p", "eq", 0.0)])
    assert integer_ids == ([node] if expected_type is int else [])
    assert float_ids == ([node] if expected_type is float else [])


@pytest.mark.parametrize("depth", [63, 64, 65])
def test_python_and_snapshot_property_depth_limits_agree(depth):
    value = None
    for _ in range(depth):
        value = [value]
    store = NativeStore()
    if depth <= 63:
        (node,) = store.add_nodes(0, [("n", {"p": value})])
        loaded = NativeStore.from_snapshot(store.snapshot())
        loaded.add_nodes(0, [("n", loaded.get_node(node))])
        assert loaded.get_node(node) == {"p": value}
    else:
        with pytest.raises(ValueError, match="nesting"):
            store.add_nodes(0, [("n", {"p": value})])
        store.add_nodes(0, [("n", {"p": "TOKEN"})])
        payload = store.snapshot().replace(json.dumps("TOKEN").encode(), json.dumps(value).encode())
        with pytest.raises(ValueError, match="nesting"):
            NativeStore.from_snapshot(payload)

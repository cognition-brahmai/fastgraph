"""Persistence contracts, atomic failures, bounded codecs, and graph round trips."""

from __future__ import annotations

import errno
import gzip
import io
import json
import os
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import msgpack
import pytest

from fastgraph import FastGraph
from fastgraph._native import NativeStore
from fastgraph.config.manager import ConfigManager
from fastgraph.core import persistence
from fastgraph.core.persistence import PersistenceManager, detect_format
from fastgraph.exceptions import PersistenceError


@pytest.fixture
def envelope():
    return {
        "format": "fastgraph",
        "version": 3,
        "metadata": {"name": "snapshot", "created_at": 1720000000.25},
        "store": {
            "version": 1,
            "revision": 0,
            "next_node_id": 1,
            "next_edge_id": 0,
            "next_scope_id": 1,
            "scopes": [{"id": 0, "owner": None, "indexes": ["type"]}],
            "nodes": [
                {
                    "id": 0,
                    "scope": 0,
                    "local_id": "a",
                    "child_scope": None,
                    "attrs": {"type": "Person", "nested": {"items": [1, True, None]}},
                }
            ],
            "edges": [],
        },
    }


@pytest.fixture
def nested_graph(tmp_path):
    graph = FastGraph(name="nested", config={"storage": {"data_dir": str(tmp_path)}})
    graph.add_node("company", type="Company")
    graph.add_node("outside", type="Person", payload={"text": "caf\u00e9", "values": [1, None]})
    graph.add_node("empty")
    graph["empty"].graph
    child = graph["company"].graph
    child.add_node("alice", type="Person", age=31, profile={"active": True, "tags": ["a", "b"]})
    child.add_node("team", type="Team")
    grandchild = child["team"].graph
    grandchild.add_node("alice", type="Person", age=12)
    graph.build_node_index("type")
    child.build_node_index("type")
    grandchild.build_node_index("age")
    child.add_edge(child["alice"], graph["outside"], "KNOWS", weight=2, attrs={"src": "property"})
    grandchild.add_edge(grandchild["alice"], child["alice"], "REPORTS_TO", weight=3)
    graph.add_edge(graph["company"], grandchild["alice"], "HAS_MEMBER", active=True)
    yield graph
    graph.close()


def _write_encoded(path, data, format, compress=False):
    payload = (
        json.dumps(data).encode("utf-8")
        if format == "json"
        else msgpack.packb(data, use_bin_type=True)
    )
    path.write_bytes(gzip.compress(payload, mtime=0) if compress else payload)


@pytest.mark.parametrize("format", ["json", "msgpack"])
@pytest.mark.parametrize("compress", [False, True])
def test_exact_envelope_round_trip(tmp_path, envelope, format, compress):
    manager = PersistenceManager()
    path = tmp_path / f"snapshot.{format}"
    original = deepcopy(envelope)
    assert manager.save(envelope, str(path), format=format, compress=compress) == path
    assert path.is_file()
    assert path.read_bytes().startswith(b"\x1f\x8b") is compress
    assert manager.load(path) == original
    assert manager.load(str(path), format=format) == original
    assert envelope == original


@pytest.mark.parametrize("format", ["json", "msgpack"])
@pytest.mark.parametrize("compress", [False, True])
def test_nested_cross_scope_graph_round_trip(tmp_path, nested_graph, format, compress):
    graph = nested_graph
    before = graph.snapshot()
    path = tmp_path / f"hierarchy.{format}"
    assert graph.save(path, compress=compress) == path
    loaded = FastGraph.from_file(path)
    try:
        assert loaded.snapshot() == before
        assert loaded.name == "nested"
        assert loaded.resolve(("company", "alice")).path == ("company", "alice")
        assert loaded.resolve(("company", "team", "alice")).attrs == {"type": "Person", "age": 12}
        assert loaded["empty"].is_compound
        assert loaded["empty"].graph.node_count == 0
        child = loaded["company"].graph
        assert child.get_edge(child["alice"], loaded["outside"], "KNOWS").attrs["weight"] == 2
        assert loaded.get_edge(
            loaded["company"], loaded.resolve(("company", "team", "alice")), "HAS_MEMBER"
        )
        assert child.get_edge(child["alice"], loaded["outside"], "KNOWS").attrs["attrs"] == {
            "src": "property"
        }
        assert loaded.stats(recursive=True)["nodes"] == 6
        assert loaded.stats(recursive=True)["edges"] == 3
        assert dict(child.find_nodes(type="Person")) == {
            "alice": {"type": "Person", "age": 31, "profile": {"active": True, "tags": ["a", "b"]}}
        }
        child.add_node("bob", type="Person")
        child.update_node("alice", type="Robot")
        assert dict(child.find_nodes(type="Person")) == {"bob": {"type": "Person"}}
        assert set(dict(loaded.find_nodes(recursive=True, type="Person"))) == {
            ("outside",),
            ("company", "bob"),
            ("company", "team", "alice"),
        }
    finally:
        loaded.close()


def test_loading_replaces_existing_graph(tmp_path, nested_graph):
    path = nested_graph.save(tmp_path / "replacement.msgpack")
    loaded = FastGraph(name="old")
    loaded.add_node("old")
    try:
        assert loaded.load(path) == path
        assert loaded.snapshot() == nested_graph.snapshot()
        assert "old" not in loaded
    finally:
        loaded.close()


def test_child_save_captures_whole_store(tmp_path, nested_graph):
    path = nested_graph["company"].graph.save(tmp_path / "child.msgpack")
    assert PersistenceManager().load(path) == nested_graph.snapshot()


@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_failed_serialization_does_not_touch_target_or_make_parents(tmp_path, envelope, format):
    manager = PersistenceManager()
    path = tmp_path / f"original.{format}"
    manager.save(envelope, path, format=format)
    original = path.read_bytes()
    invalid = deepcopy(envelope)
    invalid["metadata"]["unsupported"] = object()
    with pytest.raises(PersistenceError, match="JSON values only"):
        manager.save(invalid, path, format=format)
    assert path.read_bytes() == original
    missing = tmp_path / "missing" / "subdir" / f"graph.{format}"
    with pytest.raises(PersistenceError):
        manager.save(invalid, missing, format=format)
    assert not (tmp_path / "missing").exists()
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("codec", ["json", "msgpack", "gzip"])
def test_codec_failure_occurs_before_any_filesystem_change(tmp_path, envelope, monkeypatch, codec):
    manager = PersistenceManager()
    path = manager.save(envelope, tmp_path / "original.msgpack")
    original = path.read_bytes()

    def fail(*args, **kwargs):
        raise ValueError("injected codec failure")

    module, function = {
        "json": (persistence.json, "dumps"),
        "msgpack": (persistence.msgpack, "packb"),
        "gzip": (persistence.gzip, "compress"),
    }[codec]
    monkeypatch.setattr(module, function, fail)
    format = "json" if codec == "json" else "msgpack"
    for target in (path, tmp_path / "missing" / "graph.msgpack"):
        with pytest.raises(PersistenceError, match="injected codec"):
            manager.save(envelope, target, format=format, compress=codec == "gzip")
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "failure", ["mkstemp", "fdopen", "write", "short_write", "flush", "fsync", "replace"]
)
def test_save_failures_preserve_original_and_cleanup(tmp_path, envelope, monkeypatch, failure):
    manager = PersistenceManager()
    path = manager.save(envelope, tmp_path / "original.msgpack")
    original = path.read_bytes()
    replacement = deepcopy(envelope)
    replacement["metadata"]["name"] = "replacement"
    real_fdopen = os.fdopen

    def fail(*args, **kwargs):
        raise OSError(f"injected {failure} failure")

    if failure in {"write", "short_write", "flush"}:

        class FailingStream:
            def __init__(self, fd, mode):
                self.stream = real_fdopen(fd, mode)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def write(self, data):
                if failure == "write":
                    self.stream.write(data[:10])
                    fail()
                if failure == "short_write":
                    return self.stream.write(data[:10])
                return self.stream.write(data)

            def flush(self):
                fail()

            def fileno(self):
                return self.stream.fileno()

        monkeypatch.setattr(persistence.os, "fdopen", FailingStream)
    else:
        owner = persistence.tempfile if failure == "mkstemp" else persistence.os
        name = "replace" if failure == "replace" else failure
        monkeypatch.setattr(owner, name, fail)
    with pytest.raises(
        PersistenceError, match="Incomplete" if failure == "short_write" else "injected"
    ):
        manager.save(replacement, path)
    assert path.read_bytes() == original
    assert manager.load(path) == envelope
    assert list(tmp_path.iterdir()) == [path]


def test_durable_flush_fsync_and_replace_order(tmp_path, envelope, monkeypatch):
    events = []
    real_fdopen, real_fsync, real_replace = os.fdopen, os.fsync, os.replace

    class TrackedStream:
        def __init__(self, fd, mode):
            self.stream = real_fdopen(fd, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            events.append("write")
            return self.stream.write(data)

        def flush(self):
            events.append("flush")
            return self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    def fsync(fd):
        events.append("fsync")
        real_fsync(fd)

    def replace(source, target):
        events.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(persistence.os, "fdopen", TrackedStream)
    monkeypatch.setattr(persistence.os, "fsync", fsync)
    monkeypatch.setattr(persistence.os, "replace", replace)
    PersistenceManager().save(envelope, tmp_path / "durable.msgpack")
    expected = ["write", "flush", "fsync", "replace"]
    assert events == expected + (["fsync"] if os.name == "posix" else [])


def test_nondurable_save_still_atomically_publishes(tmp_path, envelope, monkeypatch):
    def unexpected_fsync(fd):
        pytest.fail("durable=False must not request fsync")

    monkeypatch.setattr(persistence.os, "fsync", unexpected_fsync)
    manager = PersistenceManager()
    path = manager.save(envelope, tmp_path / "snapshot.msgpack", durable=False)
    assert manager.load(path) == envelope
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("durable", [False, True])
def test_overlapping_saves_each_publish_a_complete_snapshot(
    tmp_path, envelope, monkeypatch, durable
):
    manager = PersistenceManager()
    path = manager.save(envelope, tmp_path / "shared.msgpack")
    workers = 6
    barrier = threading.Barrier(workers)
    real_replace = os.replace
    published, temporary_names = [], []
    seen, guard = set(), threading.Lock()
    snapshots = []
    for writer in range(workers):
        snapshot = deepcopy(envelope)
        snapshot["metadata"].update(
            name=f"writer-{writer}", writer=writer, payload=str(writer) * 2000
        )
        snapshots.append(snapshot)

    def replace(source, target):
        assert Path(source).parent == Path(target).parent
        candidate = manager.load(source)
        assert candidate in snapshots
        with guard:
            first_attempt = source not in seen
            if first_attempt:
                seen.add(source)
                temporary_names.append(Path(source).name)
        if first_attempt:
            barrier.wait(timeout=15)
        real_replace(source, target)
        published.append(candidate)

    monkeypatch.setattr(persistence.os, "replace", replace)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(
            executor.map(lambda snapshot: manager.save(snapshot, path, durable=durable), snapshots)
        )
    assert results == [path] * workers
    assert len(set(temporary_names)) == workers
    assert len(published) == workers
    assert all(snapshot in snapshots for snapshot in published)
    assert manager.load(path) in snapshots
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name != "nt", reason="Windows replacement sharing violations")
@pytest.mark.parametrize("persistent", [False, True])
def test_windows_replace_retries_are_bounded_and_never_unlink_target(
    tmp_path, envelope, monkeypatch, persistent
):
    manager = PersistenceManager()
    path = manager.save(envelope, tmp_path / "existing.msgpack")
    original = path.read_bytes()
    replacement = deepcopy(envelope)
    replacement["metadata"]["name"] = "replacement"
    calls, delays = [], []
    real_replace = os.replace

    def replace(source, target):
        calls.append(source)
        if persistent or len(calls) <= 2:
            error = PermissionError(errno.EACCES, "injected sharing violation")
            error.winerror = 32
            raise error
        real_replace(source, target)

    monkeypatch.setattr(persistence.os, "replace", replace)
    monkeypatch.setattr(persistence.time, "sleep", delays.append)
    if persistent:
        with pytest.raises(PersistenceError, match="injected sharing"):
            manager.save(replacement, path)
        assert len(calls) == 10 and len(delays) == 9
        assert path.read_bytes() == original
    else:
        assert manager.save(replacement, path) == path
        assert len(calls) == 3 and len(delays) == 2
        assert manager.load(path) == replacement
    assert len(set(calls)) == 1
    assert all(0 < delay <= 0.05 for delay in delays)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("format", ["json", "msgpack"])
@pytest.mark.parametrize("compress", [False, True])
def test_truncated_corrupt_and_trailing_data_rejected(tmp_path, envelope, format, compress):
    manager = PersistenceManager()
    path = manager.save(envelope, tmp_path / f"corrupt.{format}", format=format, compress=compress)
    original = path.read_bytes()
    for payload in (
        b"",
        original[:-1],
        original[: len(original) // 2],
        b"not a snapshot",
        original + b"invalid trailing data",
    ):
        path.write_bytes(payload)
        with pytest.raises(PersistenceError):
            manager.load(path)
    if compress:
        damaged = bytearray(original)
        damaged[-8] ^= 1
        path.write_bytes(damaged)
        with pytest.raises(PersistenceError):
            manager.load(path)


class _MaliciousPickle:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return eval, (f"__import__('pathlib').Path({str(self.marker)!r}).touch()",)


@pytest.mark.parametrize("protocol", [0, pickle.HIGHEST_PROTOCOL])
@pytest.mark.parametrize("compress", [False, True])
def test_pickle_payload_is_never_executed(tmp_path, protocol, compress):
    marker = tmp_path / "executed"
    payload = pickle.dumps(_MaliciousPickle(marker), protocol=protocol)
    path = tmp_path / "misleading.json"
    path.write_bytes(gzip.compress(payload, mtime=0) if compress else payload)
    for format in (None, "json", "msgpack", "pickle"):
        with pytest.raises(PersistenceError):
            PersistenceManager().load(path, format=format)
        assert not marker.exists()


@pytest.mark.parametrize("format", ["pickle", "pkl", "yaml", "unknown", ""])
def test_unsupported_format_rejected_before_destination_access(tmp_path, envelope, format):
    manager = PersistenceManager()
    path = tmp_path / "missing" / "target"
    with pytest.raises(PersistenceError, match="Unsupported snapshot format"):
        manager.save(envelope, path, format=format)
    with pytest.raises(PersistenceError, match="Unsupported snapshot format"):
        manager.load(path, format=format)
    assert not path.parent.exists()


@pytest.mark.parametrize("format", ["json", "msgpack"])
@pytest.mark.parametrize("compress", [False, True])
def test_encoded_size_limit_and_exact_boundary(tmp_path, envelope, format, compress):
    path = PersistenceManager().save(
        envelope, tmp_path / f"bounded.{format}", format=format, compress=compress
    )
    encoded = path.read_bytes()
    decoded = gzip.decompress(encoded) if compress else encoded
    limit = max(len(encoded), len(decoded))
    assert PersistenceManager().load(path, max_bytes=limit) == envelope
    with pytest.raises(PersistenceError, match="exceeds max_bytes"):
        PersistenceManager().load(path, max_bytes=len(encoded) - 1)


@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_gzip_decoded_size_limit_independent_of_suffix(tmp_path, envelope, format):
    envelope["metadata"]["large"] = "x" * 50_000
    path = PersistenceManager().save(
        envelope, tmp_path / "compressed.data", format=format, compress=True
    )
    encoded = path.read_bytes()
    decoded = gzip.decompress(encoded)
    assert len(encoded) < 1000 < len(decoded)
    with pytest.raises(PersistenceError, match="decoded size"):
        PersistenceManager().load(path, max_bytes=1000)
    assert PersistenceManager().load(path, max_bytes=len(decoded)) == envelope


def test_concatenated_gzip_members_share_decoded_limit(tmp_path):
    path = tmp_path / "members.json"
    path.write_bytes(gzip.compress(b" " * 1000) + gzip.compress(b" " * 1000))
    with pytest.raises(PersistenceError, match="decoded size"):
        PersistenceManager().load(path, max_bytes=1500)


def test_bounded_reader_never_issues_an_unbounded_read():
    class LimitedReader(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 64 * 1024
            return super().read(size)

    assert (
        persistence._read_bounded(LimitedReader(b"x" * 100_000), 100_000, "input") == b"x" * 100_000
    )
    with pytest.raises(ValueError, match="exceeds max_bytes"):
        persistence._read_bounded(LimitedReader(b"x" * 100_001), 100_000, "input")


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.5, None])
def test_invalid_size_limit_rejected(tmp_path, max_bytes):
    with pytest.raises(PersistenceError, match="positive integer"):
        PersistenceManager().load(tmp_path / "missing.msgpack", max_bytes=max_bytes)


def test_explicit_missing_parent_is_created_without_redirection(tmp_path, envelope):
    fallback = tmp_path / "fallback"
    manager = PersistenceManager(config={"storage": {"data_dir": str(fallback)}})
    path = tmp_path / "requested" / "deep" / "graph.json"
    assert manager.save(envelope, path, format="json") == path
    assert path.parent.is_dir() and path.is_file()
    assert not fallback.exists()
    assert manager.load(path) == envelope
    assert list(path.parent.iterdir()) == [path]


def test_existing_directory_is_not_relocated_or_replaced(tmp_path, envelope):
    path = tmp_path / "graph.msgpack"
    path.mkdir()
    with pytest.raises(PersistenceError):
        PersistenceManager().save(envelope, path)
    assert path.is_dir()
    assert list(tmp_path.iterdir()) == [path]


def test_missing_path_does_not_discover_another_snapshot(tmp_path, envelope):
    manager = PersistenceManager(config={"storage": {"data_dir": str(tmp_path)}})
    manager.save(envelope, tmp_path / "same-name.msgpack")
    with pytest.raises(PersistenceError):
        manager.load(tmp_path / "missing" / "same-name.msgpack")


@pytest.mark.parametrize(
    "suffix, expected",
    [
        ("json", "json"),
        ("JSON.gz", "json"),
        ("msgpack", "msgpack"),
        ("msgpack.gz", "msgpack"),
        ("mpk", "msgpack"),
    ],
)
def test_format_detection_supported_missing_suffix(tmp_path, suffix, expected):
    assert detect_format(tmp_path / f"missing.{suffix}") == expected
    assert PersistenceManager().detect_format(tmp_path / f"missing.{suffix}") == expected


@pytest.mark.parametrize("format", ["json", "msgpack"])
@pytest.mark.parametrize("compress", [False, True])
def test_sniff_unknown_suffix_and_suffixless_payload(tmp_path, envelope, format, compress):
    path = tmp_path / "snapshot.data"
    PersistenceManager().save(envelope, path, format=format, compress=compress)
    assert detect_format(path) == format
    assert PersistenceManager().load(path) == envelope
    assert detect_format(tmp_path / "missing") is None
    opposite = tmp_path / ("misleading.msgpack" if format == "json" else "misleading.json")
    opposite.write_bytes(path.read_bytes())
    assert PersistenceManager().load(opposite) == envelope
    with pytest.raises(PersistenceError):
        PersistenceManager().load(opposite, format="msgpack" if format == "json" else "json")


@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_bare_and_pickle_bytes_are_not_format_fallbacks(tmp_path, format):
    path = tmp_path / "unknown.data"
    path.write_bytes(b"unknown")
    with pytest.raises(PersistenceError):
        detect_format(path)
    path.write_bytes(
        pickle.dumps({"format": "fastgraph", "version": 3, "metadata": {}, "store": {}})
    )
    with pytest.raises(PersistenceError):
        PersistenceManager().load(path, format=format)


@pytest.mark.parametrize("source_format,target_format", [("json", "msgpack"), ("msgpack", "json")])
@pytest.mark.parametrize("compress", [False, True])
def test_translation_preserves_deep_envelope(
    tmp_path, nested_graph, source_format, target_format, compress
):
    manager = PersistenceManager()
    expected = nested_graph.snapshot()
    source = manager.save(
        expected, tmp_path / f"source.{source_format}", format=source_format, compress=True
    )
    target = tmp_path / "new" / f"translated.{target_format}"
    assert manager.translate(source, target, compress=compress) == target
    assert manager.load(target) == expected
    assert manager.load(source) == expected
    loaded = FastGraph.from_file(target)
    try:
        assert loaded.snapshot() == expected
    finally:
        loaded.close()


@pytest.mark.parametrize("version", [4, 0, "3", "3.0.0", True, 3.0, None])
@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_unknown_or_mistyped_envelope_version_rejected(tmp_path, envelope, version, format):
    envelope["version"] = version
    path = tmp_path / f"version.{format}"
    _write_encoded(path, envelope, format)
    with pytest.raises(PersistenceError, match="version"):
        PersistenceManager().load(path)
    original = path.read_bytes()
    with pytest.raises(PersistenceError, match="version"):
        PersistenceManager().save(envelope, path, format=format)
    assert path.read_bytes() == original


@pytest.mark.parametrize("mutation", ["format", "missing", "metadata", "store", "extra"])
@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_invalid_envelope_schema_rejected(tmp_path, envelope, mutation, format):
    if mutation == "format":
        envelope["format"] = "other"
    elif mutation == "missing":
        del envelope["store"]
    elif mutation == "extra":
        envelope["nodes"] = {}
    else:
        envelope[mutation] = []
    path = tmp_path / f"schema.{format}"
    _write_encoded(path, envelope, format)
    with pytest.raises(PersistenceError):
        PersistenceManager().load(path)
    with pytest.raises(PersistenceError):
        PersistenceManager().save(envelope, tmp_path / "not-created", format=format)
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    "value", [b"binary", (1, 2), {1, 2}, {1: "nonstring"}, float("nan"), float("inf")]
)
@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_non_json_save_values_rejected_without_coercion(tmp_path, envelope, value, format):
    envelope["metadata"]["unsupported"] = value
    with pytest.raises(PersistenceError):
        PersistenceManager().save(envelope, tmp_path / "snapshot", format=format)
    assert list(tmp_path.iterdir()) == []


def test_cycles_rejected_without_touching_target(tmp_path, envelope):
    envelope["metadata"]["cycle"] = envelope
    with pytest.raises(PersistenceError, match="Circular"):
        PersistenceManager().save(envelope, tmp_path / "cycle.json", format="json")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_duplicate_object_keys_are_rejected(tmp_path, format):
    path = tmp_path / f"duplicate.{format}"
    if format == "json":
        payload = b'{"format":"fastgraph","version":4,"version":3,"metadata":{},"store":{}}'
    else:
        packer = msgpack.Packer(use_bin_type=True)
        payload = packer.pack_map_header(5) + b"".join(
            packer.pack(key) + packer.pack(value)
            for key, value in [
                ("format", "fastgraph"),
                ("version", 4),
                ("version", 3),
                ("metadata", {}),
                ("store", {}),
            ]
        )
    path.write_bytes(payload)
    with pytest.raises(PersistenceError, match="Duplicate"):
        PersistenceManager().load(path)


@pytest.mark.parametrize(
    "value",
    [
        b"binary",
        msgpack.ExtType(7, b"extension"),
        float("nan"),
        {1: "key"},
    ],
)
def test_non_json_msgpack_values_rejected(tmp_path, envelope, value):
    envelope["metadata"]["unsupported"] = value
    path = tmp_path / "invalid.msgpack"
    path.write_bytes(msgpack.packb(envelope, use_bin_type=True))
    with pytest.raises(PersistenceError):
        PersistenceManager().load(path)


def test_non_json_msgpack_timestamp_rejected(tmp_path, envelope):
    packer = msgpack.Packer(use_bin_type=True)
    payload = packer.pack_map_header(len(envelope))
    for key, value in envelope.items():
        payload += packer.pack(key)
        if key != "metadata":
            payload += packer.pack(value)
            continue
        payload += packer.pack_map_header(len(value) + 1)
        for field, item in value.items():
            payload += packer.pack(field) + packer.pack(item)
        # Timestamp32 wire encoding avoids C-extension class checks under coverage.
        payload += packer.pack("unsupported") + b"\xd6\xff\x00\x00\x00\x01"
    path = tmp_path / "timestamp.msgpack"
    path.write_bytes(payload)
    with pytest.raises(PersistenceError):
        PersistenceManager().load(path)


@pytest.mark.parametrize("header", [b"\xdf", b"\xdd", b"\xdb", b"\xc6"])
def test_forged_msgpack_container_lengths_are_bounded(tmp_path, header):
    path = tmp_path / "forged.msgpack"
    path.write_bytes(header + b"\xff\xff\xff\xff")
    with pytest.raises(PersistenceError):
        PersistenceManager().load(path, max_bytes=64)


def test_nonfinite_json_value_rejected(tmp_path, envelope):
    envelope["metadata"]["invalid"] = float("nan")
    path = tmp_path / "invalid.json"
    _write_encoded(path, envelope, "json")
    with pytest.raises(PersistenceError, match="Non-finite"):
        PersistenceManager().load(path)


@pytest.mark.parametrize("version", [2, "2.0.0"])
@pytest.mark.parametrize("format", ["json", "msgpack"])
@pytest.mark.parametrize("compress", [False, True])
def test_v2_migration_rebuilds_native_indexes(tmp_path, version, format, compress):
    legacy = {
        "version": version,
        "created_at": 1200.5,
        "metadata": {"name": "legacy", "created_at": 1100.5},
        "nodes": {
            "a": {"type": "Person", "code": "1"},
            "b": {"type": "Company", "code": 1},
        },
        "edges": [
            {"src": "a", "dst": "b", "rel": "WORKS_AT", "weight": 3, "attrs": {"nested": [1, True]}}
        ],
        "indexes": {"type": {"stale": ["nonexistent"]}, "code": {"1": ["b"]}},
    }
    original = deepcopy(legacy)
    path = tmp_path / f"legacy.{format}"
    _write_encoded(path, legacy, format, compress=compress)
    manager = PersistenceManager()
    migrated = manager.load(path)
    assert migrated["format"] == "fastgraph" and migrated["version"] == 3
    assert migrated["metadata"] == legacy["metadata"]
    assert migrated["store"]["scopes"][0]["indexes"] == ["code", "type"]
    assert legacy == original
    loaded = FastGraph.from_file(path)
    try:
        assert dict(loaded.find_nodes(code="1")) == {"a": {"type": "Person", "code": "1"}}
        assert dict(loaded.find_nodes(code=1)) == {"b": {"type": "Company", "code": 1}}
        assert dict(loaded.find_nodes(type="Person")) == {"a": {"type": "Person", "code": "1"}}
        assert loaded.get_edge(loaded["a"], loaded["b"], "WORKS_AT").attrs == {
            "weight": 3,
            "attrs": {"nested": [1, True]},
        }
        loaded.update_node("a", type="Robot")
        loaded.add_node("c", type="Person")
        assert dict(loaded.find_nodes(type="Person")) == {"c": {"type": "Person"}}
        rewritten = manager.translate(path, tmp_path / "v3.msgpack")
        assert manager.load(rewritten) == migrated
    finally:
        loaded.close()


def test_v2_top_level_created_at_migrates(tmp_path):
    legacy = {
        "version": "2.0.0",
        "created_at": 1234.5,
        "metadata": {"name": "legacy"},
        "nodes": {},
        "edges": [],
        "indexes": {},
    }
    path = tmp_path / "legacy.json"
    _write_encoded(path, legacy, "json")
    assert PersistenceManager().load(path)["metadata"] == {"name": "legacy", "created_at": 1234.5}


@pytest.mark.parametrize("version", [4, "4.0.0", None, True])
def test_unknown_legacy_version_rejected(tmp_path, version):
    path = tmp_path / "legacy.json"
    _write_encoded(path, {"version": version, "nodes": {}, "edges": []}, "json")
    with pytest.raises(PersistenceError, match="version"):
        PersistenceManager().load(path)


def test_invalid_v2_edge_rejected_without_changing_graph(tmp_path, nested_graph):
    path = tmp_path / "legacy.json"
    _write_encoded(
        path,
        {
            "version": "2.0.0",
            "nodes": {"a": {}},
            "edges": [{"src": "a", "dst": "missing", "rel": "R"}],
        },
        "json",
    )
    before = nested_graph.snapshot()
    with pytest.raises(PersistenceError, match="missing node"):
        nested_graph.load(path)
    assert nested_graph.snapshot() == before


@pytest.mark.parametrize(
    "mutation", ["version", "missing_scope", "edge_endpoint", "duplicate_node", "cycle", "metadata"]
)
def test_invalid_graph_state_leaves_original_intact(tmp_path, nested_graph, mutation):
    before = nested_graph.snapshot()
    invalid = deepcopy(before)
    store = invalid["store"]
    if mutation == "version":
        store["version"] = 999
    elif mutation == "missing_scope":
        store["nodes"][0]["scope"] = 999999
    elif mutation == "edge_endpoint":
        store["edges"][0]["dst"] = 999999
    elif mutation == "duplicate_node":
        store["nodes"].append(deepcopy(store["nodes"][0]))
    elif mutation == "cycle":
        owner = next(node for node in store["nodes"] if node["child_scope"] is not None)
        owner["scope"] = owner["child_scope"]
    else:
        invalid["metadata"]["name"] = 7
    path = PersistenceManager().save(invalid, tmp_path / "invalid.msgpack")
    old_ref = nested_graph.resolve(("company", "alice"))
    with pytest.raises(PersistenceError):
        nested_graph.load(path)
    assert nested_graph.snapshot() == before
    assert old_ref.path == ("company", "alice")


def test_native_snapshot_is_versioned_and_validated(nested_graph):
    with nested_graph._state.lock:
        payload = nested_graph._state.store.snapshot()
    assert type(payload) is bytes
    assert json.loads(payload.decode("utf-8"))["version"] == 1
    replacement = NativeStore.from_snapshot(payload)
    assert json.loads(replacement.snapshot()) == nested_graph.snapshot()["store"]
    with pytest.raises(ValueError):
        NativeStore.from_snapshot(b'{"version":999}')


def test_manager_optional_config_and_legacy_lock(tmp_path):
    lock = threading.RLock()
    assert PersistenceManager(lock).lock is lock
    assert (
        PersistenceManager(config={"storage": {"data_dir": str(tmp_path)}}, lock=lock).lock is lock
    )
    config = ConfigManager(config_dict={"storage": {"data_dir": str(tmp_path)}})
    assert PersistenceManager(config=config).config == config.get_config()
    assert PersistenceManager().get_supported_formats() == ["json", "msgpack"]
    with pytest.raises(TypeError):
        PersistenceManager(config=object())


@pytest.mark.skipif(os.name != "posix", reason="Directory fsync is a POSIX durability step")
def test_directory_fsync_unsupported_is_tolerated(tmp_path, monkeypatch):
    def unsupported(fd):
        raise OSError(errno.EINVAL, "directory fsync unsupported")

    monkeypatch.setattr(persistence.os, "fsync", unsupported)
    persistence._fsync_directory(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="Directory fsync is a POSIX durability step")
def test_directory_fsync_io_error_is_reported_after_complete_publish(
    tmp_path, envelope, monkeypatch
):
    real_fsync = os.fsync
    calls = 0

    def fsync(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EIO, "directory fsync failed")
        real_fsync(fd)

    monkeypatch.setattr(persistence.os, "fsync", fsync)
    path = tmp_path / "published.msgpack"
    with pytest.raises(PersistenceError, match="directory fsync failed"):
        PersistenceManager().save(envelope, path)
    assert PersistenceManager().load(path) == envelope
    assert list(tmp_path.iterdir()) == [path]

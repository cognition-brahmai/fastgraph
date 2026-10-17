"""Shared-scope isolation and safe snapshot observations."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from fastgraph import FastGraph, PersistenceError, ValidationError
from fastgraph._native import NativeStore


def test_parallel_upserts_keep_all_adjacency_representations_consistent():
    graph = FastGraph()
    graph.add_nodes_batch([(str(i), {}) for i in range(100)])

    def write(worker):
        for i in range(100):
            graph.add_edge(str(i), str((i + 1) % 100), "r", worker=worker)
            graph.update_node(str(i), last_worker=worker)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(4)))
    assert graph.edge_count == 100
    for i in range(100):
        assert graph.degree(str(i)) == (1, 1, 2)


def test_transaction_blocks_other_scope_observers_until_commit():
    graph = FastGraph()
    graph.add_node("owner")
    child = graph["owner"].graph
    observer_started = Event()
    observed = Event()

    def read():
        observer_started.set()
        result = child.node_ids()
        observed.set()
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph.transaction():
            child.add_node("a")
            future = pool.submit(read)
            assert observer_started.wait(5)
            assert not observed.is_set()
            child.add_node("b")
        assert future.result(timeout=5) == ("a", "b")


def test_snapshot_observations_validate_during_concurrent_churn():
    graph = FastGraph()
    graph.add_node("anchor")

    def mutate():
        for i in range(100):
            graph.add_node("temp", iteration=i)
            graph.add_edge("anchor", "temp", "r")
            graph.remove_node("temp")

    def observe():
        import json

        for _ in range(100):
            data = graph.snapshot()
            NativeStore.from_snapshot(json.dumps(data["store"]).encode())

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda function: function(), [mutate, observe]))
    assert graph.node_ids() == ("anchor",)
    assert graph.edge_count == 0


def test_transaction_cannot_publish_uncommitted_snapshot_or_close(tmp_path):
    graph = FastGraph()
    with graph.transaction():
        graph.add_node("a")
        with pytest.raises(PersistenceError):
            graph.save(tmp_path / "uncommitted.json")
        with pytest.raises(ValidationError):
            graph.close()
    assert not (tmp_path / "uncommitted.json").exists()


def test_view_registry_reads_wait_until_transaction_commit():
    graph = FastGraph()
    graph.add_node("n")
    started = Event()
    observed = Event()

    def read():
        started.set()
        view = graph.get_subgraph_view("committed")
        observed.set()
        return view

    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph.transaction():
            graph.create_subgraph_view("committed")
            future = pool.submit(read)
            assert started.wait(5)
            assert not observed.is_set()
        assert future.result(timeout=5) is not None


def test_rollback_drops_uncommitted_view_registry_entries():
    graph = FastGraph()
    graph.add_node("n")
    with pytest.raises(RuntimeError):
        with graph.transaction():
            graph.create_subgraph_view("failed")
            raise RuntimeError("rollback")
    assert graph.get_subgraph_view("failed") is None

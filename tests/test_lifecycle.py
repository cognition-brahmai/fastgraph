"""Scope handles cannot mutate replacement stores after waiting for the lock."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from fastgraph import ClosedGraphError, FastGraph, StaleReferenceError


def test_waiting_index_creation_rechecks_scope_after_rollback():
    graph = FastGraph()
    child = graph.add_node("owner").graph
    started = Event()

    def create():
        started.set()
        child.build_node_index("property")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph._state.lock:
            future = pool.submit(create)
            assert started.wait(5)
            with pytest.raises(RuntimeError):
                with graph.transaction():
                    raise RuntimeError("rollback")
        with pytest.raises(StaleReferenceError):
            future.result(timeout=5)
    assert graph["owner"].graph.get_index_stats()["attributes"] == []


def test_waiting_index_creation_rechecks_after_close():
    graph = FastGraph()
    manager = graph.index_manager
    started = Event()

    def create():
        started.set()
        manager.create_node_index("property")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with graph._state.lock:
            future = pool.submit(create)
            assert started.wait(5)
            graph.close()
        with pytest.raises(ClosedGraphError):
            future.result(timeout=5)


def test_child_close_closes_handle_only_not_scope_or_root():
    graph = FastGraph()
    node = graph.add_node("owner")
    child = node.graph
    child.add_node("inside")
    child.close()
    with pytest.raises(ClosedGraphError):
        child.add_node("bad")
    assert node.graph.node_ids() == ("inside",)
    assert graph.node_ids() == ("owner",)

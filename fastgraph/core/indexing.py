"""Scope-local index administration over the native store."""

from __future__ import annotations

import weakref
from typing import Any

from ..exceptions import IndexingError, StaleReferenceError


class IndexManager:
    """Indexes are explicit native equality indexes, not duplicate Python postings."""

    def __init__(self, graph):
        self._graph = weakref.ref(graph)

    def _get_graph(self):
        graph = self._graph()
        if graph is None:
            raise StaleReferenceError("The graph owning this index manager no longer exists")
        return graph

    @property
    def indexed_attributes(self) -> frozenset[str]:
        graph = self._get_graph()
        with graph._state.lock:
            graph._guard()
            return frozenset(graph._state.store.index_names(graph._scope))

    def has_index(self, attr_name: str) -> bool:
        return attr_name in self.indexed_attributes

    def create_node_index(self, attr_name: str) -> None:
        graph = self._get_graph()
        with graph._state.lock:
            graph._guard()
            graph._native_call(graph._state.store.create_index, graph._scope, attr_name)

    def drop_node_index(self, attr_name: str) -> None:
        graph = self._get_graph()
        with graph._state.lock:
            graph._guard()
            if not self.has_index(attr_name):
                raise IndexingError(f"No index on '{attr_name}'", index_name=attr_name)
            graph._state.store.drop_index(graph._scope, attr_name)

    def query_by_index(self, attr_name: str, value: Any) -> set:
        graph = self._get_graph()
        with graph._state.lock:
            graph._guard()
            if not self.has_index(attr_name):
                raise IndexingError(f"No index on '{attr_name}'", index_name=attr_name)
            ids = graph._native_call(
                graph._state.store.find_nodes, graph._scope, [(attr_name, "eq", value)]
            )
            return {graph._display_id(nid) for nid in ids}

    def query_by_index_range(self, attr_name: str, min_val: Any, max_val: Any) -> set:
        graph = self._get_graph()
        if not self.has_index(attr_name):
            raise IndexingError(f"No index on '{attr_name}'", index_name=attr_name)
        return {
            nid
            for nid, _ in graph.find_nodes(
                **{f"{attr_name}__gte": min_val, f"{attr_name}__lte": max_val}
            )
        }

    def rebuild_all_indexes(self) -> None:
        for name in self.indexed_attributes:
            self.create_node_index(name)

    def get_index_statistics(self) -> dict[str, Any]:
        names = sorted(self.indexed_attributes)
        return {
            "attributes": names,
            "global": {"total_indexes": len(names)},
            "kind": "native equality",
            "range_strategy": "filtered scan",
        }

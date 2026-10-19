"""Fixed-membership selection handles into a live native graph store."""

from __future__ import annotations

import weakref
from collections.abc import Mapping
from contextlib import contextmanager

from ..exceptions import NodeNotFoundError, TraversalError
from .traversal import TraversalOperations


class _NodeMapping(Mapping):
    __slots__ = ("_view",)

    def __init__(self, view):
        self._view = view

    def __len__(self):
        return self._view.node_count

    def __iter__(self):
        return iter(self._view._keys())

    def __getitem__(self, key):
        try:
            return self._view.get_node(key)
        except NodeNotFoundError as exc:
            raise KeyError(key) from exc


class SubgraphView:
    """A fixed ID selection, not a graph clone or a repeatedly evaluated filter.

    Membership excludes removed IDs. Attributes and edges are copied native
    snapshots when requested; the selection itself owns no graph payloads.
    """

    def __init__(self, parent, node_ids):
        with parent._state.lock:
            parent._guard()
            selected = set()
            for value in node_ids:
                if isinstance(value, int) and not isinstance(value, bool):
                    if not parent._state.store.has_node(value):
                        raise NodeNotFoundError(value)
                    selected.add(value)
                else:
                    selected.add(parent._resolve_id(value))
            self._node_ids = frozenset(selected)
            self._parent_ref = weakref.ref(parent)
            self._epoch = parent._state.epoch

    @contextmanager
    def _locked_parent(self):
        parent = self._parent_ref()
        if parent is None:
            raise TraversalError("Parent graph was garbage collected")
        with parent._state.lock:
            parent._guard()
            if parent._state.epoch != self._epoch:
                raise TraversalError("Subgraph view belongs to an invalidated graph")
            yield parent

    @property
    def parent(self):
        with self._locked_parent() as parent:
            return parent

    def _live_ids(self, parent):
        return [nid for nid in sorted(self._node_ids) if parent._state.store.has_node(nid)]

    def _resolve(self, parent, value):
        nid = parent._resolve_id(value)
        if nid not in self._node_ids:
            raise NodeNotFoundError(value)
        return nid

    def _keys(self):
        with self._locked_parent() as parent:
            return tuple(parent._display_id(nid) for nid in self._live_ids(parent))

    def _edge_ids(self, parent):
        return (
            edge_id
            for nid in self._live_ids(parent)
            for neighbor, edge_id in parent._state.store.neighbors(nid, direction="out")
            if neighbor in self._node_ids
        )

    @property
    def nodes(self) -> Mapping:
        with self._locked_parent():
            return _NodeMapping(self)

    @property
    def edges(self):
        with self._locked_parent() as parent:
            return [parent._edge_ref(eid) for eid in self._edge_ids(parent)]

    @property
    def node_count(self) -> int:
        with self._locked_parent() as parent:
            return sum(parent._state.store.has_node(nid) for nid in self._node_ids)

    @property
    def edge_count(self) -> int:
        with self._locked_parent() as parent:
            return sum(1 for _ in self._edge_ids(parent))

    def contains_node(self, node) -> bool:
        with self._locked_parent() as parent:
            try:
                nid = parent._resolve_id(node)
            except NodeNotFoundError:
                return False
            return nid in self._node_ids

    def get_node(self, node):
        with self._locked_parent() as parent:
            return parent._node_ref(self._resolve(parent, node)).attrs

    def neighbors_out(self, node, rel=None, edge_filter=None):
        with self._locked_parent() as parent:
            return TraversalOperations(parent, allowed=self._node_ids).neighbors_out(
                node, rel, edge_filter
            )

    def neighbors_in(self, node, rel=None, edge_filter=None):
        with self._locked_parent() as parent:
            return TraversalOperations(parent, allowed=self._node_ids).neighbors_in(
                node, rel, edge_filter
            )

    def neighbors(self, node, rel=None, edge_filter=None):
        with self._locked_parent() as parent:
            return TraversalOperations(parent, allowed=self._node_ids).neighbors(
                node, rel, edge_filter
            )

    def degree(self, node, rel=None):
        with self._locked_parent() as parent:
            return TraversalOperations(parent, allowed=self._node_ids).degree(node, rel)

    def get_edges_between(self, src, dst, rel=None):
        with self._locked_parent() as parent:
            try:
                src_id, dst_id = self._resolve(parent, src), self._resolve(parent, dst)
            except NodeNotFoundError:
                return []
            return [
                parent._edge_ref(eid)
                for neighbor, eid in parent._state.store.neighbors(src_id, direction="out", rel=rel)
                if neighbor == dst_id
            ]

    def get_node_edges(self, node):
        with self._locked_parent() as parent:
            try:
                nid = self._resolve(parent, node)
            except NodeNotFoundError:
                return []
            edge_ids = dict.fromkeys(
                eid
                for neighbor, eid in parent._state.store.neighbors(nid, direction="both")
                if neighbor in self._node_ids
            )
            return [parent._edge_ref(eid) for eid in edge_ids]

    def get_neighbors(self, node):
        with self._locked_parent() as parent:
            try:
                nid = self._resolve(parent, node)
            except NodeNotFoundError:
                return []
            ids = dict.fromkeys(
                neighbor
                for neighbor, _ in parent._state.store.neighbors(nid, direction="both")
                if neighbor in self._node_ids
            )
            return [parent._display_id(nid) for nid in ids]

    def stats(self):
        with self._locked_parent() as parent:
            nodes = sum(parent._state.store.has_node(nid) for nid in self._node_ids)
            edges = sum(1 for _ in self._edge_ids(parent))
            return {
                "nodes": nodes,
                "edges": edges,
                "avg_degree": 2 * edges / nodes if nodes else 0.0,
                "density": edges / (nodes * (nodes - 1)) if nodes > 1 else 0.0,
            }

    def _calculate_density(self):
        return self.stats()["density"]

    def bfs(
        self,
        start,
        max_depth=None,
        rel=None,
        node_filter=None,
        edge_filter=None,
        *,
        direction="out",
        nested=False,
        max_nodes=None,
        filters=None,
    ):
        with self._locked_parent() as parent:
            return TraversalOperations(parent, allowed=self._node_ids).bfs(
                start,
                max_depth,
                rel,
                node_filter,
                edge_filter,
                direction=direction,
                nested=nested,
                max_nodes=max_nodes,
                filters=filters,
            )

    def shortest_path(
        self,
        start,
        end,
        rel=None,
        edge_filter=None,
        *,
        direction="out",
        nested=False,
        max_depth=None,
        node_filter=None,
        filters=None,
    ):
        with self._locked_parent() as parent:
            return TraversalOperations(parent, allowed=self._node_ids).shortest_path(
                start,
                end,
                rel,
                edge_filter,
                direction=direction,
                nested=nested,
                max_depth=max_depth,
                node_filter=node_filter,
                filters=filters,
            )

    def is_connected(self) -> bool:
        with self._locked_parent() as parent:
            ids = self._live_ids(parent)
            if len(ids) <= 1:
                return True
            visited, _, _, _ = parent._state.store.bfs(ids[0], direction="both", allowed=ids)
            return len(visited) == len(ids)

    def find_components(self):
        with self._locked_parent() as parent:
            components = TraversalOperations(parent, allowed=self._node_ids).connected_components()
            return [
                {parent._display_id(node._id) for node in component} for component in components
            ]

    def __contains__(self, node):
        return self.contains_node(node)

    def __len__(self):
        return self.node_count

    def __iter__(self):
        return iter(self._keys())

    def __repr__(self):
        stats = self.stats()
        return f"SubgraphView(nodes={stats['nodes']}, edges={stats['edges']})"

    def __str__(self):
        stats = self.stats()
        return f"Subgraph with {stats['nodes']} nodes and {stats['edges']} edges"

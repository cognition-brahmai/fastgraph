"""Python handles over a shared native graph store."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

try:
    from .._native import NativeStore
except ImportError as exc:
    raise ImportError(
        "FastGraph requires its native extension. Install with `pip install .` or build "
        "a development installation with `maturin develop --release`."
    ) from exc

from ..config.manager import ConfigManager
from ..exceptions import (
    ClosedGraphError,
    EdgeNotFoundError,
    NodeNotFoundError,
    PersistenceError,
    StaleReferenceError,
    ValidationError,
)
from .edge import Edge
from .indexing import IndexManager
from .node import NodeRef
from .persistence import PersistenceManager
from .subgraph import SubgraphView
from .traversal import TraversalOperations


class _GraphState:
    """Shared ownership and one serializable observation boundary for all scopes."""

    __slots__ = (
        "store",
        "lock",
        "epoch",
        "closed",
        "config",
        "metadata",
        "transaction_depth",
        "identity",
    )

    def __init__(self, name: str, config: ConfigManager):
        self.store = NativeStore()
        self.lock = threading.RLock()
        self.epoch = 0
        self.closed = False
        self.config = config
        self.metadata = {"name": name, "created_at": time.time(), "version": "3.0.0"}
        self.transaction_depth = 0
        self.identity = object()


class FastGraph:
    """A graph scope in a native store, with explicit nested forward traversal.

    A string selects a local node. A tuple is an absolute path from the root.
    Child graphs share storage, locking, persistence and qualified node identities.
    Relationships are directed and unique by (source, destination, type); repeated
    insertion replaces properties. Node insertion also replaces properties; use
    update_node for a merge. Returned property dictionaries are detached copies.
    """

    def __init__(self, name: str = "fastgraph", config=None, **overrides: Any):
        if isinstance(config, ConfigManager):
            cfg = config
        elif isinstance(config, Mapping):
            cfg = ConfigManager(config_dict=dict(config))
        elif isinstance(config, (str, Path)):
            cfg = ConfigManager(config_file=config)
        elif config is None:
            cfg = ConfigManager()
        else:
            raise ValidationError("Config must be a mapping, path, or ConfigManager")
        for key, value in overrides.items():
            cfg.set("enhanced_api.enabled" if key == "enhanced_api" else key, value)
        if name is None:
            name = cfg.get("engine.name", "fastgraph")
        self._validate_local_id(name, "name")
        self._state = _GraphState(name, cfg)
        self._scope = 0
        self._epoch = 0
        self._closed = False
        self._subgraph_views: dict[str, SubgraphView] = {}
        self._setup_managers()

    @classmethod
    def _view(cls, state: _GraphState, scope: int) -> FastGraph:
        instance = cls.__new__(cls)
        instance._state = state
        instance._scope = scope
        instance._epoch = state.epoch
        instance._closed = False
        instance._subgraph_views = {}
        instance._setup_managers()
        return instance

    def _setup_managers(self) -> None:
        self.index_manager = IndexManager(self)
        self.traversal_ops = TraversalOperations(self)
        self.persistence_manager = PersistenceManager(config=self._state.config)

    def _guard(self) -> None:
        if self._closed or self._state.closed:
            raise ClosedGraphError("The graph is closed")
        if self._scope != 0:
            if self._epoch != self._state.epoch:
                raise StaleReferenceError("Graph scope predates a load or transaction rollback")
            if not self._state.store.scope_exists(self._scope):
                raise StaleReferenceError("The node owning this graph scope was removed")

    @staticmethod
    def _validate_local_id(value: Any, field: str = "node_id") -> None:
        if not isinstance(value, str) or not value:
            raise ValidationError("Identifiers must be nonempty strings", field=field, value=value)

    @staticmethod
    def _native_call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValidationError(str(exc)) from exc

    @staticmethod
    def _parse_filters(filters: Mapping[str, Any]) -> list[tuple[str, str, Any]]:
        operators = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists", "startswith"}
        parsed = []
        for expression, value in filters.items():
            if not isinstance(expression, str) or not expression:
                raise ValidationError("Property filters require nonempty string keys")
            if "__" in expression:
                key, operator = expression.rsplit("__", 1)
                if operator not in operators or not key:
                    raise ValidationError(f"Unknown filter operator in '{expression}'")
            else:
                key, operator = expression, "eq"
            if operator == "exists" and not isinstance(value, bool):
                raise ValidationError("The exists operator expects a boolean")
            if operator == "in" and not isinstance(value, (list, tuple)):
                raise ValidationError("The in operator expects a list")
            if operator == "in" and isinstance(value, tuple):
                value = list(value)
            parsed.append((key, operator, value))
        return parsed

    def _resolve_id(self, value) -> int:
        self._guard()
        if isinstance(value, NodeRef):
            if value._state is not self._state:
                raise ValidationError("A node from another store cannot be used as an endpoint")
            value._guard()
            return value._id
        if isinstance(value, str):
            self._validate_local_id(value)
            node_id = self._state.store.node_id(self._scope, value)
            if node_id is None:
                raise NodeNotFoundError(value)
            return node_id
        if isinstance(value, tuple) and value:
            scope = 0
            for position, local_id in enumerate(value):
                self._validate_local_id(local_id)
                node_id = self._state.store.node_id(scope, local_id)
                if node_id is None:
                    raise NodeNotFoundError(repr(value[: position + 1]))
                if position < len(value) - 1:
                    scope = self._state.store.node_info(node_id)[2]
                    if scope is None:
                        raise NodeNotFoundError(repr(value[: position + 2]))
            return node_id
        raise ValidationError("Use a local string ID, absolute path tuple, or NodeRef")

    def _node_ref(self, node_id: int) -> NodeRef:
        return NodeRef(self._state, node_id)

    def _display_id(self, node_id: int):
        scope, local_id, _ = self._state.store.node_info(node_id)
        return local_id if scope == self._scope else self._node_ref(node_id).path

    def _edge_ref(self, edge_id: int) -> Edge:
        src, dst, rel, attrs = self._state.store.get_edge(edge_id)
        return Edge._from_native(
            self._display_id(src),
            self._display_id(dst),
            rel,
            attrs,
            edge_id,
            (self._state.identity, self._state.epoch, edge_id),
        )

    @property
    def config(self) -> ConfigManager:
        return self._state.config

    @property
    def name(self) -> str:
        with self._state.lock:
            self._guard()
            owner = self._state.store.scope_owner(self._scope)
            return self._state.metadata["name"] if owner is None else self._node_ref(owner).local_id

    @property
    def path(self) -> tuple[str, ...]:
        with self._state.lock:
            self._guard()
            owner = self._state.store.scope_owner(self._scope)
            return () if owner is None else self._node_ref(owner).path

    @property
    def parent(self) -> FastGraph | None:
        with self._state.lock:
            self._guard()
            owner = self._state.store.scope_owner(self._scope)
            if owner is None:
                return None
            return self._view(self._state, self._state.store.node_info(owner)[0])

    @property
    def owner(self) -> NodeRef | None:
        with self._state.lock:
            self._guard()
            owner = self._state.store.scope_owner(self._scope)
            return None if owner is None else self._node_ref(owner)

    @property
    def revision(self) -> int:
        with self._state.lock:
            self._guard()
            return self._state.store.revision

    @property
    def node_count(self) -> int:
        return self.stats()["nodes"]

    @property
    def edge_count(self) -> int:
        return self.stats()["edges"]

    @property
    def graph(self) -> dict[str, Any]:
        """A detached inspection snapshot, not a mutable storage escape hatch."""
        with self._state.lock:
            self._guard()
            return {"nodes": dict(self.find_nodes()), "metadata": deepcopy(self._state.metadata)}

    def resolve(self, value) -> NodeRef:
        with self._state.lock:
            return self._node_ref(self._resolve_id(value))

    def enter(self, node, *, create: bool = True) -> FastGraph | None:
        return self.resolve(node).enter(create=create)

    def add_node(self, node_id: str, **attrs: Any) -> NodeRef:
        return self.add_nodes_batch([(node_id, attrs)])[0]

    def add_nodes_batch(self, nodes) -> list[NodeRef]:
        prepared = []
        for node_id, attrs in nodes:
            self._validate_local_id(node_id)
            if not isinstance(attrs, Mapping):
                raise ValidationError("Node properties must be a mapping")
            prepared.append((node_id, dict(attrs)))
        with self._state.lock:
            self._guard()
            ids = self._native_call(self._state.store.add_nodes, self._scope, prepared)
            return [self._node_ref(node_id) for node_id in ids]

    def update_node(self, node, **attrs: Any) -> NodeRef:
        with self._state.lock:
            node_id = self._resolve_id(node)
            scope, local_id, _ = self._state.store.node_info(node_id)
            properties = self._state.store.get_node(node_id)
            properties.update(attrs)
            self._native_call(self._state.store.add_nodes, scope, [(local_id, properties)])
            return self._node_ref(node_id)

    def get_node(self, node) -> dict[str, Any] | None:
        with self._state.lock:
            try:
                node_id = self._resolve_id(node)
                return self._state.store.get_node(node_id)
            except NodeNotFoundError:
                return None

    def remove_node(self, node) -> bool:
        with self._state.lock:
            try:
                node_id = self._resolve_id(node)
            except NodeNotFoundError:
                return False
            return self._state.store.remove_node(node_id)

    def add_edge(self, src, dst, rel: str, **attrs: Any) -> Edge:
        with self._state.lock:
            ids = self.add_edges_batch([(src, dst, rel, attrs)])
            return self._edge_ref(ids[0])

    def add_edges_batch(self, edges) -> list[int]:
        """Insert atomically and return compact relationship IDs, not hydrated payloads."""
        with self._state.lock:
            self._guard()
            prepared = []
            local = True
            for edge in edges:
                if len(edge) not in (3, 4):
                    raise ValidationError("Edges require (source, destination, type[, properties])")
                src, dst, rel = edge[:3]
                self._validate_local_id(rel, "rel")
                attrs = edge[3] if len(edge) == 4 else {}
                if attrs is None:
                    attrs = {}
                if not isinstance(attrs, Mapping):
                    raise ValidationError("Relationship properties must be a mapping")
                local = local and isinstance(src, str) and isinstance(dst, str)
                prepared.append((src, dst, rel, dict(attrs)))
            if local:
                try:
                    return self._native_call(
                        self._state.store.add_edges_local, self._scope, prepared
                    )
                except KeyError as exc:
                    raise NodeNotFoundError(str(exc.args[0])) from exc
            resolved = [
                (self._resolve_id(src), self._resolve_id(dst), rel, attrs)
                for src, dst, rel, attrs in prepared
            ]
            ids = self._native_call(self._state.store.add_edges, resolved)
            return ids

    def get_edge(self, src, dst, rel: str) -> Edge | None:
        with self._state.lock:
            self._guard()
            if isinstance(src, str) and isinstance(dst, str):
                result = self._state.store.edge_local(self._scope, src, dst, rel)
                if result is None:
                    return None
                edge_id, attrs = result
                return Edge._from_native(
                    src,
                    dst,
                    rel,
                    attrs,
                    edge_id,
                    (self._state.identity, self._state.epoch, edge_id),
                )
            try:
                src_id, dst_id = self._resolve_id(src), self._resolve_id(dst)
            except NodeNotFoundError:
                return None
            edge_id = self._state.store.edge_id(src_id, dst_id, rel)
            return None if edge_id is None else self._edge_ref(edge_id)

    def has_edge(self, src, dst, rel: str) -> bool:
        """Check a relationship without materializing its properties."""
        with self._state.lock:
            self._guard()
            if isinstance(src, str) and isinstance(dst, str):
                return self._state.store.has_edge_local(self._scope, src, dst, rel)
            try:
                src_id, dst_id = self._resolve_id(src), self._resolve_id(dst)
            except NodeNotFoundError:
                return False
            return self._state.store.edge_id(src_id, dst_id, rel) is not None

    def neighbor_nodes(
        self, node, *, direction: str = "out", rel: str | None = None
    ) -> tuple[NodeRef, ...]:
        """Select adjacent nodes without hydrating relationship properties."""
        with self._state.lock:
            node_id = self._resolve_id(node)
            neighbors = self._native_call(
                self._state.store.neighbors, node_id, direction=direction, rel=rel
            )
            return tuple(self._node_ref(nid) for nid, _ in neighbors)

    def update_edge(self, src, dst, rel: str, **attrs: Any) -> Edge:
        with self._state.lock:
            edge = self.get_edge(src, dst, rel)
            if edge is None:
                raise EdgeNotFoundError(str(src), str(dst), rel)
            properties = dict(edge.attrs)
            properties.update(attrs)
            ids = self.add_edges_batch([(src, dst, rel, properties)])
            return self._edge_ref(ids[0])

    def find_nodes(
        self, *, recursive: bool = False, limit: int | None = None, **filters: Any
    ) -> list[tuple[Any, dict[str, Any]]]:
        with self._state.lock:
            self._guard()
            ids = self._native_call(
                self._state.store.find_nodes,
                self._scope,
                self._parse_filters(filters),
                recursive=recursive,
                limit=limit,
            )
            return [
                (
                    self._node_ref(nid).path if recursive else self._display_id(nid),
                    self._state.store.get_node(nid),
                )
                for nid in ids
            ]

    def node_ids(self, *, recursive: bool = False) -> tuple:
        with self._state.lock:
            self._guard()
            return tuple(
                self._node_ref(nid).path if recursive else self._display_id(nid)
                for nid in self._state.store.node_ids(self._scope, recursive=recursive)
            )

    def nodes(self, *, recursive: bool = False, **filters: Any) -> tuple[NodeRef, ...]:
        with self._state.lock:
            self._guard()
            ids = self._native_call(
                self._state.store.find_nodes,
                self._scope,
                self._parse_filters(filters),
                recursive=recursive,
            )
            return tuple(self._node_ref(nid) for nid in ids)

    def find_edges(
        self, src=None, dst=None, rel: str | None = None, *, recursive: bool = False, **filters: Any
    ) -> list[Edge]:
        with self._state.lock:
            self._guard()
            src_id = None if src is None else self._resolve_id(src)
            dst_id = None if dst is None else self._resolve_id(dst)
            ids = self._native_call(
                self._state.store.edge_ids,
                self._scope,
                recursive=recursive,
                src=src_id,
                dst=dst_id,
                rel=rel,
                filters=self._parse_filters(filters),
            )
            return [self._edge_ref(edge_id) for edge_id in ids]

    def remove_edge(
        self, src=None, dst=None, rel: str | None = None, *, recursive: bool = False, **filters: Any
    ) -> int:
        with self._state.lock:
            try:
                edges = self.find_edges(src, dst, rel, recursive=recursive, **filters)
            except NodeNotFoundError:
                return 0
            return self._state.store.remove_edges([edge.id for edge in edges])

    def neighbors_out(self, node, rel: str | None = None):
        return self.traversal_ops.neighbors_out(node, rel)

    def neighbors_in(self, node, rel: str | None = None):
        return self.traversal_ops.neighbors_in(node, rel)

    def neighbors(self, node, rel: str | None = None):
        return self.traversal_ops.neighbors(node, rel)

    def degree(self, node) -> tuple[int, int, int]:
        return self.traversal_ops.degree(node)

    def bfs(self, start, **options):
        return self.traversal_ops.bfs(start, **options)

    def dfs(self, start, **options):
        return self.traversal_ops.dfs(start, **options)

    def shortest_path(self, start, end, **options):
        return self.traversal_ops.shortest_path(start, end, **options)

    def all_shortest_paths(self, start, end, **options):
        return self.traversal_ops.all_shortest_paths(start, end, **options)

    def find_paths(self, start, end, **options):
        return self.traversal_ops.find_paths(start, end, **options)

    def connected_components(self, *, recursive: bool = False):
        return self.traversal_ops.connected_components(recursive=recursive)

    def topological_sort(self, *, recursive: bool = False):
        return self.traversal_ops.topological_sort(recursive=recursive)

    def has_cycles(self, *, recursive: bool = False) -> bool:
        return self.traversal_ops.has_cycles(recursive=recursive)

    def build_node_index(self, attr_name: str) -> None:
        self.index_manager.create_node_index(attr_name)

    def drop_node_index(self, attr_name: str) -> None:
        self.index_manager.drop_node_index(attr_name)

    def get_index_stats(self) -> dict[str, Any]:
        return self.index_manager.get_index_statistics()

    def create_subgraph_view(self, name: str, node_filter=None, **filters: Any) -> SubgraphView:
        with self._state.lock:
            self._guard()
            ids = self._native_call(
                self._state.store.find_nodes, self._scope, self._parse_filters(filters)
            )
            if node_filter is not None:
                ids = [
                    nid
                    for nid in ids
                    if node_filter(self._display_id(nid), self._state.store.get_node(nid))
                ]
            view = SubgraphView(self, ids)
            self._subgraph_views[name] = view
            return view

    def get_subgraph_view(self, name: str) -> SubgraphView | None:
        with self._state.lock:
            self._guard()
            return self._subgraph_views.get(name)

    def stats(self, *, recursive: bool = False, detailed: bool = False) -> dict[str, Any]:
        with self._state.lock:
            self._guard()
            stats = self._state.store.stats(self._scope, recursive=recursive)
            stats.update(
                {
                    "name": self.name,
                    "backend": "rust",
                    "indexes": len(self._state.store.index_names(self._scope)),
                }
            )
            if detailed:
                stats["components"] = len(
                    self._state.store.connected_components(self._scope, recursive=recursive)
                )
                stats["memory"] = self.memory_usage_estimate()
            return stats

    def memory_usage_estimate(self) -> dict[str, Any]:
        with self._state.lock:
            self._guard()
            stats = self._state.store.memory_usage()
            stats["kind"] = "native capacity estimate; not process RSS"
            stats["scope"] = "whole shared store"
            return stats

    def clear(self) -> None:
        with self._state.lock:
            self._guard()
            self._state.store.clear_scope(self._scope)
            self._subgraph_views.clear()

    def clear_cache(self) -> None:
        """No query-result cache is retained; calls always observe current state."""
        self._guard()

    @contextmanager
    def transaction(self) -> Iterator[FastGraph]:
        """Serializable in-memory transaction with rollback; not a durable commit.

        A private native snapshot is copied once on entry. All scopes share the
        lock, so other Python graph handles cannot observe intermediate writes.
        Rollback invalidates node and child-graph handles acquired before it.
        """
        with self._state.lock:
            self._guard()
            if self._state.transaction_depth:
                raise ValidationError("Nested transactions are not supported")
            before = self._state.store.clone()
            metadata = deepcopy(self._state.metadata)
            views = dict(self._subgraph_views)
            self._state.transaction_depth = 1
            try:
                yield self
            except BaseException:
                self._state.store = before
                self._state.metadata = metadata
                self._state.epoch += 1
                self._epoch = self._state.epoch
                self._subgraph_views = views
                raise
            finally:
                self._state.transaction_depth = 0

    def snapshot(self) -> dict[str, Any]:
        """Return a detached, versioned snapshot of the entire scope hierarchy."""
        with self._state.lock:
            self._guard()
            return {
                "format": "fastgraph",
                "version": 3,
                "metadata": deepcopy(self._state.metadata),
                "store": json.loads(self._state.store.snapshot()),
            }

    def _default_path(self, format: str | None = None) -> Path:
        name = self._state.metadata["name"]
        if Path(name).name != name or name in {".", ".."} or "/" in name or "\\" in name:
            raise PersistenceError("An explicit path is required for this graph name")
        directory = Path(self.config.get("storage.data_dir", "~/.fastgraph/graphs")).expanduser()
        fmt = format or self.config.get("storage.default_format", "msgpack")
        return directory / f"{name}.{fmt}"

    def save(self, path=None, format: str | None = None, **options) -> Path:
        with self._state.lock:
            self._guard()
            if self._state.transaction_depth:
                raise PersistenceError(
                    "Save after the in-memory transaction commits", operation="save"
                )
            target = self._default_path(format) if path is None else Path(path).expanduser()
            fmt = format or self.persistence_manager.detect_format(target) or "msgpack"
            options.setdefault("durable", self.config.get("persistence.durable", True))
            return self.persistence_manager.save(self.snapshot(), target, format=fmt, **options)

    def load(self, path=None, format: str | None = None, **options) -> Path:
        with self._state.lock:
            self._guard()
            if self._scope != 0 or self._state.transaction_depth:
                raise PersistenceError(
                    "Load requires the root outside a transaction", operation="load"
                )
            target = self._default_path(format) if path is None else Path(path).expanduser()
            options.setdefault(
                "max_bytes", self.config.get("persistence.max_bytes", 256 * 1024 * 1024)
            )
            data = self.persistence_manager.load(target, format=format, **options)
            try:
                encoded = json.dumps(data["store"], ensure_ascii=False, allow_nan=False).encode(
                    "utf-8"
                )
                replacement = NativeStore.from_snapshot(encoded)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                raise PersistenceError(
                    f"Invalid graph snapshot: {exc}", str(target), "load"
                ) from exc
            metadata = data["metadata"]
            if not isinstance(metadata.get("name"), str) or not metadata["name"]:
                raise PersistenceError(
                    "Snapshot metadata requires a graph name", str(target), "load"
                )
            self._state.store = replacement
            self._state.metadata = deepcopy(metadata)
            self._state.epoch += 1
            self._epoch = self._state.epoch
            self._subgraph_views.clear()
            return target

    @classmethod
    def from_file(cls, path, format: str | None = None, config=None, **options) -> FastGraph:
        graph = cls(config=config)
        graph.load(path, format=format, **options)
        return graph

    @classmethod
    def load_graph(
        cls, path_hint=None, graph_name: str | None = None, config=None, **options
    ) -> FastGraph:
        graph = cls(name=graph_name or "fastgraph", config=config)
        graph.load(path_hint, **options)
        return graph

    @classmethod
    def with_config(cls, config, name: str | None = None, **options) -> FastGraph:
        return cls(name=name, config=config, **options)

    def exists(self, path_hint=None) -> bool:
        with self._state.lock:
            self._guard()
            return (
                self._default_path() if path_hint is None else Path(path_hint).expanduser()
            ).is_file()

    def translate(
        self, source_path, target_path, source_format=None, target_format=None, **options
    ) -> Path:
        with self._state.lock:
            self._guard()
            options.setdefault("durable", self.config.get("persistence.durable", True))
            options.setdefault(
                "max_bytes", self.config.get("persistence.max_bytes", 256 * 1024 * 1024)
            )
            return self.persistence_manager.translate(
                source_path, target_path, source_format, target_format, **options
            )

    def backup(self, backup_dir=None) -> list[Path]:
        with self._state.lock:
            self._guard()
            directory = (
                Path(backup_dir)
                if backup_dir is not None
                else Path(self.config.get("storage.backup_directory", "~/.fastgraph/backups"))
            ).expanduser()
            prefix = self._state.metadata["name"]
            if Path(prefix).name != prefix or "/" in prefix or "\\" in prefix:
                raise PersistenceError("A simple graph name is required for backups")
            path = directory / f"{prefix}.{time.time_ns()}.{uuid4().hex}.msgpack"
            return [self.save(path, format="msgpack")]

    def restore_from_backup(self, backup_dir=None, format=None) -> Path:
        directory = (
            Path(backup_dir)
            if backup_dir is not None
            else Path(self.config.get("storage.backup_directory", "~/.fastgraph/backups"))
        ).expanduser()
        candidates = sorted(
            directory.glob(f"{self.name}.*.{format or 'msgpack'}"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if not candidates:
            raise PersistenceError("No backup found", operation="restore")
        return self.load(candidates[0], format=format)

    def close(self) -> None:
        with self._state.lock:
            if self._scope == 0:
                if self._state.transaction_depth:
                    raise ValidationError("Cannot close a store during a transaction")
                self._state.closed = True
                self._state.store = None
            self._closed = True

    def cleanup(self) -> None:
        self.close()

    def __enter__(self) -> FastGraph:
        self._guard()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if (
                exc_type is None
                and self._scope == 0
                and (
                    self.config.get("enhanced_api.auto_save", False)
                    or self.config.get("persistence.auto_save_on_exit", False)
                )
            ):
                self.save()
        finally:
            self.close()
        return False

    def __getitem__(self, node) -> NodeRef:
        return self.resolve(node)

    def __contains__(self, node) -> bool:
        with self._state.lock:
            try:
                self._resolve_id(node)
                return True
            except NodeNotFoundError:
                return False

    def __len__(self) -> int:
        return self.node_count

    def __iter__(self):
        return iter(self.node_ids())

    def __repr__(self) -> str:
        if self._closed or self._state.closed:
            return "FastGraph(closed=True)"
        try:
            return f"FastGraph(name={self.name!r}, path={self.path!r}, nodes={self.node_count}, edges={self.edge_count}, backend='rust')"
        except StaleReferenceError:
            return "FastGraph(stale=True)"

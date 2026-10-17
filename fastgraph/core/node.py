"""Scoped node handles and lazy compound-node promotion."""

from __future__ import annotations

from typing import Any

from ..exceptions import ClosedGraphError, NodeNotFoundError, StaleReferenceError


class NodeRef:
    """A node identity in a shared store; properties and child scopes are separate."""

    __slots__ = ("_state", "_id", "_epoch")

    def __init__(self, state, node_id: int):
        self._state = state
        self._id = node_id
        self._epoch = state.epoch

    def _guard(self) -> None:
        if self._state.closed:
            raise ClosedGraphError("The graph store is closed")
        if self._epoch != self._state.epoch:
            raise StaleReferenceError("Node handle predates a load or transaction rollback")
        if not self._state.store.has_node(self._id):
            raise NodeNotFoundError(str(self._id))

    @property
    def id(self) -> int:
        with self._state.lock:
            self._guard()
            return self._id

    @property
    def local_id(self) -> str:
        with self._state.lock:
            self._guard()
            return self._state.store.node_info(self._id)[1]

    @property
    def path(self) -> tuple[str, ...]:
        with self._state.lock:
            self._guard()
            parts = []
            current = self._id
            while True:
                scope, local_id, _ = self._state.store.node_info(current)
                parts.append(local_id)
                owner = self._state.store.scope_owner(scope)
                if owner is None:
                    break
                current = owner
            return tuple(reversed(parts))

    @property
    def attrs(self) -> dict[str, Any]:
        with self._state.lock:
            self._guard()
            return self._state.store.get_node(self._id)

    @property
    def is_compound(self) -> bool:
        with self._state.lock:
            self._guard()
            return self._state.store.node_info(self._id)[2] is not None

    def enter(self, *, create: bool = True):
        """Select the child graph, creating an empty scope only when requested."""
        from .graph import FastGraph

        with self._state.lock:
            self._guard()
            child = self._state.store.node_info(self._id)[2]
            if child is None:
                if not create:
                    return None
                child = self._state.store.create_scope(self._id)
            return FastGraph._view(self._state, child)

    @property
    def graph(self):
        """Lazily promote this node to a compound node and enter its graph."""
        return self.enter()

    def update(self, **attrs: Any) -> NodeRef:
        from .graph import FastGraph

        with self._state.lock:
            self._guard()
            scope = self._state.store.node_info(self._id)[0]
            return FastGraph._view(self._state, scope).update_node(self, **attrs)

    def traverse(self, *, nested: bool = True, **options):
        from .graph import FastGraph

        with self._state.lock:
            self._guard()
            scope = self._state.store.node_info(self._id)[0]
            return FastGraph._view(self._state, scope).bfs(self, nested=nested, **options)

    def __getitem__(self, local_id: str) -> NodeRef:
        return self.graph[local_id]

    def __hash__(self) -> int:
        return hash((id(self._state), self._epoch, self._id))

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, NodeRef) and self._state is other._state
                and self._epoch == other._epoch and self._id == other._id)

    def __repr__(self) -> str:
        try:
            return f"NodeRef(path={self.path!r})"
        except (ClosedGraphError, StaleReferenceError, NodeNotFoundError):
            return f"NodeRef(id={self._id}, unavailable=True)"

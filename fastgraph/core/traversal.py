"""Native-backed traversal with lazy paths and bounded iterative searches."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ..exceptions import FastGraphError, NodeNotFoundError, TraversalError
from .edge import Edge

if TYPE_CHECKING:
    from .node import NodeRef


def _budget(value, name, *, optional=False, minimum=0):
    if optional and value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if minimum == 1 else "nonnegative"
        raise ValueError(f"{name} must be a {qualifier} integer")


def _path_ids(predecessors, target):
    path = []
    while target is not None:
        path.append(target)
        target = predecessors[target]
    path.reverse()
    return path


class _TraversalPaths(Sequence):
    """Reconstruct only the paths requested by indexing or iteration."""

    __slots__ = ("_result",)

    def __init__(self, result):
        self._result = result

    def __len__(self):
        return self._result.node_count

    def __getitem__(self, index):
        nodes = self._result.nodes[index]
        if isinstance(index, slice):
            return [self._result.path_to(node) for node in nodes]
        return self._result.path_to(nodes)

    def __iter__(self):
        for node in self._result.nodes:
            yield self._result.path_to(node)


class TraversalResult:
    """Discovery order and a predecessor tree, not a collection of full paths.

    Node handles refer to the graph's captured epoch. Discovery edges are copied
    only when requested; the first read requires an unchanged store revision.
    Implicit containment hops have predecessors but no real edges.
    """

    __slots__ = (
        "_graph",
        "_epoch",
        "_revision",
        "nodes",
        "_edge_ids",
        "_edges",
        "_predecessors",
        "_depths",
    )

    def __init__(self, graph, order, predecessors, depths, tree_edges):
        self._graph = graph
        self._epoch = graph._state.epoch
        self._revision = graph._state.store.revision
        self.nodes: tuple[NodeRef, ...] = tuple(graph._node_ref(nid) for nid in order)
        self._edge_ids = tuple(tree_edges[nid] for nid in order if tree_edges.get(nid) is not None)
        self._edges = () if not self._edge_ids else None
        self._predecessors = predecessors
        self._depths = depths

    @property
    def edges(self) -> tuple[Edge, ...]:
        if self._edges is not None:
            return self._edges
        graph = self._graph
        with graph._state.lock:
            self._guard()
            if self._edges is None:
                if graph._state.store.revision != self._revision:
                    raise TraversalError("Graph changed before discovery edges were read")
                self._edges = tuple(graph._edge_ref(eid) for eid in self._edge_ids)
            return self._edges

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edge_ids)

    @property
    def depth(self) -> int:
        return max(self._depths.values(), default=0)

    @property
    def path_count(self) -> int:
        return self.node_count

    @property
    def paths(self) -> Sequence:
        return _TraversalPaths(self)

    @property
    def node_paths(self) -> tuple[tuple[str, ...], ...]:
        graph = self._graph
        with graph._state.lock:
            self._guard()
            return tuple(node.path for node in self.nodes)

    def _guard(self):
        self._graph._guard()
        if self._graph._state.epoch != self._epoch:
            raise TraversalError("Traversal result belongs to an invalidated graph")

    def path_to(self, node) -> list[NodeRef] | None:
        graph = self._graph
        with graph._state.lock:
            self._guard()
            nid = graph._resolve_id(node)
            if nid not in self._predecessors:
                return None
            ids = _path_ids(self._predecessors, nid)
            for path_id in ids:
                if not graph._state.store.has_node(path_id):
                    raise NodeNotFoundError(path_id)
            return [graph._node_ref(path_id) for path_id in ids]

    def __repr__(self):
        return (
            f"TraversalResult(nodes={self.node_count}, edges={self.edge_count}, depth={self.depth})"
        )


class TraversalOperations:
    """Traverse actual directed edges, optionally adding containment hops.

    Property and node filters select allowed IDs across the whole store, so
    explicit cross-scope edges remain traversable. Node callbacks receive a
    local-or-qualified ID and copied attributes. Edge callbacks receive copied
    edges and use the slower, iterative reference search. Neither callback is
    invoked for an implicit containment edge.
    """

    def __init__(self, graph, *, allowed=None):
        self.graph = graph
        self._allowed = None if allowed is None else frozenset(allowed)

    def _validate(
        self,
        max_depth=None,
        max_nodes=None,
        direction="out",
        nested=False,
        rel=None,
        node_filter=None,
        edge_filter=None,
        filters=None,
    ):
        _budget(max_depth, "max_depth", optional=True)
        _budget(max_nodes, "max_nodes", optional=True, minimum=1)
        if direction not in ("out", "in", "both"):
            raise ValueError("direction must be 'out', 'in', or 'both'")
        if not isinstance(nested, bool):
            raise ValueError("nested must be a boolean")
        if rel is not None and not isinstance(rel, str):
            raise ValueError("rel must be a string or None")
        if node_filter is not None and not callable(node_filter):
            raise ValueError("node_filter must be callable")
        if edge_filter is not None and not callable(edge_filter):
            raise ValueError("edge_filter must be callable")
        if filters is not None and not isinstance(filters, Mapping):
            raise ValueError("filters must be a mapping")

    def _resolve(self, value):
        nid = self.graph._resolve_id(value)
        if self._allowed is not None and nid not in self._allowed:
            raise NodeNotFoundError(value)
        return nid

    def _check_version(self, epoch, revision, operation):
        self.graph._guard()
        state = self.graph._state
        if state.epoch != epoch or state.store.revision != revision:
            raise TraversalError("Graph changed during traversal", operation=operation)

    def _callback(self, callback, args, operation):
        state = self.graph._state
        epoch, revision = state.epoch, state.store.revision
        try:
            accepted = bool(callback(*args))
        except FastGraphError:
            raise
        except Exception as exc:
            raise TraversalError(f"Traversal callback failed: {exc}", operation=operation) from exc
        self._check_version(epoch, revision, operation)
        return accepted

    def _allowed_ids(self, start, node_filter, filters):
        store = self.graph._state.store
        allowed = None
        if self._allowed is not None:
            allowed = {nid for nid in self._allowed if store.has_node(nid)}
        if filters:
            selected = set(
                store.find_nodes(0, self.graph._parse_filters(dict(filters)), recursive=True)
            )
            allowed = selected if allowed is None else allowed & selected
        if node_filter is not None:
            candidates = store.node_ids(0, recursive=True) if allowed is None else sorted(allowed)
            selected = set()
            for nid in candidates:
                if nid == start:
                    continue
                ref = self.graph._node_ref(nid)
                if self._callback(
                    node_filter, (self.graph._display_id(nid), ref.attrs), "node_filter"
                ):
                    selected.add(nid)
            allowed = selected
        if allowed is not None:
            allowed.add(start)
        return allowed

    def _steps(self, nid, direction, rel, nested):
        store = self.graph._state.store
        yield from store.neighbors(nid, direction=direction, rel=rel)
        if nested:
            scope, _, child_scope = store.node_info(nid)
            if direction in ("out", "both") and child_scope is not None:
                for child in store.node_ids(child_scope):
                    yield child, None
            if direction in ("in", "both"):
                owner = store.scope_owner(scope)
                if owner is not None:
                    yield owner, None

    def _accept_edge(self, edge_id, edge_filter):
        return (
            edge_filter is None
            or edge_id is None
            or self._callback(edge_filter, (self.graph._edge_ref(edge_id),), "edge_filter")
        )

    def _neighbors(self, node, direction, rel, edge_filter):
        self._validate(direction=direction, rel=rel, edge_filter=edge_filter)
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            nid = self._resolve(node)
            result = []
            for neighbor, edge_id in graph._state.store.neighbors(
                nid, direction=direction, rel=rel
            ):
                if self._allowed is not None and neighbor not in self._allowed:
                    continue
                edge = graph._edge_ref(edge_id)
                if edge_filter is None or self._callback(edge_filter, (edge,), "edge_filter"):
                    result.append((graph._display_id(neighbor), edge))
            return result

    def neighbors_out(self, node, rel=None, edge_filter=None):
        return self._neighbors(node, "out", rel, edge_filter)

    def neighbors_in(self, node, rel=None, edge_filter=None):
        return self._neighbors(node, "in", rel, edge_filter)

    def neighbors(self, node, rel=None, edge_filter=None):
        return self._neighbors(node, "both", rel, edge_filter)

    def degree(self, node, rel=None) -> tuple[int, int, int]:
        self._validate(rel=rel)
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            nid = self._resolve(node)
            store = graph._state.store
            if rel is None and self._allowed is None:
                outgoing, incoming = store.degree(nid)
            else:
                outgoing = sum(
                    self._allowed is None or neighbor in self._allowed
                    for neighbor, _ in store.neighbors(nid, direction="out", rel=rel)
                )
                incoming = sum(
                    self._allowed is None or neighbor in self._allowed
                    for neighbor, _ in store.neighbors(nid, direction="in", rel=rel)
                )
            return outgoing, incoming, outgoing + incoming

    def _search(
        self,
        start,
        max_depth,
        rel,
        edge_filter,
        direction,
        nested,
        max_nodes,
        allowed,
        *,
        dfs=False,
    ):
        store = self.graph._state.store
        if not dfs and edge_filter is None:
            ids, parents, depths, edges = store.bfs(
                start,
                max_depth=max_depth,
                direction=direction,
                rel=rel,
                nested=nested,
                max_nodes=max_nodes,
                allowed=None if allowed is None else list(allowed),
            )
            return ids, dict(zip(ids, parents)), dict(zip(ids, depths)), dict(zip(ids, edges))

        order = [start]
        parents = {start: None}
        depths = {start: 0}
        edges = {start: None}
        if not dfs:
            queue = deque([start])
            while queue:
                current = queue.popleft()
                if max_depth is not None and depths[current] >= max_depth:
                    continue
                if max_nodes is not None and len(order) >= max_nodes:
                    break
                for neighbor, edge_id in self._steps(current, direction, rel, nested):
                    if neighbor in depths or (allowed is not None and neighbor not in allowed):
                        continue
                    if not self._accept_edge(edge_id, edge_filter):
                        continue
                    parents[neighbor] = current
                    depths[neighbor] = depths[current] + 1
                    edges[neighbor] = edge_id
                    order.append(neighbor)
                    queue.append(neighbor)
                    if max_nodes is not None and len(order) >= max_nodes:
                        break
            return order, parents, depths, edges

        stack = [(start, 0, None)]
        while stack:
            current, depth, neighbors = stack[-1]
            if depth != depths[current] or (max_depth is not None and depth >= max_depth):
                stack.pop()
                continue
            if neighbors is None:
                neighbors = iter(self._steps(current, direction, rel, nested))
                stack[-1] = current, depth, neighbors
            try:
                neighbor, edge_id = next(neighbors)
            except StopIteration:
                stack.pop()
                continue
            if allowed is not None and neighbor not in allowed:
                continue
            next_depth = depth + 1
            previous_depth = depths.get(neighbor)
            if previous_depth is not None:
                # A first, deeper visit must not hide a later route within the bound.
                if max_depth is None or next_depth >= previous_depth:
                    continue
            elif max_nodes is not None and len(order) >= max_nodes:
                continue
            if not self._accept_edge(edge_id, edge_filter):
                continue
            if previous_depth is None:
                order.append(neighbor)
            parents[neighbor] = current
            depths[neighbor] = next_depth
            edges[neighbor] = edge_id
            stack.append((neighbor, next_depth, None))
        return order, parents, depths, edges

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
    ) -> TraversalResult:
        self._validate(
            max_depth, max_nodes, direction, nested, rel, node_filter, edge_filter, filters
        )
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            nid = self._resolve(start)
            allowed = self._allowed_ids(nid, node_filter, filters)
            data = self._search(
                nid, max_depth, rel, edge_filter, direction, nested, max_nodes, allowed
            )
            return TraversalResult(graph, *data)

    def dfs(
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
    ) -> TraversalResult:
        """Depth-first discovery; bounded searches revisit improved depths.

        With a depth bound, final predecessors describe shortest valid routes
        among the admitted nodes, even if those nodes were discovered deeply.
        """
        self._validate(
            max_depth, max_nodes, direction, nested, rel, node_filter, edge_filter, filters
        )
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            nid = self._resolve(start)
            allowed = self._allowed_ids(nid, node_filter, filters)
            data = self._search(
                nid, max_depth, rel, edge_filter, direction, nested, max_nodes, allowed, dfs=True
            )
            return TraversalResult(graph, *data)

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
        self._validate(
            max_depth=max_depth,
            direction=direction,
            nested=nested,
            rel=rel,
            node_filter=node_filter,
            edge_filter=edge_filter,
            filters=filters,
        )
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            start_id, end_id = self._resolve(start), self._resolve(end)
            if start_id == end_id:
                return [graph._node_ref(start_id)]
            allowed = self._allowed_ids(start_id, node_filter, filters)
            if allowed is None and edge_filter is None:
                ids = graph._state.store.shortest_path(
                    start_id,
                    end_id,
                    direction=direction,
                    rel=rel,
                    nested=nested,
                    max_depth=max_depth,
                )
            else:
                _, parents, _, _ = self._search(
                    start_id, max_depth, rel, edge_filter, direction, nested, None, allowed
                )
                ids = _path_ids(parents, end_id) if end_id in parents else None
            return None if ids is None else [graph._node_ref(nid) for nid in ids]

    def all_shortest_paths(
        self,
        start,
        end,
        rel=None,
        edge_filter=None,
        *,
        direction="out",
        nested=False,
        max_depth=None,
        max_paths=1000,
        node_filter=None,
        filters=None,
    ):
        """Enumerate at most max_paths distinct node paths from a predecessor DAG."""
        _budget(max_paths, "max_paths", minimum=1)
        self._validate(
            max_depth=max_depth,
            direction=direction,
            nested=nested,
            rel=rel,
            node_filter=node_filter,
            edge_filter=edge_filter,
            filters=filters,
        )
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            start_id, end_id = self._resolve(start), self._resolve(end)
            allowed = self._allowed_ids(start_id, node_filter, filters)
            if start_id == end_id:
                return [[graph._node_ref(start_id)]]
            distances = {start_id: 0}
            predecessors = {start_id: []}
            queue = deque([start_id])
            target_depth = None
            while queue:
                current = queue.popleft()
                depth = distances[current]
                if target_depth is not None and depth >= target_depth:
                    break
                if max_depth is not None and depth >= max_depth:
                    continue
                seen = set()
                for neighbor, edge_id in self._steps(current, direction, rel, nested):
                    if neighbor in seen or (allowed is not None and neighbor not in allowed):
                        continue
                    if not self._accept_edge(edge_id, edge_filter):
                        continue
                    seen.add(neighbor)
                    next_depth = depth + 1
                    if neighbor not in distances:
                        distances[neighbor] = next_depth
                        predecessors[neighbor] = [current]
                        queue.append(neighbor)
                    elif distances[neighbor] == next_depth:
                        predecessors[neighbor].append(current)
                    if neighbor == end_id:
                        target_depth = next_depth
            if end_id not in distances:
                return []

            paths = []
            reverse_path = [end_id]
            stack = [iter(predecessors[end_id])]
            while stack and len(paths) < max_paths:
                if reverse_path[-1] == start_id:
                    paths.append([graph._node_ref(nid) for nid in reversed(reverse_path)])
                    stack.pop()
                    reverse_path.pop()
                    continue
                try:
                    parent = next(stack[-1])
                except StopIteration:
                    stack.pop()
                    reverse_path.pop()
                    continue
                reverse_path.append(parent)
                stack.append(iter(predecessors[parent]))
            return paths

    def find_paths(
        self,
        start,
        end,
        max_length=None,
        edge_filter=None,
        *,
        rel=None,
        direction="out",
        nested=False,
        max_depth=None,
        max_paths=1000,
        max_expansions=100000,
        node_filter=None,
        filters=None,
    ):
        """Yield simple paths with explicit path and examined-adjacency budgets.

        max_depth counts hops; the legacy max_length counts nodes in a path.
        The lock is released before each yield. Mutation between yields fails
        rather than mixing observations from different native revisions.
        """
        _budget(max_paths, "max_paths", minimum=1)
        _budget(max_expansions, "max_expansions", minimum=1)
        _budget(max_length, "max_length", optional=True)
        self._validate(
            max_depth=max_depth,
            direction=direction,
            nested=nested,
            rel=rel,
            node_filter=node_filter,
            edge_filter=edge_filter,
            filters=filters,
        )
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            start_id, end_id = self._resolve(start), self._resolve(end)
            allowed = self._allowed_ids(start_id, node_filter, filters)
            epoch, revision = graph._state.epoch, graph._state.store.revision
        depth_limit = max_depth
        if max_length is not None:
            depth_limit = (
                max_length - 1 if depth_limit is None else min(depth_limit, max_length - 1)
            )

        def generate():
            if depth_limit is not None and depth_limit < 0:
                return
            path = [start_id]
            in_path = {start_id}
            stack = [None]
            expansions = yielded = 0
            while stack:
                with graph._state.lock:
                    self._check_version(epoch, revision, "find_paths")
                    while stack:
                        current = path[-1]
                        if current == end_id:
                            found = [graph._node_ref(nid) for nid in path]
                            stack.pop()
                            in_path.remove(path.pop())
                            yielded += 1
                            break
                        if depth_limit is not None and len(path) - 1 >= depth_limit:
                            stack.pop()
                            in_path.remove(path.pop())
                            continue
                        if stack[-1] is None:
                            stack[-1] = (iter(self._steps(current, direction, rel, nested)), set())
                        neighbors, seen = stack[-1]
                        try:
                            neighbor, edge_id = next(neighbors)
                        except StopIteration:
                            stack.pop()
                            in_path.remove(path.pop())
                            continue
                        expansions += 1
                        if expansions > max_expansions:
                            raise TraversalError(
                                "Path expansion budget exhausted", operation="find_paths"
                            )
                        if (
                            neighbor in seen
                            or neighbor in in_path
                            or (allowed is not None and neighbor not in allowed)
                        ):
                            continue
                        if not self._accept_edge(edge_id, edge_filter):
                            continue
                        seen.add(neighbor)
                        path.append(neighbor)
                        in_path.add(neighbor)
                        stack.append(None)
                    else:
                        return
                yield found
                if yielded >= max_paths:
                    return

        return generate()

    def connected_components(self, edge_filter=None, *, recursive=False):
        """Weak components induced by the requested scope, never scope exits."""
        self._validate(edge_filter=edge_filter)
        if not isinstance(recursive, bool):
            raise ValueError("recursive must be a boolean")
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            store = graph._state.store
            if edge_filter is None and self._allowed is None:
                components = store.connected_components(graph._scope, recursive=recursive)
            else:
                candidates = store.node_ids(graph._scope, recursive=recursive)
                if self._allowed is not None:
                    candidates = [nid for nid in sorted(self._allowed) if store.has_node(nid)]
                remaining = set(candidates)
                components = []
                for start in candidates:
                    if start not in remaining:
                        continue
                    remaining.remove(start)
                    component = [start]
                    queue = deque([start])
                    while queue:
                        current = queue.popleft()
                        for neighbor, edge_id in store.neighbors(current, direction="both"):
                            if neighbor in remaining and self._accept_edge(edge_id, edge_filter):
                                remaining.remove(neighbor)
                                component.append(neighbor)
                                queue.append(neighbor)
                    components.append(component)
            return [{graph._node_ref(nid) for nid in component} for component in components]

    def weakly_connected_components(self, *, recursive=False):
        return self.connected_components(recursive=recursive)

    def topological_sort(self, *, recursive=False):
        if not isinstance(recursive, bool):
            raise ValueError("recursive must be a boolean")
        graph = self.graph
        with graph._state.lock:
            graph._guard()
            ids = graph._state.store.topological_sort(graph._scope, recursive=recursive)
            return None if ids is None else [graph._node_ref(nid) for nid in ids]

    def has_cycles(self, *, recursive=False) -> bool:
        return self.topological_sort(recursive=recursive) is None

    def __repr__(self):
        return f"TraversalOperations(graph.nodes={self.graph.node_count})"

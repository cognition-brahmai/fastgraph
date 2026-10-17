"""Benchmark-only adapters for directed, uniquely keyed relationship graphs.

``add_nodes`` and ``add_edges`` accept unique initial-load batches. Repeated
relationship keys belong in ``upsert_edges``, which replaces properties.
Identifiers are strings; hashable qualified tuples also work without coercion.
Only the selected comparator is imported by ``Peer``.

NetworkX uses external IDs and relation keys directly. Rustworkx retains an
external-ID/index map and node/edge payloads ``(external_id, attrs)`` and
``(rel, attrs)``. Igraph retains the same ID/index map, with ``__fg_id`` vertex
and ``__fg_rel`` edge columns alongside property columns. Its missing-property
sentinel preserves absent versus explicit None without per-entity dictionaries.
These mappings, payloads, and their construction are part of adapter costs.

Property reads are live dictionaries for NetworkX/rustworkx, assembled shallow
dictionaries for igraph. Nested property containers can be shared; callers must
deep-copy returned properties when benchmarking detached-value semantics.
BFS retains each library's materialized native result, not identical payloads:
NetworkX discovery successors, rustworkx adjacency successors (including repeat
children), and igraph's visited/layer/parent arrays. Counts are derived from the
actual payloads; rustworkx additionally deduplicates reached external IDs.
"""

from __future__ import annotations

import warnings


_MISSING = object()
_IG_ID = "__fg_id"
_IG_REL = "__fg_rel"


class Peer:
    def __init__(self, engine: str):
        self.engine = engine
        if engine == "networkx":
            import networkx

            self._lib = networkx
            self._graph = networkx.MultiDiGraph()
        elif engine == "rustworkx":
            import rustworkx

            self._lib = rustworkx
            self._graph = rustworkx.PyDiGraph(multigraph=True)
            self._ids = {}
        elif engine == "igraph":
            import igraph

            self._lib = igraph
            self._graph = igraph.Graph(directed=True)
            self._ids = {}
        else:
            raise ValueError(f"Unknown benchmark peer: {engine!r}")

    @property
    def internal(self):
        """Underlying library graph, including adapter-reserved payloads/columns."""
        return self._graph

    @property
    def ids(self):
        """External-ID/index mapping for numeric-ID engines, None for NetworkX."""
        return None if self.engine == "networkx" else self._ids

    def _ig_add(self, entries: list, *, vertices: bool) -> None:
        if not entries:
            return
        graph = self._graph
        sequence = graph.vs if vertices else graph.es
        reserved = _IG_ID if vertices else _IG_REL
        count = graph.vcount() if vertices else graph.ecount()
        existing = set(sequence.attributes())
        names = dict.fromkeys(existing - {reserved})
        for entry in entries:
            if reserved in entry[-1]:
                raise ValueError(f"Igraph adapter reserves property {reserved!r}")
            for name in entry[-1]:
                names.setdefault(name, None)
        columns = {name: [entry[-1].get(name, _MISSING) for entry in entries] for name in names}
        columns[reserved] = [entry[0 if vertices else 2] for entry in entries]
        if vertices:
            endpoints = len(entries)
        else:
            endpoints = [(self._ids[src], self._ids[dst]) for src, dst, _, _ in entries]
        for name in names:
            if count and name not in existing:
                sequence[name] = [_MISSING] * count
        if vertices:
            graph.add_vertices(endpoints, attributes=columns)
        else:
            graph.add_edges(endpoints, attributes=columns)

    def add_nodes(self, nodes: list[tuple[str, dict]]) -> None:
        if self.engine == "networkx":
            self._graph.add_nodes_from(nodes)
        elif self.engine == "rustworkx":
            indices = self._graph.add_nodes_from(
                [(identifier, dict(attrs)) for identifier, attrs in nodes]
            )
            self._ids.update((node[0], index) for node, index in zip(nodes, indices))
        else:
            start = self._graph.vcount()
            self._ig_add(nodes, vertices=True)
            self._ids.update((node[0], start + index) for index, node in enumerate(nodes))

    def add_edges(self, edges: list[tuple[str, str, str, dict]]) -> None:
        if self.engine == "networkx":
            self._graph.add_edges_from(edges)
        elif self.engine == "rustworkx":
            self._graph.add_edges_from(
                [
                    (self._ids[src], self._ids[dst], (rel, dict(attrs)))
                    for src, dst, rel, attrs in edges
                ]
            )
        else:
            self._ig_add(edges, vertices=False)

    def _edge_index(self, src: str, dst: str, rel: str) -> int | None:
        source = self._ids.get(src)
        target = self._ids.get(dst)
        if source is None or target is None:
            return None
        graph = self._graph
        if self.engine == "rustworkx":
            for index in graph.edge_indices_from_endpoints(source, target):
                if graph.get_edge_data_by_index(index)[0] == rel:
                    return index
        else:
            index = graph.get_eid(source, target, directed=True, error=False)
            if index < 0:
                return None
            if graph.es[index][_IG_REL] == rel:
                return index
            for edge in graph.es.select(_source=source, _target=target):
                if edge[_IG_REL] == rel:
                    return edge.index
        return None

    def upsert_edges(self, edges: list[tuple[str, str, str, dict]]) -> None:
        graph = self._graph
        if self.engine == "networkx":
            for src, dst, rel, attrs in edges:
                previous = graph.get_edge_data(src, dst, key=rel)
                if previous is None:
                    graph.add_edges_from([(src, dst, rel, attrs)])
                else:
                    replacement = dict(attrs)
                    previous.clear()
                    previous.update(replacement)
            return
        unique = {(src, dst, rel): attrs for src, dst, rel, attrs in edges}
        if self.engine == "igraph":
            names = dict.fromkeys(set(graph.es.attributes()) - {_IG_REL})
            for attrs in unique.values():
                if _IG_REL in attrs:
                    raise ValueError(f"Igraph adapter reserves property {_IG_REL!r}")
                for name in attrs:
                    names.setdefault(name, None)
            existing = set(graph.es.attributes())
            for name in names:
                if name not in existing:
                    graph.es[name] = [_MISSING] * graph.ecount()
        additions = []
        for (src, dst, rel), attrs in unique.items():
            index = self._edge_index(src, dst, rel)
            if index is None:
                additions.append((src, dst, rel, attrs))
            elif self.engine == "rustworkx":
                graph.update_edge_by_index(index, (rel, dict(attrs)))
            else:
                edge = graph.es[index]
                for name in names:
                    edge[name] = attrs.get(name, _MISSING)
        self.add_edges(additions)

    def get_node(self, identifier: str) -> dict:
        if self.engine == "networkx":
            return self._graph.nodes[identifier]
        if self.engine == "rustworkx":
            return self._graph[self._ids[identifier]][1]
        return {
            name: value
            for name, value in self._graph.vs[self._ids[identifier]].attributes().items()
            if name != _IG_ID and value is not _MISSING
        }

    def has_edge(self, src: str, dst: str, rel: str) -> bool:
        if self.engine == "networkx":
            return self._graph.has_edge(src, dst, key=rel)
        if self.engine == "rustworkx":
            return self.get_edge(src, dst, rel) is not None
        return self._edge_index(src, dst, rel) is not None

    def get_edge(self, src: str, dst: str, rel: str) -> dict | None:
        graph = self._graph
        if self.engine == "networkx":
            return graph.get_edge_data(src, dst, key=rel)
        if self.engine == "rustworkx":
            source = self._ids.get(src)
            target = self._ids.get(dst)
            if source is None or target is None:
                return None
            try:
                data = graph.get_edge_data(source, target)
            except self._lib.NoEdgeBetweenNodes:
                return None
            if data[0] == rel:
                return data[1]
            for edge_rel, attrs in graph.get_all_edge_data(source, target):
                if edge_rel == rel:
                    return attrs
            return None
        index = self._edge_index(src, dst, rel)
        if index is None:
            return None
        return {
            name: value
            for name, value in graph.es[index].attributes().items()
            if name != _IG_REL and value is not _MISSING
        }

    def neighbors_out(self, identifier: str) -> list[str]:
        graph = self._graph
        if self.engine == "networkx":
            return [dst for _, dst, _ in graph.out_edges(identifier, keys=True)]
        if self.engine == "rustworkx":
            return [graph[dst][0] for _, dst, _ in graph.out_edges(self._ids[identifier])]
        indices = graph.neighbors(self._ids[identifier], mode="out", multiple=True)
        return graph.vs[indices][_IG_ID]

    def degree(self, identifier: str) -> tuple[int, int]:
        graph = self._graph
        if self.engine == "networkx":
            return graph.out_degree(identifier), graph.in_degree(identifier)
        index = self._ids[identifier]
        if self.engine == "rustworkx":
            return graph.out_degree(index), graph.in_degree(index)
        return graph.degree(index, mode="out"), graph.degree(index, mode="in")

    def counts(self) -> tuple[int, int]:
        if self.engine == "networkx":
            return self._graph.number_of_nodes(), self._graph.number_of_edges()
        if self.engine == "rustworkx":
            return self._graph.num_nodes(), self._graph.num_edges()
        return self._graph.vcount(), self._graph.ecount()

    def bfs(self, start: str) -> tuple[int, object]:
        if self.engine == "networkx":
            payload = list(self._lib.bfs_successors(self._graph, start))
            return 1 + sum(len(children) for _, children in payload), payload
        if self.engine == "rustworkx":
            payload = self._lib.bfs_successors(self._graph, self._ids[start])
            visited = {start}
            for parent, children in payload:
                visited.add(parent[0])
                visited.update(child[0] for child in children)
            return len(visited), payload
        payload = self._graph.bfs(self._ids[start], mode="out")
        return len(payload[0]), payload

    def shortest_path(self, start: str, end: str) -> list[str] | None:
        graph = self._graph
        if self.engine == "networkx":
            if start not in graph or end not in graph:
                return None
            try:
                return self._lib.shortest_path(graph, source=start, target=end, weight=None)
            except self._lib.NetworkXNoPath:
                return None
        source = self._ids.get(start)
        target = self._ids.get(end)
        if source is None or target is None:
            return None
        if source == target:
            return [start]
        if self.engine == "rustworkx":
            paths = self._lib.digraph_dijkstra_shortest_paths(
                graph, source, target=target, weight_fn=None
            )
            if target not in paths:
                return None
            return [graph[index][0] for index in paths[target]]
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Couldn't reach some vertices.*", category=RuntimeWarning
            )
            path = graph.get_shortest_paths(source, to=target, weights=None, mode="out")[0]
        return graph.vs[path][_IG_ID] if path else None

    def remove_nodes(self, ids: list[str]) -> None:
        if self.engine == "networkx":
            self._graph.remove_nodes_from(ids)
        elif self.engine == "rustworkx":
            indices = [self._ids.pop(identifier) for identifier in ids if identifier in self._ids]
            self._graph.remove_nodes_from(indices)
        else:
            indices = {self._ids[identifier] for identifier in ids if identifier in self._ids}
            if indices:
                self._graph.delete_vertices(list(indices))
                self._ids = {
                    identifier: index for index, identifier in enumerate(self._graph.vs[_IG_ID])
                }

    def remove_edges(self, keys: list[tuple[str, str, str]]) -> int:
        graph = self._graph
        if self.engine == "networkx":
            existing = {key for key in keys if graph.has_edge(*key)}
            graph.remove_edges_from(existing)
            return len(existing)
        if self.engine == "rustworkx":
            indices = {index for key in keys if (index := self._edge_index(*key)) is not None}
            for index in indices:
                graph.remove_edge_from_index(index)
            return len(indices)
        translated = [
            (self._ids[src], self._ids[dst], rel, (src, dst, rel))
            for src, dst, rel in keys
            if src in self._ids and dst in self._ids
        ]
        edge_ids = graph.get_eids(
            pairs=[(src, dst) for src, dst, _, _ in translated],
            directed=True,
            error=False,
        )
        indices = set()
        for (_, _, rel, key), index in zip(translated, edge_ids):
            if index < 0:
                continue
            if graph.es[index][_IG_REL] != rel:
                index = self._edge_index(*key)
            if index is not None:
                indices.add(index)
        if indices:
            graph.delete_edges(list(indices))
        return len(indices)

    def clear(self) -> None:
        self._graph.clear()
        if self.engine != "networkx":
            self._ids.clear()
        if self.engine == "igraph":
            # igraph 1.0.0 retains attribute column names after Graph.clear().
            for name in self._graph.vs.attributes():
                del self._graph.vs[name]
            for name in self._graph.es.attributes():
                del self._graph.es[name]

    def topological_sort(self) -> list[str] | None:
        if self.engine == "networkx":
            try:
                return list(self._lib.topological_sort(self._graph))
            except self._lib.NetworkXUnfeasible:
                return None
        if self.engine == "rustworkx":
            try:
                indices = self._lib.topological_sort(self._graph)
            except self._lib.DAGHasCycle:
                return None
            return [self._graph[index][0] for index in indices]
        if not self._graph.is_dag():
            return None
        indices = self._graph.topological_sorting(mode="out")
        return self._graph.vs[indices][_IG_ID] if indices else []

    def components(self) -> list[list[str]]:
        """Materialized weakly connected components, including isolated nodes."""
        if self.engine == "networkx":
            return [
                list(component) for component in self._lib.weakly_connected_components(self._graph)
            ]
        if self.engine == "rustworkx":
            return [
                [self._graph[index][0] for index in component]
                for component in self._lib.weakly_connected_components(self._graph)
            ]
        if not self._graph.vcount():
            return []
        labels = self._graph.vs[_IG_ID]
        return [
            [labels[index] for index in component]
            for component in self._graph.connected_components(mode="weak")
        ]

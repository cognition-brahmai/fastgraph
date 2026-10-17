"""Isolated, correctness-checked release benchmarks; emits raw JSON, not speed claims."""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor


SEED = 20261017
ENGINES = ("fastgraph", "native", "networkx", "rustworkx", "igraph")
METRIC_KEYS = ("wall_ms", "cpu_ms", "per_op_us", "throughput_per_s", "rss_delta_mib")


def memory():
    import psutil

    info = psutil.Process().memory_info()
    return {
        "rss_mib": info.rss / 2**20,
        "private_mib": getattr(info, "private", info.vms) / 2**20,
        "peak_rss_mib": getattr(info, "peak_wset", info.rss) / 2**20,
        "peak_commit_mib": getattr(info, "peak_pagefile", info.vms) / 2**20,
        "page_faults": getattr(info, "num_page_faults", 0),
    }


class Meter:
    def __init__(self):
        self.metrics = {}

    def run(self, name, function, *, repeats=1, units=1, validate=None, warmup=False):
        if warmup:
            value = function()
            if validate:
                validate(value)
            del value
        gc.collect()
        before = memory()
        walls, cpus = [], []
        result = None
        for _ in range(repeats):
            result = None
            cpu = time.process_time_ns()
            started = time.perf_counter_ns()
            result = function()
            walls.append((time.perf_counter_ns() - started) / 1e6)
            cpus.append((time.process_time_ns() - cpu) / 1e6)
            if validate:
                validate(result)
        after = memory()
        wall = statistics.median(walls)
        self.metrics[name] = {
            "wall_ms": wall,
            "cpu_ms": statistics.median(cpus),
            "repeats_in_process": repeats,
            "wall_samples_ms": walls,
            "operations": units,
            "per_op_us": wall * 1000 / max(units, 1),
            "throughput_per_s": units * 1000 / wall if wall else None,
            "rss_delta_mib": after["rss_mib"] - before["rss_mib"],
            "memory_before": before,
            "memory_after": after,
        }
        return result

    def latency(self, name, function, keys, *, validate=None):
        durations = []
        for key in keys[:10]:
            function(key)
        gc.collect()
        before = memory()
        for key in keys:
            started = time.perf_counter_ns()
            result = function(key)
            durations.append((time.perf_counter_ns() - started) / 1000)
            if validate:
                validate(result)
        ordered = sorted(durations)

        def percentile(q):
            return ordered[max(0, math.ceil(q * len(ordered)) - 1)]

        self.metrics[name] = {
            "operations": len(keys),
            "p50_us": percentile(0.50),
            "p95_us": percentile(0.95),
            "p99_us": percentile(0.99),
            "min_us": ordered[0],
            "max_us": ordered[-1],
            "timer_overhead_not_subtracted": True,
            "memory_before": before,
            "memory_after": memory(),
        }


class Backend:
    """The native layer is a diagnostic, not a semantics-identical public competitor."""

    def __init__(self, engine):
        self.engine = engine
        self.mapping = {}
        if engine == "fastgraph":
            from fastgraph import FastGraph

            self.graph = FastGraph(
                "benchmark", config={"persistence": {"auto_save_on_exit": False}}
            )
            self.store = self.graph._state.store
        elif engine == "native":
            from fastgraph._native import NativeStore

            self.graph = self.store = NativeStore()
        else:
            from _peers import Peer

            self.graph = Peer(engine)
            self.store = None

    def add_nodes(self, nodes):
        if self.engine == "fastgraph":
            self.graph.add_nodes_batch(nodes)
        elif self.engine == "native":
            self.mapping.update(zip((key for key, _ in nodes), self.store.add_nodes(0, nodes)))
        else:
            self.graph.add_nodes(nodes)

    def add_edges(self, edges):
        if self.engine == "fastgraph":
            self.graph.add_edges_batch(edges)
        elif self.engine == "native":
            self.store.add_edges_local(0, edges)
        else:
            self.graph.add_edges(edges)

    def upsert_edges(self, edges):
        if self.engine in ("fastgraph", "native"):
            self.add_edges(edges)
        else:
            self.graph.upsert_edges(edges)

    def counts(self):
        if self.store is not None:
            info = self.store.stats(0)
            return info["nodes"], info["edges"]
        return self.graph.counts()

    def get_node(self, key):
        if self.engine == "native":
            return self.store.get_node(self.mapping[key])
        return self.graph.get_node(key)

    def get_edge(self, key):
        if self.engine == "fastgraph":
            result = self.graph.get_edge(*key)
            return None if result is None else result.attrs
        if self.engine == "native":
            result = self.store.edge_local(0, *key)
            return None if result is None else result[1]
        return self.graph.get_edge(*key)

    def has_edge(self, key):
        if self.engine == "native":
            return self.store.has_edge_local(0, *key)
        return self.graph.has_edge(*key)

    def neighbors(self, key):
        if self.engine == "fastgraph":
            return self.graph.neighbor_nodes(key)
        if self.engine == "native":
            return self.store.neighbors(self.mapping[key])
        return self.graph.neighbors_out(key)

    def degree(self, key):
        if self.engine == "native":
            return self.store.degree(self.mapping[key])
        return self.graph.degree(key)[:2]

    def bfs(self, start):
        if self.engine == "fastgraph":
            result = self.graph.bfs(start)
            return result.node_count, result
        if self.engine == "native":
            result = self.store.bfs(self.mapping[start])
            return len(result[0]), result
        return self.graph.bfs(start)

    def shortest(self, start, target):
        if self.engine == "fastgraph":
            result = self.graph.shortest_path(start, target)
            return None if result is None else [node.local_id for node in result]
        if self.engine == "native":
            return self.store.shortest_path(self.mapping[start], self.mapping[target])
        return self.graph.shortest_path(start, target)

    def remove_edges(self, keys):
        if self.engine == "fastgraph":
            return sum(self.graph.remove_edge(*key) for key in keys)
        if self.engine == "native":
            ids = [
                self.store.edge_id(self.mapping[src], self.mapping[dst], rel)
                for src, dst, rel in keys
            ]
            return self.store.remove_edges([edge for edge in ids if edge is not None])
        return self.graph.remove_edges(keys)

    def remove_nodes(self, nodes):
        if self.engine == "fastgraph":
            for node in nodes:
                self.graph.remove_node(node)
        elif self.engine == "native":
            for node in nodes:
                self.store.remove_node(self.mapping[node])
        else:
            self.graph.remove_nodes(nodes)

    def update_nodes(self, nodes):
        if self.engine == "fastgraph":
            for key, score in nodes:
                self.graph.update_node(key, score=score)
        elif self.engine == "native":
            replacement = [(key, {**self.get_node(key), "score": score}) for key, score in nodes]
            self.store.add_nodes(0, replacement)
        else:
            for key, score in nodes:
                attrs = self.graph.get_node(key)
                attrs["score"] = score
                if self.engine == "igraph":
                    self.graph.internal.vs[self.graph.ids[key]]["score"] = score

    def clear(self):
        if self.engine == "fastgraph":
            self.graph.clear()
        elif self.engine == "native":
            self.store.clear_scope(0)
        else:
            self.graph.clear()


def node_attrs(i, profile):
    if profile == "empty":
        return {}
    if profile == "rich":
        return {
            "group": i % 1000,
            "score": i % 10000,
            "name": f"node-{i}",
            "text": "abcdefghijklmnopqrstuvwxyz012345" * 3,
            "tags": ["graph", "native", str(i % 10), "bench"],
            "meta": {"active": i % 2 == 0, "region": i % 7},
        }
    return {"group": i % 1000, "score": i % 10000}


def edge_attrs(i, profile):
    if profile == "empty":
        return {}
    if profile == "rich":
        return {
            "weight": i % 10 + 1,
            "label": "relation-property-" * 4,
            "flags": [True, False],
            "meta": {"rank": i % 5},
        }
    return {"weight": i % 10 + 1}


def dataset(n, shape="ring", profile="sparse", degree=4):
    nodes = [(str(i), node_attrs(i, profile)) for i in range(n)]
    pairs = []
    if shape == "ring":
        offsets = (1, 7, 37, 181)[:degree]
        pairs = [(i, (i + offset) % n) for i in range(n) for offset in offsets]
    elif shape == "chain":
        pairs = [(i, i + 1) for i in range(n - 1)]
    elif shape == "star":
        pairs = [(0, i) for i in range(1, n)]
    elif shape == "disconnected":
        width = max(1, n // 10)
        for base in range(0, n, width):
            count = min(width, n - base)
            pairs.extend(
                (base + i, base + (i + offset) % count)
                for i in range(count)
                for offset in (1, 7, 37, 181)
            )
    elif shape == "hub":
        rng = random.Random(SEED)
        for i in range(n):
            targets = {(i + 1) % n}
            attempts = 0
            while len(targets) < 4:
                attempts += 1
                target = min(n - 1, int(rng.paretovariate(1.3)))
                if attempts > 30:
                    target = rng.randrange(n)
                targets.add(target)
            pairs.extend((i, target) for target in sorted(targets))
    else:
        raise ValueError(shape)
    pairs = list(dict.fromkeys(pairs))
    edges = [
        (str(src), str(dst), "r", edge_attrs(i, profile)) for i, (src, dst) in enumerate(pairs)
    ]
    expected_reachable = n if shape != "disconnected" else max(1, n // 10)
    return nodes, edges, expected_reachable


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def load_backend(job, meter):
    gc.collect()
    baseline = memory()
    started = time.perf_counter_ns()
    nodes, edges, reachable = dataset(
        job["nodes"], job.get("shape", "ring"), job.get("profile", "sparse")
    )
    generation_ms = (time.perf_counter_ns() - started) / 1e6
    backend = Backend(job["engine"])
    chunk = job.get("batch", 0)

    def insert(items, method):
        if not chunk:
            method(items)
        else:
            for start in range(0, len(items), chunk):
                method(items[start : start + chunk])

    meter.run("load_nodes", lambda items=nodes: insert(items, backend.add_nodes), units=len(nodes))
    meter.run("load_edges", lambda items=edges: insert(items, backend.add_edges), units=len(edges))
    expected_counts = len(nodes), len(edges)
    require(
        backend.counts() == expected_counts,
        f"Count mismatch: {backend.counts()} vs {expected_counts}",
    )
    del nodes, edges
    gc.collect()
    loaded_memory = memory()
    details = {
        "nodes": expected_counts[0],
        "edges": expected_counts[1],
        "expected_reachable": reachable,
        "input_generation_ms": generation_ms,
        "baseline_memory": baseline,
        "loaded_memory": loaded_memory,
        "retained_rss_delta_mib": loaded_memory["rss_mib"] - baseline["rss_mib"],
        "retained_private_delta_mib": loaded_memory["private_mib"] - baseline["private_mib"],
    }
    if backend.store is not None:
        details["native_estimate"] = backend.store.memory_usage()
    # Query/reference data is rebuilt only after measuring graph-only retained memory.
    nodes, edges, _ = dataset(job["nodes"], job.get("shape", "ring"), job.get("profile", "sparse"))
    keys = [edge[:3] for edge in edges]
    expected_weights = {edge[:3]: edge[3].get("weight") for edge in edges}
    del nodes, edges
    gc.collect()
    return backend, keys, expected_weights, details


def flat(job, meter):
    backend, keys, weights, details = load_backend(job, meter)
    n = details["nodes"]
    rng = random.Random(SEED)
    count = job.get("queries", 30000)
    hits = [keys[rng.randrange(len(keys))] for _ in range(count)]
    misses = [(str(rng.randrange(n)), str(rng.randrange(n)), "missing") for _ in range(count)]
    mixed = [hits[i] if i % 2 == 0 else misses[i] for i in range(count)]
    node_keys = [str(rng.randrange(n)) for _ in range(count)]

    def check_get(keys_to_get):
        matches = 0
        for key in keys_to_get:
            result = backend.get_edge(key)
            if result is not None:
                if "weight" in result:
                    require(result["weight"] == weights[key], "Wrong relationship property")
                matches += 1
        return matches

    meter.run(
        "edge_has_hit",
        lambda: sum(backend.has_edge(key) for key in hits),
        units=count,
        validate=lambda result: require(result == count, "Existence hit mismatch"),
        warmup=True,
    )
    meter.run(
        "edge_has_mixed",
        lambda: sum(backend.has_edge(key) for key in mixed),
        units=count,
        validate=lambda result: require(result == (count + 1) // 2, "Mixed hit mismatch"),
    )
    meter.run(
        "edge_get_hit",
        lambda: check_get(hits),
        units=count,
        validate=lambda result: require(result == count, "Lookup hit mismatch"),
        warmup=True,
    )
    if job["engine"] in ("networkx", "rustworkx", "igraph"):
        meter.run(
            "edge_get_detached",
            lambda: sum(copy.deepcopy(backend.get_edge(key)) is not None for key in hits),
            units=count,
            validate=lambda result: require(result == count, "Copied lookup mismatch"),
        )
    else:
        meter.metrics["edge_get_detached"] = dict(meter.metrics["edge_get_hit"])
        meter.metrics["edge_get_detached"]["alias_of"] = "edge_get_hit"
    meter.run(
        "node_get",
        lambda: sum(backend.get_node(key) is not None for key in node_keys),
        units=count,
        validate=lambda result: require(result == count, "Node lookup mismatch"),
    )
    neighbor_keys = node_keys[: min(1000, count)]
    expected_degrees = {key: backend.degree(key)[0] for key in set(neighbor_keys)}
    meter.run(
        "neighbors_ids",
        lambda: sum(len(backend.neighbors(key)) for key in neighbor_keys),
        units=len(neighbor_keys),
        validate=lambda value: require(
            value == sum(expected_degrees[key] for key in neighbor_keys), "Neighbor mismatch"
        ),
    )
    meter.run(
        "degree",
        lambda: sum(backend.degree(key)[0] for key in node_keys),
        units=count,
        validate=lambda value: require(value >= 0, "Invalid degree"),
    )
    meter.run(
        "counts",
        backend.counts,
        units=1,
        repeats=20,
        validate=lambda value: require(
            value == (details["nodes"], details["edges"]), "Counts changed"
        ),
    )
    meter.latency("edge_has_latency", backend.has_edge, mixed[: min(2000, count)])
    meter.latency("edge_get_latency", backend.get_edge, hits[: min(2000, count)])
    bfs_result = meter.run(
        "bfs",
        lambda: backend.bfs("0"),
        repeats=3 if n <= 100000 else 2,
        units=details["expected_reachable"],
        validate=lambda result: require(
            result[0] == details["expected_reachable"], "BFS reachability mismatch"
        ),
        warmup=True,
    )
    if job["engine"] == "fastgraph" and n <= 100000:
        meter.run(
            "bfs_discovery_edge_hydration",
            lambda: bfs_result[1].edges,
            units=max(bfs_result[1].edge_count, 1),
            validate=lambda values: require(
                len(values) == bfs_result[1].edge_count, "Tree edges mismatch"
            ),
        )
        meter.run(
            "neighbors_hydrated",
            lambda: backend.graph.neighbors_out("0"),
            units=max(backend.degree("0")[0], 1),
            validate=lambda values: require(
                len(values) == backend.degree("0")[0], "Hydrated neighbor mismatch"
            ),
        )
    targets = [str(n - 1)] if job.get("shape") in ("chain", "star") else [str(n // 2)]
    if job.get("shape") == "disconnected":
        targets = [str(n // 20)]
    path = meter.run(
        "shortest_path",
        lambda: backend.shortest("0", targets[0]),
        units=1,
        repeats=3 if n <= 100000 else 1,
        validate=lambda path: require(path is not None and len(path) >= 1, "Path missing"),
    )
    details["shortest_path_length"] = len(path)
    display_path = [str(value) for value in path]
    require(display_path[0] == "0" and display_path[-1] == targets[0], "Path endpoints mismatch")
    require(
        all((src, dst, "r") in weights for src, dst in zip(display_path, display_path[1:])),
        "Shortest path contains a nonedge",
    )
    if job["engine"] == "fastgraph" and n <= 100000:
        meter.run(
            "dfs",
            lambda: backend.graph.dfs("0"),
            units=details["expected_reachable"],
            validate=lambda result: require(
                result.node_count == details["expected_reachable"], "DFS mismatch"
            ),
        )
        if job.get("profile") != "empty":
            meter.run(
                "bfs_property_filter",
                lambda: backend.graph.bfs("0", filters={"score__gte": 0}),
                units=details["expected_reachable"],
                validate=lambda result: require(
                    result.node_count == details["expected_reachable"], "Filtered BFS mismatch"
                ),
            )
        if n <= 25000 and job.get("shape") == "ring":
            meter.run(
                "bfs_edge_callback",
                lambda: backend.graph.bfs("0", edge_filter=lambda _: True),
                units=details["expected_reachable"],
                validate=lambda result: require(
                    result.node_count == details["expected_reachable"], "Callback BFS mismatch"
                ),
            )
    details["final_memory"] = memory()
    return details


def query_case(job, meter):
    job = {**job, "shape": "ring", "profile": "sparse"}
    backend, _, _, details = load_backend(job, meter)
    n = job["nodes"]
    predicates = {
        "rare": ([("group", "eq", 107)], {"group": 107}, lambda attrs: attrs["group"] == 107),
        "miss": ([("group", "eq", 1001)], {"group": 1001}, lambda attrs: attrs["group"] == 1001),
        "range": (
            [("score", "gte", 9990)],
            {"score__gte": 9990},
            lambda attrs: attrs["score"] >= 9990,
        ),
        "broad": (
            [("score", "gte", 5000)],
            {"score__gte": 5000},
            lambda attrs: attrs["score"] >= 5000,
        ),
        "compound": (
            [("group", "eq", 107), ("score", "gte", 5000)],
            {"group": 107, "score__gte": 5000},
            lambda attrs: attrs["group"] == 107 and attrs["score"] >= 5000,
        ),
    }

    def query(name, limit=None):
        native, keywords, predicate = predicates[name]
        if backend.engine == "fastgraph":
            return backend.graph.find_nodes(limit=limit, **keywords)
        if backend.engine == "native":
            return backend.store.find_nodes(0, native, limit=limit)
        result = []
        for key, attrs in backend.graph.internal.nodes(data=True):
            if predicate(attrs):
                result.append((key, attrs))
                if limit is not None and len(result) >= limit:
                    break
        return result

    expected = {
        name: sum(predicate(node_attrs(i, "sparse")) for i in range(n))
        for name, (_, _, predicate) in predicates.items()
    }
    for name in predicates:
        repeats = 10 if name in ("rare", "miss", "compound") else 3
        meter.run(
            f"query_scan_{name}",
            lambda name=name: query(name),
            repeats=repeats,
            validate=lambda result, name=name: require(
                len(result) == expected[name], f"Query {name} mismatch"
            ),
            warmup=True,
        )
    meter.run(
        "query_scan_limit10",
        lambda: query("rare", 10),
        repeats=10,
        validate=lambda result: require(len(result) == min(10, expected["rare"]), "Limit mismatch"),
    )
    if backend.store is not None:
        for name in ("group", "score"):
            meter.run(f"index_build_{name}", lambda name=name: backend.store.create_index(0, name))
        for name in predicates:
            meter.run(
                f"query_indexed_{name}",
                lambda name=name: query(name),
                repeats=20 if name in ("rare", "miss", "compound") else 3,
                validate=lambda result, name=name: require(
                    len(result) == expected[name], "Indexed mismatch"
                ),
                warmup=True,
            )
        meter.run(
            "query_indexed_limit10",
            lambda: query("rare", 10),
            repeats=20,
            validate=lambda result: require(
                len(result) == min(10, expected["rare"]), "Indexed limit mismatch"
            ),
        )
        meter.latency(
            "query_indexed_rare_latency",
            lambda _: query("rare"),
            list(range(200)),
            validate=lambda result: require(len(result) == expected["rare"], "Hot query mismatch"),
        )
        details["indexed_memory"] = memory()
        details["indexed_native_estimate"] = backend.store.memory_usage()
    details["query_cardinalities"] = expected
    return details


def mutation_case(job, meter):
    backend, keys, _, details = load_backend(job, meter)
    n, original_edges = details["nodes"], details["edges"]
    size = min(1000, len(keys) // 4)
    selected = keys[:size]
    replacements = [(src, dst, rel, {"weight": 999}) for src, dst, rel in selected]
    meter.run("duplicate_upsert", lambda: backend.upsert_edges(replacements), units=size)
    require(backend.counts() == (n, original_edges), "Duplicate upsert added edges")
    require(
        all(backend.get_edge(key)["weight"] == 999 for key in selected), "Upsert properties wrong"
    )
    meter.run(
        "update_nodes",
        lambda: backend.update_nodes([(str(i), 42) for i in range(size)]),
        units=size,
    )
    require(
        all(backend.get_node(str(i))["score"] == 42 for i in range(size)), "Node updates missing"
    )
    meter.run(
        "delete_edges",
        lambda: backend.remove_edges(selected),
        units=size,
        validate=lambda removed: require(removed == size, "Edge deletion count mismatch"),
    )
    require(all(not backend.has_edge(key) for key in selected), "Ghost relationship after deletion")
    deleted = [str(i) for i in range(n - min(500, n // 10), n)]
    deleted_set = set(deleted)
    remaining = sum(
        src not in deleted_set and dst not in deleted_set for src, dst, _ in keys[size:]
    )
    meter.run("delete_nodes", lambda: backend.remove_nodes(deleted), units=len(deleted))
    require(backend.counts() == (n - len(deleted), remaining), "Incident edge cleanup mismatch")
    details["after_delete_memory"] = memory()
    meter.run("clear", backend.clear)
    require(backend.counts() == (0, 0), "Clear failed")
    gc.collect()
    details["after_clear_memory"] = memory()
    details["operation_sizes"] = {
        "upserts": size,
        "node_updates": size,
        "edge_deletes": size,
        "node_deletes": len(deleted),
    }
    return details


def transaction_case(job, meter):
    backend, _, _, details = load_backend({**job, "engine": "fastgraph"}, meter)
    graph = backend.graph

    def empty():
        with graph.transaction():
            pass

    def commit():
        with graph.transaction():
            for i in range(10):
                graph.update_node(str(i), score=123)

    def rollback():
        try:
            with graph.transaction():
                for i in range(10):
                    graph.update_node(str(i), score=321)
                raise RuntimeError("benchmark rollback")
        except RuntimeError:
            pass

    meter.run("transaction_empty", empty, repeats=3)
    meter.run("transaction_commit_10", commit, repeats=3, units=10)
    meter.run("transaction_rollback_10", rollback, repeats=3, units=10)
    require(
        all(graph.get_node(str(i))["score"] == 123 for i in range(10)), "Rollback did not restore"
    )
    return details


def view_case(job, meter):
    backend, _, _, details = load_backend({**job, "engine": "fastgraph"}, meter)
    graph = backend.graph
    count = sum(i % 1000 < 100 for i in range(job["nodes"]))
    view = meter.run(
        "view_create",
        lambda: graph.create_subgraph_view("selected", group__lt=100),
        validate=lambda view: require(view.node_count == count, "View selection mismatch"),
    )
    meter.run(
        "view_count",
        lambda: view.node_count,
        repeats=100,
        validate=lambda value: require(value == count, "View count changed"),
    )
    edges = meter.run("view_edges", lambda: view.edges)
    details["selected_nodes"] = count
    details["selected_edges"] = len(edges)
    result = meter.run("view_bfs", lambda: view.bfs("0"))
    details["view_reached"] = result.node_count
    require(all(node.attrs["group"] < 100 for node in result.nodes), "View traversal escaped")
    return details


def make_nested(engine, groups, teams, leaves):
    if engine == "fastgraph":
        from fastgraph import FastGraph

        graph = FastGraph("nested-benchmark")
        store = graph._state.store
    elif engine == "native":
        from fastgraph._native import NativeStore

        graph = store = NativeStore()
    else:
        import networkx as nx

        graph, store = nx.MultiDiGraph(), None
    node_map, paths, scoped, real_edges = {}, [], [], []
    root_path = ("world",)
    if engine == "fastgraph":
        root = graph.add_node("world")
        world = root.graph
    elif engine == "native":
        (root,) = store.add_nodes(0, [("world", {})])
        world = store.create_scope(root)
    else:
        graph.add_node(root_path)
        root = world = root_path
    node_map[root_path] = root if engine != "networkx" else root_path
    for group in range(groups):
        dept_path = ("world", f"d{group}")
        if engine == "fastgraph":
            owner = world.add_node(f"d{group}")
            department = owner.graph
        elif engine == "native":
            (owner,) = store.add_nodes(world, [(f"d{group}", {})])
            department = store.create_scope(owner)
        else:
            graph.add_node(dept_path)
            graph.add_edge(root_path, dept_path, key="__containment__")
            owner, department = dept_path, dept_path
        node_map[dept_path] = owner
        for team in range(teams):
            team_path = (*dept_path, f"t{team}")
            if engine == "fastgraph":
                team_node = department.add_node(f"t{team}")
                child = team_node.graph
                refs = child.add_nodes_batch(
                    [(f"n{i}", node_attrs(i, "sparse")) for i in range(leaves)]
                )
                child.add_edges_batch(
                    [
                        (f"n{i}", f"n{(i + offset) % leaves}", "r", {"weight": 1})
                        for i in range(leaves)
                        for offset in (1, 7, 13)
                        if offset % leaves
                    ]
                )
            elif engine == "native":
                (team_node,) = store.add_nodes(department, [(f"t{team}", {})])
                child = store.create_scope(team_node)
                refs = store.add_nodes(
                    child, [(f"n{i}", node_attrs(i, "sparse")) for i in range(leaves)]
                )
                store.add_edges(
                    [
                        (refs[i], refs[(i + offset) % leaves], "r", {"weight": 1})
                        for i in range(leaves)
                        for offset in (1, 7, 13)
                        if offset % leaves
                    ]
                )
            else:
                graph.add_node(team_path)
                graph.add_edge(dept_path, team_path, key="__containment__")
                refs = [(*team_path, f"n{i}") for i in range(leaves)]
                graph.add_nodes_from(
                    [(path, node_attrs(i, "sparse")) for i, path in enumerate(refs)]
                )
                graph.add_edges_from([(team_path, path, "__containment__", {}) for path in refs])
                graph.add_edges_from(
                    [
                        (refs[i], refs[(i + offset) % leaves], "r", {"weight": 1})
                        for i in range(leaves)
                        for offset in (1, 7, 13)
                        if offset % leaves
                    ]
                )
                child, team_node = team_path, team_path
            node_map[team_path] = team_node
            scoped.append(child)
            for i, ref in enumerate(refs):
                path = (*team_path, f"n{i}")
                node_map[path] = ref
                paths.append(path)
            real_edges.extend(
                ((*team_path, f"n{i}"), (*team_path, f"n{(i + offset) % leaves}"), "r")
                for i in range(leaves)
                for offset in (1, 7, 13)
                if offset % leaves
            )
    # Sparse explicit cross-scope relationships; no implicit child-to-parent exits.
    cross = [
        (paths[i], paths[(i + leaves) % len(paths)], "cross") for i in range(0, len(paths), leaves)
    ]
    if engine == "fastgraph":
        graph.add_edges_batch([(node_map[src], node_map[dst], rel) for src, dst, rel in cross])
    elif engine == "native":
        store.add_edges([(node_map[src], node_map[dst], rel, {}) for src, dst, rel in cross])
    else:
        graph.add_edges_from([(src, dst, rel, {}) for src, dst, rel in cross])
    real_edges.extend(cross)
    return graph, store, root, node_map, paths, scoped, real_edges


def nested_case(job, meter):
    gc.collect()
    baseline = memory()
    result = meter.run(
        "nested_build",
        lambda: make_nested(job["engine"], job["groups"], job["teams"], job["leaves"]),
    )
    graph, store, root, node_map, paths, scopes, edges = result
    expected_nodes = 1 + job["groups"] + job["groups"] * job["teams"] + len(paths)
    require(len(node_map) == expected_nodes, "Nested identities collided")
    loaded = memory()

    def bfs(nested, depth=None):
        if job["engine"] == "fastgraph":
            result = graph.bfs(root, nested=nested, max_depth=depth)
            return result.node_count, result
        if job["engine"] == "native":
            result = store.bfs(root, nested=nested, max_depth=depth)
            return len(result[0]), result
        import networkx as nx

        if not nested:
            queue = [root]
            distance = {root: 0}
            for source in queue:
                if depth is not None and distance[source] >= depth:
                    continue
                for _, target, relation in graph.out_edges(source, keys=True):
                    if relation == "__containment__" or target in distance:
                        continue
                    distance[target] = distance[source] + 1
                    queue.append(target)
            return len(queue), distance
        result = dict(nx.single_source_shortest_path_length(graph, ("world",), cutoff=depth))
        return len(result), result

    def cross_scope_bfs():
        start_path = paths[0]
        if job["engine"] == "fastgraph":
            result = graph.bfs(node_map[start_path], nested=False)
            return result.node_count, result
        if job["engine"] == "native":
            result = store.bfs(node_map[start_path], nested=False)
            return len(result[0]), result
        import networkx as nx

        result = dict(nx.single_source_shortest_path_length(graph, start_path))
        return len(result), result

    meter.run(
        "nested_bfs_all",
        lambda: bfs(True),
        repeats=3,
        units=expected_nodes,
        validate=lambda result: require(result[0] == expected_nodes, "Nested BFS mismatch"),
        warmup=True,
    )
    meter.run(
        "nested_bfs_parent_only",
        lambda: bfs(False),
        repeats=20,
        validate=lambda result: require(result[0] == 1, "Unexpected implicit descent"),
    )
    depth2_count = 1 + job["groups"] * (1 + job["teams"])
    meter.run(
        "nested_bfs_depth2",
        lambda: bfs(True, 2),
        repeats=5,
        units=depth2_count,
        validate=lambda result: require(result[0] == depth2_count, "Nested depth mismatch"),
    )
    meter.run(
        "nested_cross_scope_bfs",
        cross_scope_bfs,
        repeats=3,
        units=len(paths),
        validate=lambda result: require(
            result[0] == len(paths), "Explicit cross-scope traversal mismatch"
        ),
    )
    rng = random.Random(SEED)
    selected = [paths[rng.randrange(len(paths))] for _ in range(job.get("queries", 10000))]

    def lookup_path(path):
        if job["engine"] == "fastgraph":
            return graph.resolve(path).attrs
        if job["engine"] == "native":
            scope = 0
            for offset, part in enumerate(path):
                node = store.node_id(scope, part)
                if offset + 1 < len(path):
                    scope = store.node_info(node)[2]
            return store.get_node(node)
        return graph.nodes[path]

    def lookup_handle(path):
        if job["engine"] == "fastgraph":
            return graph.get_node(node_map[path])
        if job["engine"] == "native":
            return store.get_node(node_map[path])
        return graph.nodes[path]

    meter.run(
        "nested_lookup_path",
        lambda: sum(lookup_path(path)["score"] >= 0 for path in selected),
        units=len(selected),
        validate=lambda count: require(count == len(selected), "Qualified lookup mismatch"),
    )
    meter.run(
        "nested_lookup_handle",
        lambda: sum(lookup_handle(path)["score"] >= 0 for path in selected),
        units=len(selected),
        validate=lambda count: require(count == len(selected), "Handle lookup mismatch"),
    )
    meter.latency("nested_path_latency", lookup_path, selected[:500])
    if store is not None:
        if job["engine"] == "fastgraph":

            def query():
                return graph.find_nodes(recursive=True, score__gte=job["leaves"] // 2)
        else:

            def query():
                return store.find_nodes(0, [("score", "gte", job["leaves"] // 2)], recursive=True)

        expected = job["groups"] * job["teams"] * (job["leaves"] - job["leaves"] // 2)
        meter.run(
            "nested_recursive_query",
            query,
            repeats=3,
            validate=lambda values: require(len(values) == expected, "Nested query mismatch"),
        )
        meter.run(
            "nested_snapshot",
            lambda: store.snapshot(),
            validate=lambda value: require(len(value) > 0, "Empty snapshot"),
        )
    return {
        "nodes": expected_nodes,
        "stored_edges": len(edges),
        "leaf_nodes": len(paths),
        "child_scopes": 1 + job["groups"] + job["groups"] * job["teams"],
        "baseline_memory": baseline,
        "loaded_memory": loaded,
        "retained_rss_delta_mib": loaded["rss_mib"] - baseline["rss_mib"],
        "networkx_explicit_containment_edges": expected_nodes - 1
        if job["engine"] == "networkx"
        else 0,
    }


def depth_case(job, meter):
    from fastgraph import FastGraph
    from fastgraph._native import NativeStore

    depth = job["depth"]
    if job["engine"] == "fastgraph":
        graph, scope = FastGraph(), None
        scope = graph
        for _ in range(depth):
            node = scope.add_node("n")
            scope = node.graph
        store = graph._state.store
        path = ("n",) * depth

        def lookup():
            return graph.resolve(path).attrs

        def fast_lookup():
            return node.attrs

        def reopen():
            return node.graph
    else:
        graph = store = NativeStore()
        scope = 0
        for _ in range(depth):
            (node,) = store.add_nodes(scope, [("n", {})])
            scope = store.create_scope(node)

        def lookup():
            current = 0
            for position in range(depth):
                selected = store.node_id(current, "n")
                if position + 1 < depth:
                    current = store.node_info(selected)[2]
            return store.get_node(selected)

        def fast_lookup():
            return store.get_node(node)

        def reopen():
            return store.create_scope(node)

    queries = job.get("queries", 1000)
    meter.run("depth_path_lookup", lambda: [lookup() for _ in range(queries)], units=queries)
    meter.run("depth_handle_lookup", lambda: [fast_lookup() for _ in range(queries)], units=queries)
    meter.run("depth_reopen_child", lambda: [reopen() for _ in range(queries)], units=queries)
    require(store.stats(0, recursive=True)["nodes"] == depth, "Reopen created nodes")
    return {"nodes": depth, "child_scopes": depth, "depth": depth}


def persistence_case(job, meter):
    from fastgraph.core.persistence import PersistenceManager
    from fastgraph._native import NativeStore

    backend, _, _, details = load_backend({**job, "engine": "fastgraph"}, meter)
    graph = backend.graph
    graph.build_node_index("group")
    encoded = meter.run("snapshot_native", lambda: graph._state.store.snapshot())
    envelope = meter.run("snapshot_python_envelope", graph.snapshot)
    details["native_snapshot_bytes"] = len(encoded)
    require(len(envelope["store"]["nodes"]) == details["nodes"], "Snapshot lost nodes")
    del encoded, envelope
    gc.collect()
    with tempfile.TemporaryDirectory(prefix="fg-persist-", dir=job["scratch"]) as temp:
        path = Path(temp) / ("graph." + job["format"] + (".gz" if job["compress"] else ""))
        meter.run(
            "save",
            lambda: graph.save(
                path, format=job["format"], compress=job["compress"], durable=job["durable"]
            ),
        )
        details["file_bytes"] = path.stat().st_size
        raw = meter.run(
            "load_decode_envelope",
            lambda: PersistenceManager().load(path, max_bytes=512 * 1024 * 1024),
        )
        require(len(raw["store"]["edges"]) == details["edges"], "Decoded snapshot lost edges")
        packed = json.dumps(raw["store"], allow_nan=False).encode()
        meter.run(
            "load_reconstruct_native",
            lambda data=packed: NativeStore.from_snapshot(data),
            validate=lambda store: require(
                store.stats(0)["edges"] == details["edges"], "Native reconstruction mismatch"
            ),
        )
        del raw, packed
        gc.collect()
        restored = meter.run(
            "load_full_warm", lambda: graph.from_file(path, max_bytes=512 * 1024 * 1024)
        )
        require(
            (restored.node_count, restored.edge_count) == (details["nodes"], details["edges"]),
            "Restore counts mismatch",
        )
        require(restored.get_node("107")["group"] == 107, "Restored property mismatch")
        restored.update_node("107", group=9999)
        require(restored.find_nodes(group=9999)[0][0] == "107", "Restored index failed maintenance")
        restored.close()
    details["cache_policy"] = "warm filesystem cache; no OS cache flush or crash injection"
    return details


def concurrency_case(job, meter):
    backend, keys, _, details = load_backend(job, meter)
    total = job.get("queries", 20000)
    workloads = job["workload"]

    def run(workers):
        barrier = threading.Barrier(workers + 1)
        if workloads == "point":
            per_worker = max(1, total // workers)
        else:
            per_worker = 2

        def worker(index):
            barrier.wait()
            if workloads == "point":
                return sum(
                    backend.has_edge(keys[(i * 37 + index) % len(keys)]) for i in range(per_worker)
                )
            return sum(backend.bfs("0")[0] for _ in range(per_worker))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(worker, i) for i in range(workers)]
            barrier.wait()
            counts = [future.result() for future in futures]
        return sum(counts)

    for workers in (1, 2, 4, 8):
        units = max(1, total // workers) * workers if workloads == "point" else workers * 2
        expected = units if workloads == "point" else units * details["expected_reachable"]
        meter.run(
            f"threads_{workers}",
            lambda workers=workers: run(workers),
            units=units,
            validate=lambda value, expected=expected: require(
                value == expected, "Concurrent read mismatch"
            ),
        )
    details["thread_workload"] = workloads
    details["thread_creation_included"] = True
    return details


def lifecycle_memory_case(job, meter):
    """Keep graph-only baselines separate from reference/query-result allocations."""
    gc.collect()
    baseline = memory()
    backend = Backend(job["engine"])
    nodes, edges, _ = dataset(job["nodes"], "ring", job.get("profile", "sparse"))
    expected = len(nodes), len(edges)
    backend.add_nodes(nodes)
    backend.add_edges(edges)
    del nodes, edges
    gc.collect()
    loaded = memory()
    require(backend.counts() == expected, "Memory case count mismatch")
    snapshots = {"baseline": baseline, "loaded": loaded}
    if backend.store is not None:
        meter.run("isolated_index_group", lambda: backend.store.create_index(0, "group"))
        meter.run("isolated_index_score", lambda: backend.store.create_index(0, "score"))
        gc.collect()
        snapshots["indexed"] = memory()
        estimate = backend.store.memory_usage()
    else:
        estimate = None
    deleted = [str(i) for i in range(job["nodes"] // 2)]
    meter.run(
        "isolated_delete_half", lambda ids=deleted: backend.remove_nodes(ids), units=len(deleted)
    )
    del deleted
    gc.collect()
    snapshots["half_deleted"] = memory()
    meter.run("isolated_clear", backend.clear)
    gc.collect()
    snapshots["cleared"] = memory()
    if backend.engine == "fastgraph":
        backend.graph.close()
    backend = None
    gc.collect()
    snapshots["closed_or_released"] = memory()
    return {
        "nodes": expected[0],
        "edges": expected[1],
        "snapshots": snapshots,
        "index_estimate": estimate,
        "index_added_rss_mib": snapshots.get("indexed", loaded)["rss_mib"] - loaded["rss_mib"],
        "index_added_private_mib": snapshots.get("indexed", loaded)["private_mib"]
        - loaded["private_mib"],
        "clear_released_rss_mib": snapshots["half_deleted"]["rss_mib"]
        - snapshots["cleared"]["rss_mib"],
        "release_released_rss_mib": snapshots["cleared"]["rss_mib"]
        - snapshots["closed_or_released"]["rss_mib"],
    }


def bfs_equivalent_case(job, meter):
    """Construct four predecessor arrays in every library, not a second graph."""
    backend, _, _, details = load_backend(job, meter)
    n = details["nodes"]

    def search():
        if backend.engine == "native":
            return backend.store.bfs(backend.mapping["0"])
        if backend.engine == "fastgraph":
            result = backend.graph.bfs("0")
            nodes = list(result.nodes)
            # Expose the same information while retaining facade identity-handle cost.
            parents = [result._predecessors[node._id] for node in nodes]
            depths = [result._depths[node._id] for node in nodes]
            edges = [None] * len(nodes)
            return nodes, parents, depths, edges
        if backend.engine == "igraph":
            graph = backend.graph.internal
            nodes, _, predecessor = graph.bfs(backend.graph.ids["0"], mode="out")
            distance = {}
            parents, depths = [], []
            for node in nodes:
                parent = predecessor[node]
                parents.append(None if parent < 0 else parent)
                depth = 0 if parent < 0 else distance[parent] + 1
                distance[node] = depth
                depths.append(depth)
            return nodes, parents, depths, [None] * len(nodes)
        if backend.engine == "rustworkx":
            from collections import deque

            graph = backend.graph.internal
            start = backend.graph.ids["0"]
            queue = deque([start])
            distance = {start: 0}
            nodes, parents, depths = [start], [None], [0]
            while queue:
                source = queue.popleft()
                for target in graph.successor_indices(source):
                    if target in distance:
                        continue
                    distance[target] = distance[source] + 1
                    nodes.append(target)
                    parents.append(source)
                    depths.append(distance[target])
                    queue.append(target)
            return nodes, parents, depths, [None] * len(nodes)
        import networkx as nx

        nodes, parents, depths = ["0"], [None], [0]
        distance = {"0": 0}
        for source, children in nx.bfs_successors(backend.graph.internal, "0"):
            depth = distance[source] + 1
            for target in children:
                nodes.append(target)
                parents.append(source)
                depths.append(depth)
                distance[target] = depth
        return nodes, parents, depths, [None] * len(nodes)

    value = meter.run(
        "bfs_predecessor_arrays",
        search,
        repeats=3,
        units=n,
        validate=lambda value: require(
            all(len(array) == n for array in value), "Predecessor shape/reach mismatch"
        ),
        warmup=True,
    )
    details["result_arrays"] = len(value)
    details["comparator_edges_placeholder"] = job["engine"] not in ("native", "fastgraph")
    details["rustworkx_algorithm"] = (
        "Python BFS using native successor_indices" if job["engine"] == "rustworkx" else None
    )
    return details


WORKERS = {
    "flat": flat,
    "query": query_case,
    "mutation": mutation_case,
    "transaction": transaction_case,
    "view": view_case,
    "nested": nested_case,
    "depth": depth_case,
    "persistence": persistence_case,
    "concurrency": concurrency_case,
    "lifecycle_memory": lifecycle_memory_case,
    "bfs_equivalent": bfs_equivalent_case,
}


def worker_main(job):
    import psutil

    start_memory = memory()
    import_start = time.perf_counter_ns()
    # Import before measured graph baseline; imports are per-engine and recorded separately.
    if job["engine"] in ("fastgraph", "native"):
        import fastgraph
        from fastgraph import _native

        import_path = str(Path(fastgraph.__file__).resolve())
        require("site-packages" in import_path, f"Benchmark imported checkout: {import_path}")
        module_path = _native.__file__
    else:
        module = __import__("networkx" if job["engine"] == "networkx" else job["engine"])
        import_path = module.__file__
        module_path = None
    import_ms = (time.perf_counter_ns() - import_start) / 1e6
    meter = Meter()
    before = psutil.virtual_memory()
    details = WORKERS[job["kind"]](job, meter)
    return {
        "job": job,
        "status": "ok",
        "pid": os.getpid(),
        "started_utc": job.get("started_utc"),
        "import_ms": import_ms,
        "module_path": import_path,
        "native_module": module_path,
        "startup_memory": start_memory,
        "metrics": meter.metrics,
        "details": details,
        "final_memory": memory(),
        "available_ram_before_gib": before.available / 2**30,
        "available_ram_after_gib": psutil.virtual_memory().available / 2**30,
    }


def plan(smoke=False):
    jobs = []

    def add(kind, engines, runs=3, **options):
        for repeat in range(runs):
            order = tuple(engines)
            shift = repeat % len(order)
            for engine in order[shift:] + order[:shift]:
                jobs.append(
                    {
                        "kind": kind,
                        "engine": engine,
                        "repeat": repeat,
                        "case": kind
                        + ":"
                        + ":".join(f"{key}={value}" for key, value in options.items()),
                        **options,
                    }
                )

    if smoke:
        add("flat", ENGINES, runs=1, nodes=200, queries=100, shape="ring", profile="sparse")
        add("query", ("fastgraph", "native", "networkx"), runs=1, nodes=200)
        add("mutation", ENGINES, runs=1, nodes=200)
        add("transaction", ("fastgraph",), runs=1, nodes=200)
        add("view", ("fastgraph",), runs=1, nodes=200)
        add(
            "nested",
            ("fastgraph", "native", "networkx"),
            runs=1,
            groups=2,
            teams=2,
            leaves=16,
            queries=100,
        )
        add("depth", ("fastgraph", "native"), runs=1, depth=4, queries=100)
        add(
            "persistence",
            ("fastgraph",),
            runs=1,
            nodes=200,
            format="msgpack",
            compress=True,
            durable=True,
        )
        add(
            "concurrency",
            ("fastgraph", "native", "networkx"),
            runs=1,
            nodes=200,
            queries=100,
            workload="point",
        )
        return jobs
    for n, repeats in ((25000, 5), (100000, 5), (250000, 3)):
        add("flat", ENGINES, runs=repeats, nodes=n, queries=30000, shape="ring", profile="sparse")
    for shape, n in (("chain", 20000), ("star", 25000), ("disconnected", 25000), ("hub", 25000)):
        add("flat", ENGINES, nodes=n, queries=10000, shape=shape, profile="sparse")
    for profile in ("empty", "rich"):
        add("flat", ENGINES, nodes=25000, queries=10000, shape="ring", profile=profile)
    for chunk in (1, 256, 0):
        add("flat", ENGINES, nodes=2000, queries=1000, shape="ring", profile="sparse", batch=chunk)
    for n in (25000, 100000):
        add("query", ("fastgraph", "native", "networkx"), nodes=n)
        add("transaction", ("fastgraph",), nodes=n)
        add("view", ("fastgraph",), nodes=n)
    add("mutation", ENGINES, nodes=25000)
    for groups, leaves in ((32, 64), (128, 128)):
        add(
            "nested",
            ("fastgraph", "native", "networkx"),
            groups=groups,
            teams=4,
            leaves=leaves,
            queries=10000,
        )
    for depth in (4, 16, 64, 256):
        add("depth", ("fastgraph", "native"), depth=depth, queries=1000)
    for format in ("json", "msgpack"):
        for compress in (False, True):
            for durable in (False, True):
                add(
                    "persistence",
                    ("fastgraph",),
                    nodes=25000,
                    format=format,
                    compress=compress,
                    durable=durable,
                )
            add(
                "persistence",
                ("fastgraph",),
                runs=2,
                nodes=100000,
                format=format,
                compress=compress,
                durable=True,
            )
    for workload in ("point", "bfs"):
        add(
            "concurrency",
            ("fastgraph", "native", "networkx"),
            nodes=25000,
            queries=20000,
            workload=workload,
        )
    return jobs


def environment():
    import psutil

    names = ("fastgx", "psutil", "networkx", "rustworkx", "igraph", "msgpack", "numpy", "maturin")
    packages = {name: importlib.metadata.version(name) for name in names}
    root = Path(__file__).resolve().parents[1]
    paths = (
        "native/src/lib.rs",
        "Cargo.toml",
        "Cargo.lock",
        "fastgraph/core/graph.py",
        "fastgraph/core/traversal.py",
        "fastgraph/core/persistence.py",
        "benchmarks/in_depth.py",
        "benchmarks/_peers.py",
    )
    hashes = {part: hashlib.sha256((root / part).read_bytes()).hexdigest() for part in paths}
    return {
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(),
        "ram_total_gib": psutil.virtual_memory().total / 2**30,
        "ram_available_gib": psutil.virtual_memory().available / 2**30,
        "packages": packages,
        "seed": SEED,
        "source_sha256": hashes,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "git_status": subprocess.check_output(["git", "status", "--short"], cwd=root, text=True),
        "timing": "perf_counter_ns wall; process_time_ns CPU; GC enabled; input generation excluded",
        "memory": "psutil RSS/private after GC; OS allocator retention included; process peak cumulative",
        "isolation": "one fresh subprocess at a time, PYTHONHASHSEED=0, no source fastgraph imports",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", help="JSON job, used by controller")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--only", help="Comma-separated workload kinds")
    parser.add_argument(
        "--supplement", action="store_true", help="Memory lifecycle and equivalent BFS checks"
    )
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--engines", help="Comma-separated engine subset")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--min-free-gib", type=float, default=1.5)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(worker_main(json.loads(args.worker)), allow_nan=False))
        except BaseException as exc:
            print(
                json.dumps(
                    {
                        "job": json.loads(args.worker),
                        "status": "error",
                        "error": repr(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
            )
            sys.exit(1)
        return
    if args.output is None or args.scratch is None:
        parser.error("--output and --scratch are required for reproducible raw results")
    args.output = args.output.resolve()
    args.scratch = args.scratch.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    args.scratch.mkdir(parents=True, exist_ok=True)
    jobs = plan(args.smoke)
    if args.supplement:
        jobs = []
        for repeat in range(3):
            for n in (25000, 100000):
                for engine in ENGINES:
                    for kind in ("lifecycle_memory", "bfs_equivalent"):
                        jobs.append(
                            {
                                "kind": kind,
                                "engine": engine,
                                "repeat": repeat,
                                "case": f"{kind}:nodes={n}",
                                "nodes": n,
                            }
                        )
    if args.only:
        kinds = set(args.only.split(","))
        jobs = [job for job in jobs if job["kind"] in kinds]
    if args.engines:
        engines = set(args.engines.split(","))
        jobs = [job for job in jobs if job["engine"] in engines]
    if args.max_jobs:
        jobs = jobs[: args.max_jobs]
    manifest = environment()
    manifest["plan"] = jobs
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    results = []
    import psutil

    env = os.environ.copy()
    env.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "FASTGRAPH_DATA_DIR": str(args.scratch),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
    env.pop("PYTHONPATH", None)
    with (args.output / "samples.jsonl").open("w", encoding="utf-8") as raw:
        for index, job in enumerate(jobs):
            job = {
                **job,
                "scratch": str(args.scratch),
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if psutil.virtual_memory().available / 2**30 < args.min_free_gib:
                result = {"job": job, "status": "skipped", "reason": "host RAM safety threshold"}
            else:
                started = time.perf_counter()
                try:
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-B",
                            str(Path(__file__).resolve()),
                            "--worker",
                            json.dumps(job),
                        ],
                        cwd=args.scratch,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=args.timeout,
                    )
                    output = completed.stdout.strip().splitlines()
                    result = (
                        json.loads(output[-1])
                        if output
                        else {"job": job, "status": "error", "error": "No worker output"}
                    )
                    result["returncode"] = completed.returncode
                    if completed.stderr:
                        result["stderr"] = completed.stderr
                except subprocess.TimeoutExpired:
                    result = {"job": job, "status": "timeout", "timeout_s": args.timeout}
                result["worker_wall_s"] = time.perf_counter() - started
            results.append(result)
            raw.write(json.dumps(result, allow_nan=False) + "\n")
            raw.flush()
            print(
                f"[{index + 1}/{len(jobs)}] {job['engine']} {job['case']} repeat={job['repeat']} "
                f"{result['status']} {result.get('worker_wall_s', 0):.2f}s",
                flush=True,
            )
    (args.output / "results.json").write_text(
        json.dumps({"environment": manifest, "samples": results}, indent=2), encoding="utf-8"
    )
    failed = sum(result["status"] == "error" for result in results)
    print(
        f"Finished {len(results)} fresh processes; errors={failed}; raw={args.output}", flush=True
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

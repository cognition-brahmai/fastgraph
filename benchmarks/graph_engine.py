"""Reproducible embedded-engine smoke measurements; not a Neo4j comparison."""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import subprocess
import sys
import time


def run_once(engine: str, nodes: int, edges_per_node: int, queries: int) -> dict:
    import psutil
    from fastgraph import FastGraph
    import networkx as nx

    process = psutil.Process()
    gc.collect()
    baseline = process.memory_info().rss
    graph = FastGraph() if engine == "fastgraph" else nx.MultiDiGraph()
    identifiers = [str(i) for i in range(nodes)]
    node_input = [(identifier, {"group": i % 10}) for i, identifier in enumerate(identifiers)]
    started = time.perf_counter_ns()
    if engine == "fastgraph":
        graph.add_nodes_batch(node_input)
    else:
        graph.add_nodes_from(node_input)
    nodes_ns = time.perf_counter_ns() - started
    del node_input
    edge_input = [
        (identifier, identifiers[(i + offset + 1) % nodes], "r", {"weight": 1})
        for i, identifier in enumerate(identifiers)
        for offset in range(edges_per_node)
    ]
    started = time.perf_counter_ns()
    if engine == "fastgraph":
        graph.add_edges_batch(edge_input)
        actual_edges = graph.edge_count
    else:
        graph.add_edges_from(edge_input)
        actual_edges = graph.number_of_edges()
    edges_ns = time.perf_counter_ns() - started
    assert actual_edges == nodes * edges_per_node
    del edge_input
    gc.collect()
    graph_rss = process.memory_info().rss - baseline
    keys = [(identifiers[i % nodes], identifiers[(i + 1) % nodes], "r") for i in range(queries)]
    lookup = graph.get_edge if engine == "fastgraph" else graph.get_edge_data
    started = time.perf_counter_ns()
    hits = sum(lookup(*key) is not None for key in keys)
    lookup_ns = time.perf_counter_ns() - started
    assert hits == queries
    started = time.perf_counter_ns()
    hits = sum(graph.has_edge(*key) for key in keys)
    existence_ns = time.perf_counter_ns() - started
    assert hits == queries
    started = time.perf_counter_ns()
    if engine == "fastgraph":
        reached = graph.bfs("0").node_count
    else:
        reached = len(list(nx.bfs_tree(graph, "0")))
    bfs_ns = time.perf_counter_ns() - started
    assert reached == nodes
    return {
        "engine": engine,
        "nodes": nodes,
        "edges": actual_edges,
        "nodes_load_ms": nodes_ns / 1e6,
        "edges_load_ms": edges_ns / 1e6,
        "point_queries_ms": lookup_ns / 1e6,
        "existence_queries_ms": existence_ns / 1e6,
        "bfs_ms": bfs_ns / 1e6,
        "rss_delta_mib": graph_rss / (1024 * 1024),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=25000)
    parser.add_argument("--edges-per-node", type=int, default=4)
    parser.add_argument("--queries", type=int, default=100000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--worker", choices=["fastgraph", "networkx"])
    args = parser.parse_args()
    if not 0 < args.edges_per_node <= args.nodes or args.queries < 1 or args.runs < 1:
        parser.error("Require 0 < edges-per-node <= nodes and positive queries/runs")
    if args.worker:
        print(json.dumps(run_once(args.worker, args.nodes, args.edges_per_node, args.queries)))
        return
    samples = []
    for engine in ("fastgraph", "networkx"):
        for _ in range(args.runs):
            output = subprocess.check_output(
                [
                    sys.executable,
                    "-B",
                    __file__,
                    "--worker",
                    engine,
                    "--nodes",
                    str(args.nodes),
                    "--edges-per-node",
                    str(args.edges_per_node),
                    "--queries",
                    str(args.queries),
                ],
                text=True,
            )
            samples.append(json.loads(output))
    metrics = (
        "nodes_load_ms",
        "edges_load_ms",
        "point_queries_ms",
        "existence_queries_ms",
        "bfs_ms",
        "rss_delta_mib",
    )
    medians = {
        engine: {
            metric: statistics.median(
                sample[metric] for sample in samples if sample["engine"] == engine
            )
            for metric in metrics
        }
        for engine in ("fastgraph", "networkx")
    }
    print(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": sys.version,
                "workload": vars(args),
                "median": medians,
                "samples": samples,
                "caveat": "Embedded memory-only APIs; point result materialization differs; "
                "no durable-write or Neo4j speed claim.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

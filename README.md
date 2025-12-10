# FastGraph

### *The graph database you build when every other graph database pisses you off.*

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI Version](https://img.shields.io/badge/pypi-fastgx-orange.svg)](https://pypi.org/project/fastgx/)

<p align="center">
  <img src="https://raw.githubusercontent.com/cognition-brahmai/fastgraph/refs/heads/main/4f0acacd709795a384cf33419ef44346.jpg" width="700"/>
</p>

<br>

FastGraph is the **no-BS, in-memory, lightning-fast graph engine** built for developers who are done tolerating slow, bloated, overengineered graph databases.

This bad boy was born out of pure founder rage and engineered with a single, loud, unapologetic goal:

> **Make graph operations insanely fast and stupidly easy.**

Built by **BRAHMAI**, powered by caffeine, spite, and questionable sleep cycles.

---

# Why FastGraph Exists

Because Neo4j said:

> “Here’s one free database. Pay for the second, peasant.”

Because TigerGraph said:

> “Install our entire planet first.”

And because NetworkX said:

> “Bro I’m a toy, please stop putting me in production.”

So we said:

> **“Nah dude… f**k that. We’ll build our own.”**

And we did.

FastGraph is:

* **In-memory**
* **Blazing fast**
* **Thread-safe**
* **Zero setup**
* **Python-first**
* **Actually fun to use**

You know… the way a modern graph DB *should* feel.

---

# Headline Features (aka: Why This Slaps)

### **O(1) Edge Lookups**

If you know what you want, FastGraph gives it to you instantly.
No traversal. No dancing. No Cypher yoga.

### **Smart API v2.0**

Resource management, path resolution, auto-save, auto-load…
Basically the “don’t make me think” edition.

### **Zero-Copy Subgraph Views**

Slice your graph into meaningful pieces without duplicating a single byte.

### **Smart Persistence**

Files? Formats? Paths?
FastGraph handles it like your personal assistant.

### **Thread Safety**

Hit it with multiple threads. It doesn’t flinch.

### **Auto Indexing**

Runs fast by default. Runs *stupid* fast when it learns your query patterns.

### **Batch Ops & Optimized Algorithms**

Because if you’re loading millions of nodes one-by-one, you hate yourself.

---

# Quick Start

### *The “I got 10 seconds” version*

```python
from fastgraph import FastGraph

with FastGraph("my_graph") as graph:
    graph.add_node("alice", name="Alice", type="Person")
    graph.add_node("bob", name="Bob", type="Person")
    graph.add_edge("alice", "bob", "friends", since=2022)
    # Auto-save on exit. No tears. No drama.
```

---

# Traditional API (still sexy)

```python
from fastgraph import FastGraph

graph = FastGraph("my_graph")

graph.add_node("alice", name="Alice", age=30)
graph.add_node("bob", name="Bob", age=25)
graph.add_edge("alice", "bob", "friends")

print(graph.find_nodes(age__gte=25))
print(graph.neighbors_out("alice", rel="friends"))

graph.save("my_graph.msgpack")
```

---

# What’s New in v2.0 (TLDR: Everything Got Better)

* Zero config mode
* Auto file discovery
* Automatic format detection
* Factory constructors
* Streaming format conversion
* Context-manager resource safety
* Backup & restore
* Enhanced error handling
* Smarter defaults everywhere

Basically v2.0 is the "we cleaned up your mess for you" release.

---

# Smart Persistence That Just Works

```python
graph = FastGraph("social_graph")

if graph.exists():
    graph.load()  # Finds the file like magic
else:
    graph.save()  # Writes to the right place like it knew all along
```

Format conversion?

```python
graph.translate("data.json", "data.msgpack")
```

Straight-up wizardry.

---

# Factory Constructors (AKA: Less Code, More Power)

```python
graph = FastGraph.from_file("existing.msgpack")
graph = FastGraph.load_graph("production_graph")
graph = FastGraph.with_config({"enhanced_api": True}, "test_graph")
```

---

# Subgraph Views (Zero Copy)

```python
people = graph.create_subgraph_view(
    "people",
    lambda id, attrs: attrs.get("type") == "Person"
)

print(people.node_count)
```

No copying. No overhead. No patience required.

---

# Traversal Ops

```python
path = graph.traversal_ops.shortest_path("alice", "bob")
bfs = graph.traversal_ops.bfs("alice", max_depth=3)

for p in graph.traversal_ops.find_paths("alice", "bob"):
    print(p)
```

Your graph. Your rules.

---

# Performance Monitoring (for the nerds)

```python
from fastgraph.utils.performance import performance_monitor

@performance_monitor("query")
def run():
    return graph.find_nodes(type="Person")

print(graph.get_performance_monitor().get_stats())
```

Because real devs measure their flexes.

---

# CLI That Doesn’t Annoy You

```bash
fastgraph create --name social
fastgraph import data.json --format json
fastgraph export social.msgpack --format json --output out.json
fastgraph stats social.msgpack --detailed
fastgraph config --show
```

Neo4j cries reading this simplicity.

---

# Benchmarks (a taste)

| Operation        | Complexity |
| ---------------- | ---------- |
| Node lookup      | O(1)       |
| Edge lookup      | O(1)       |
| Neighbor scan    | O(degree)  |
| Indexed query    | O(log n)   |
| Batch operations | O(n)       |

This thing is FAST, bro.
You’ll feel it.

---

# Contributing

Fork it. Clone it. Break it. Improve it. PR it.
We don’t gatekeep.

---

# Credits

Made by **BRAHMAI**.
Fueled by caffeine, frustration, and the existential need for a graph engine that doesn’t suck.

---

# Final Words

FastGraph isn’t trying to compete with legacy databases.

FastGraph is the **"shut up and give me speed"** graph engine for:

* Agents
* LLMs
* Memory systems
* Recommenders
* Knowledge graphs
* Your unhinged 3 AM ideas

If your app deserves fast relationships, FastGraph deserves to be in it.
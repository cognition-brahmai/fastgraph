# FastGraph

## Native Engine v3

FastGraph v3 is an embedded property-graph engine with a Rust storage/traversal
core and a Python API. It supports **nested graphs through compound nodes**:
a node belongs to its parent graph as usual, but selecting its child graph
opens a separate scope in the same store. Graph objects are lightweight handles,
not separate databases embedded inside property dictionaries.

This is an alpha engine, not a drop-in Neo4j replacement. The older v2 material
below is historical and its performance, thread-safety and automatic-indexing
claims do not describe v3. Native benchmarks are reproducible using
`benchmarks/graph_engine.py`; no universal speed advantage is claimed.

### Installation

Python 3.10 or later is required. A source installation also needs Rust and a
platform linker:

```bash
python -m pip install .
```

For development, activate a virtual environment before building:

```bash
python -m pip install maturin
maturin develop --release
python -m pip install '.[dev,performance]'
python -m pytest tests
cargo test --lib
```

### Nested Graphs

```python
from fastgraph import FastGraph

graph = FastGraph("world")
company_node = graph.add_node("company", kind="organization")

# The node becomes compound only when its child scope is requested.
company = company_node.graph
department_node = company.add_node("engineering", kind="department")
engineering = department_node.graph
alice = engineering.add_node("alice", kind="person", age=30)
engineering.add_node("bob", kind="person", age=25)
engineering.add_edge("alice", "bob", "mentors")

# Tuple paths are absolute. String IDs are local to the selected graph scope.
assert graph.resolve(("company", "engineering", "alice")) == alice
assert alice.path == ("company", "engineering", "alice")

result = graph.bfs("company", nested=True, max_depth=3)
print([node.path for node in result.nodes])
print([node.path for node in result.path_to(alice)])

graph.save("world.msgpack")
restored = FastGraph.from_file("world.msgpack")
```

Different child graphs may reuse local IDs such as `alice` without collisions.
Removing a compound node recursively removes its contents and incident
relationships, including relationships crossing scope boundaries. Old handles
never silently refer to replacement nodes with the same local name.

### Traversal Rules

- Default traversal follows actual outgoing relationships only.
- `nested=True` adds a one-hop containment transition from a compound node to
  each direct node in its child scope. It does not fabricate stored relationships.
- `direction="in"` reverses relationships and containment transitions;
  `direction="both"` follows both directions.
- Outgoing traversal does not implicitly return from a child graph to its parent.
  Add an explicit cross-scope relationship when that behavior is required.
- A relation filter applies to real relationships, not containment transitions.
- `max_depth` counts relationship and containment hops. `max_nodes` bounds BFS
  and DFS results. Path enumeration has explicit path/expansion budgets.
- BFS retains one predecessor per discovered node. Full paths are constructed
  lazily through `result.path_to(node)` or `result.paths`, not stored eagerly.
- Discovery relationship payloads are also lazy. Access `result.edges` before
  mutating the graph to capture detached relationship snapshots; reading them
  for the first time after a mutation raises an error rather than returning
  changed data from a supposedly earlier traversal.

Cross-scope relationships use node handles or absolute tuples:

```python
graph.add_node("customer")
graph.add_edge("customer", alice, "works_with")
path = graph.shortest_path("customer", ("company", "engineering", "bob"))
print([node.path for node in path])
```

### Queries And Mutation

```python
engineering.build_node_index("kind")
people = engineering.find_nodes(kind="person", age__gte=25)
all_people = graph.find_nodes(recursive=True, kind="person")

engineering.update_node("alice", age=31)  # Merge properties.
engineering.add_node("alice", age=31)     # Replace properties, preserve identity/child scope.
```

Supported predicates are equality, `ne`, `gt`, `gte`, `lt`, `lte`, `in`,
`contains`, `exists`, and `startswith`, expressed as `property__operator`.
Equality is typed: `True`, `1`, and `1.0` are distinct. Missing properties are
distinct from an explicit `None`; use `property__exists=False` for absence.
Indexes are optional equality indexes maintained in Rust. Range predicates use
filtered scans; no B-tree or automatic query-learning claim is made.

Node and relationship properties support JSON-domain values: null, booleans,
signed 64-bit integers, finite floats, strings, lists, and string-keyed mappings.
Property containers are limited to 64 levels of nesting. Unsupported values
are rejected before mutation. Returned dictionaries are
detached copies; relationship identities cannot be reassigned.

Relationships are directed and unique by source, destination, and type. Repeated
insertion replaces relationship properties without duplicating adjacency.
Batch validation completes before writes, so invalid input cannot leave a
partially applied batch.
`add_nodes_batch` returns node handles; `add_edges_batch` returns compact
relationship IDs without reading every property payload back into Python.
Use `has_edge` and `neighbor_nodes` when only identity is needed.

### Persistence And Lifetime

Snapshots include the entire shared hierarchy, cross-scope relationships,
properties, and index definitions. JSON and MessagePack are supported, with
optional gzip compression. Pickle is rejected. Reads are size-bounded and load
validates replacement state before publishing it. Saves use unique temporary
files and atomic replacement; durable saves fsync the temporary file and, on
supported POSIX filesystems, the containing directory.

```python
graph.save("world.json", format="json", compress=False)
graph.translate("world.json", "world.msgpack")

with graph.transaction():
    graph.add_node("committed")
    # Exceptions roll back all scope changes.

graph.close()
```

Transactions are serialized **in-memory** transactions implemented with a native
snapshot copy, not WAL-backed durable commits. Save after the transaction exits.
Rollback and load invalidate previous node/child-scope handles. Closing a root
closes the shared store; closing a child handle does not delete its contents.
No background cleanup threads or network services start automatically. Context
managers close handles; auto-save must be explicitly enabled.

### Current Limits

- Whole-graph snapshots and rollback copies require additional memory.
- Node/edge storage is mutable arena/adjacency storage, not memory-mapped CSR.
- Interned property names and relation names are retained for reuse for the
  lifetime of a store; arbitrary-key churn is not automatically compacted.
- There is no WAL, MVCC, network server, Cypher parser, replication, or independent
  same-type parallel relationship identity.
- Python property callbacks use slower traversal paths than native predicates.
- Memory estimates describe native allocation capacity, not measured process RSS.
- Legacy v2 JSON/MessagePack files with supported property types can be migrated
  on load. Unsafe pickle files and the old mutable/private-storage API are not supported.

Run `python examples/nested_graphs.py` for a complete nested/cross-scope example.
The new supported tests live in `tests/`; root-level v2 scripts are historical,
not the v3 correctness suite.

### Verified Development Workload

On Windows with Python 3.11, the release build passed 322 Python tests and 22
Rust tests. The installed ABI3 wheel passed the same Python suite outside the
checkout. Two directory-fsync tests are POSIX-specific and were skipped here.
Measured Python core/CLI statement coverage is 89%; Rust coverage was not
measured. These checks establish tested behavior, not production certification.

A single synthetic million-edge run (250,000 string-ID nodes, four outgoing
relationships per node, one node property and one relationship property) gave:

| Measurement | FastGraph v3 | NetworkX MultiDiGraph |
| --- | ---: | ---: |
| Insert 1,000,000 relationships | 6.83 s | 6.45 s |
| Traverse all 250,000 nodes with BFS | 0.95 s | 1.98 s |
| Graph construction RSS increase | 321 MiB | 550 MiB |
| 100,000 hydrated point lookups | 0.58 s | 0.12 s |

This workload shows a smaller graph footprint and faster bulk traversal, not
uniformly faster APIs. FastGraph constructs detached relationship snapshots
and validates scoped access; NetworkX returns live property dictionaries.
Single hydrated reads and existence checks remain optimization targets.
Results are synthetic, memory-only, hardware-specific, and not a Neo4j comparison.

```bash
python benchmarks/graph_engine.py --nodes 250000 --edges-per-node 4 --queries 100000 --runs 3
```

---

## Historical v2 README

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

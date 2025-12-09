# FastGraph

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI Version](https://img.shields.io/badge/pypi-v2.0.0-orange.svg)](https://pypi.org/project/fastgraph/)

FastGraph is a high-performance, in-memory graph database engineered for Python applications that demand speed, low latency, and zero nonsense. Built for developers who want graph operations that actually keep up.

Created by **BRAHMAI** with ❤️ & ☕.

---

## Key Features

* High-performance adjacency-list engine with O(1) edge lookups
* Memory-efficient internals and lightweight subgraph views
* Automatic and manual indexes for ultra-fast queries
* JSON/YAML configuration system with sensible defaults
* Powerful CLI for common graph management tasks
* Persistence support across msgpack, pickle, and JSON
* Full thread safety for concurrent read/write workloads
* Integrated performance monitoring and instrumentation

---

## Quick Start

### Installation

```bash
pip install fastgraph
```

### Basic Usage

```python
from fastgraph import FastGraph

graph = FastGraph("my_graph")

graph.add_node("alice", name="Alice", age=30, type="Person")
graph.add_node("bob", name="Bob", age=25, type="Person")
graph.add_node("company", name="TechCorp", type="Company")

graph.add_edge("alice", "bob", "friends", since=2021)
graph.add_edge("alice", "company", "works_at", role="Engineer")
graph.add_edge("bob", "company", "works_at", role="Manager")

people = graph.find_nodes(type="Person")
print(len(people))

friends = graph.neighbors_out("alice", rel="friends")
print([n for n, edge in friends])

graph.save("my_graph.msgpack")
```

---

## Configuration

FastGraph supports JSON/YAML configs for repeatable setups.

Example default configuration:

```yaml
engine:
  name: "FastGraph"
  version: "2.0.0"

storage:
  data_dir: "~/.cache/fastgraph/data"
  default_format: "msgpack"

memory:
  query_cache_size: 128
  cache_ttl: 3600

indexing:
  auto_index: true
  default_indexes: ["id", "type", "name"]

performance:
  thread_pool_size: 4
  batch_threshold: 100

cli:
  default_output_format: "table"
  verbose: false
```

Usage:

```python
from fastgraph import FastGraph
from fastgraph.config import ConfigManager

config = ConfigManager("my_config.yaml")
graph = FastGraph("my_graph", config=config)
```

---

## CLI Tools

```bash
fastgraph create --name "social_network"
fastgraph import data.json --format json --save social.msgpack
fastgraph export social.msgpack --format json --output export.json
fastgraph stats social.msgpack --detailed --components
fastgraph config --show
fastgraph config --set storage.default_format=json
```

---

## Advanced Capabilities

### Indexing

```python
graph.build_node_index("type")
graph.build_node_index("age")

people = graph.find_nodes(type="Person")
engineers = graph.find_nodes(role="Engineer")

stats = graph.get_index_stats()
print(stats["global"]["index_hits"])
```

### Batch Operations

```python
graph.add_nodes_batch([
    ("user1", {"name": "John", "age": 28}),
    ("user2", {"name": "Jane", "age": 32}),
    ("user3", {"name": "Bob",  "age": 25})
])

graph.add_edges_batch([
    ("user1", "user2", "friends"),
    ("user2", "user3", "colleagues"),
    ("user1", "user3", "acquaintances")
])
```

### Subgraph Views

```python
view = graph.create_subgraph_view(
    "people",
    lambda nid, attrs: attrs.get("type") == "Person"
)

print(view.node_count)
components = graph.traversal_ops.connected_components()
```

### Traversal Algorithms

```python
bfs = graph.traversal_ops.bfs("alice", max_depth=2)
path = graph.traversal_ops.shortest_path("alice", "bob")

for p in graph.traversal_ops.find_paths("alice", "bob", max_length=3):
    print(p)
```

---

## Performance Monitoring

```python
from fastgraph.utils.performance import performance_monitor

@performance_monitor("query_op")
def q():
    return graph.find_nodes(type="Person", age__gte=25)

monitor = graph.get_performance_monitor()
print(monitor.get_stats()["query_op"].avg_duration)
```

---

## Testing

```bash
pip install fastgraph[dev]
pytest
pytest --cov=fastgraph --cov-report=html
```

---

## Development

### Setup

```bash
git clone https://github.com/fastgraph/fastgraph.git
cd fastgraph
pip install -e ".[dev]"
pre-commit install
```

### Quality

```bash
black fastgraph tests examples
flake8 fastgraph tests examples
mypy fastgraph
pre-commit run --all-files
```

---

## Benchmarks

FastGraph is tuned for high throughput and low latency.

| Operation      | Complexity |
| -------------- | ---------- |
| Node lookup    | O(1)       |
| Edge lookup    | O(1)       |
| Neighbor query | O(degree)  |
| Indexed search | O(log n)   |
| Batch inserts  | O(n)       |

Detailed benchmarks live in `benchmarks/`.

---

## Contributing

1. Fork the repo
2. Create a branch
3. Commit your changes
4. Push and open a PR

We keep contributions simple and frictionless.

---

## License

MIT. See the LICENSE file.

---

## Acknowledgments

FastGraph builds on proven graph database principles and a relentless focus on performance and developer experience. Thanks to all contributors and the Python ecosystem that made it possible.
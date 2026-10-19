# FastGraph v3 In-Depth Benchmark Report

**Date:** 2026-10-17  
**Engine revision:** `54ab9b5e362996855c35be629ccf78a2a08d4df9`  
**Build:** optimized Rust release, ABI3 wheel, FastGraph `3.0.0`  
**Scope:** embedded in-memory graph libraries, nested scopes, property queries, mutations, full snapshots, and same-store read concurrency.

Primary measurements ran from 12:08 UTC; corrected nested measurements finished at approximately 12:40 UTC. Smoke/reproduction checks are separate from those sample counts.

## 1. Executive Summary

FastGraph has useful advantages, but it is **not yet an across-the-board faster, lighter graph engine**. Results depend strongly on property representation, output materialization, API layer, topology, and operation.

- **Sparse graphs:** the public FastGraph API had a much smaller post-load process footprint than NetworkX. At 250,000 nodes and 1,000,000 relationships, the RSS increase was **322.28 MiB versus 1,002.64 MiB** in this input/adapter setup.
- **Bulk loading:** the same million-relationship workload took **3.193 s** for FastGraph edge insertion, **2.571 s** for NetworkX, **1.076 s** for rustworkx, and **0.379 s** for igraph. FastGraph is not the loading winner.
- **Traversal:** default full BFS took **668.24 ms** through the FastGraph facade, versus **1,144.44 ms** for NetworkX, **330.39 ms** for rustworkx, and **25.15 ms** for igraph. These APIs return different payloads, so this is an API-workload comparison, not a pure algorithm ranking.
- **Equality indexes:** a 100-match query over 100,000 nodes fell from **9.366 ms unindexed to 0.0549 ms indexed** through the facade, approximately **171x** in this selective workload. Range predicates did not receive this benefit.
- **Rich properties:** at 25,000 nodes and 100,000 relationships, FastGraph's RSS increase was **163.82 MiB**, exceeding NetworkX's **142.76 MiB**, rustworkx's **130.39 MiB**, and igraph's **108.13 MiB**. The sparse-memory advantage does not generalize to rich values.
- **Nested graphs:** hierarchical selection, containment hops, depth bounds, repeated local IDs, and explicit cross-scope traversal validated. Qualified lookup grows with path depth; cached node handles remain much cheaper.
- **Concurrency:** the facade does not scale same-store BFS throughput across threads. Direct native readers do overlap; this is not evidence that the facade does.
- **Persistence:** serialization, validation, Python object staging, compression, and reconstruction dominate. A durable, uncompressed MessagePack snapshot of 100,000 nodes/400,000 relationships saved in **2.343 s** and loaded in **3.577 s** from a warm filesystem cache.

**Conclusion:** the strongest current position is a scoped embedded property graph with efficient selective equality queries and a compact sparse topology. To compete broadly with mature native libraries, the next work should focus on property layout, facade/result materialization, traversal kernels, scoped read concurrency, and a native persistence format.

No Neo4j server was benchmarked. Nothing here establishes a Neo4j speedup or equivalent database guarantees.

## 2. Evidence And Reproducibility

The report is based on actual runs, not extrapolated complexity claims or hardcoded test outcomes.

| Evidence | Count/result |
| --- | ---: |
| Original flat measurement processes | 200 |
| Original feature measurement processes | 137 |
| Supplementary memory/predecessor processes | 60 |
| Nested corrective reruns | 36 |
| Total measurement processes executed | 433 |
| Samples retained in final aggregate | 397 |
| Superseded nested samples retained as raw evidence | 36 |
| Final retained case/engine groups | 127 |
| Correctness failures, timeouts, or RAM skips in retained measurements | 0 |
| Release validation before timing | 322 tests passed, 2 POSIX-only skips |

Smoke runs were used to validate the harness and are excluded from performance aggregates. A smoke-only adapter spelling error was corrected before measured runs. No engine implementation was modified or tuned during this benchmark request.

### Raw artifacts

- [Aggregate statistics, JSON](benchmarks/results/2026-10-17/summary.json)
- [All scalar statistics, CSV](benchmarks/results/2026-10-17/summary.csv)
- [Host/build metadata](benchmarks/results/2026-10-17/hardware.json)
- [Flat samples](benchmarks/results/2026-10-17/flat/samples.jsonl) and [manifest](benchmarks/results/2026-10-17/flat/manifest.json)
- [Feature samples](benchmarks/results/2026-10-17/features/samples.jsonl) and [manifest](benchmarks/results/2026-10-17/features/manifest.json)
- [Supplementary controls](benchmarks/results/2026-10-17/supplement/results.json)
- [Final corrected nested runs](benchmarks/results/2026-10-17/nested-final/results.json)
- [Intermediate nested correction](benchmarks/results/2026-10-17/nested-corrected/results.json), preserved but superseded
- [Harness](benchmarks/in_depth.py), [peer adapters](benchmarks/_peers.py), and [aggregator](benchmarks/analyze_results.py)

The aggregate uses an explicit replacement rule: a later source replaces the same case/engine/repetition identity. Original raw files are never deleted. This prevents corrective reruns from being counted as extra independent repetitions.

### Provenance

The engine was built with `maturin build --release --locked`, installed into a dedicated virtual environment, and imported from `site-packages`, not the checkout. Engine source hashes matched across flat, feature, and supplementary runs. Harness hashes differ where controls were added; each manifest records the version actually used.

**Release wheel SHA-256:**

```text
5d82e802cf174739291c92552b2cab24c7cfec09440d24543d00a062a1df700f
```

**Native source SHA-256:**

```text
f9a55416dfc576a850c88f72afd5b61154640153b9fc44dfb70752ea85a55c10
```

The full manifest also fingerprints `Cargo.toml`, `Cargo.lock`, the graph/traversal/persistence facade, and both benchmark source files. Installed package files and the compiled extension were checked against wheel provenance during independent review.

## 3. Environment

| Component | Configuration |
| --- | --- |
| CPU | AMD Ryzen AI 9 365 with Radeon 880M |
| Cores | 10 physical, 20 logical |
| OS | Windows build 26200, 64-bit |
| Python | CPython 3.11.9, MSC 1938, AMD64 |
| Rust / Cargo | 1.90.0 / 1.90.0 |
| Power policy | Performance |
| Physical RAM | 23.12 GiB |
| Available RAM before primary workers | 2.92-5.59 GiB |
| Lowest available RAM after primary workers | 2.58 GiB |
| Storage | MTFDKBK1T0QFM-1BD1AABGB, approximately 1 TB, NTFS |
| FastGraph distribution | fastgx 3.0.0 |
| NetworkX | 3.6.1 |
| rustworkx | 0.18.1 |
| igraph | 1.0.0 |
| NumPy | 2.4.6 |
| MessagePack | 1.2.3 |
| psutil | 7.2.2 |
| Maturin | 1.15.0 |

The machine was not a dedicated bare-metal benchmark host. Existing applications consumed substantial RAM. Processes ran serially, with a 1.5 GiB available-RAM guard. CPU affinity was not pinned, OS caches were not flushed, and thermal behavior was not independently controlled. These are local engineering measurements, not cross-machine capacity guarantees.

## 4. Measurement Method

### Isolation and repetition

- One fresh subprocess per engine/workload/repetition; no concurrent benchmark workers.
- Five repetitions for the 25K/100K-node scale comparisons; three for the million-edge case and most feature/shape controls.
- The larger persistence cases have two repetitions and should be treated as particularly limited samples.
- Engine order rotates between repetitions within primary/corrective cases. Supplementary lifecycle/predecessor cases use a fixed engine order across repetitions, which can introduce time-order bias.
- Deterministic workload seed `20261017`; `PYTHONHASHSEED=0`.
- Input generation is excluded from construction timers, but measured separately.
- Counts and construction correctness assertions execute after timed insertion.
- Garbage collection remains enabled. Explicit collections happen outside measured operation timers.
- Some reads/BFS operations have an untimed warmup. This is warm API performance, not first-call latency.

### Timing and statistics

Wall time uses `perf_counter_ns`. Main tables show the **median of independent fresh-process values**, not the fastest trial. Within-process repetitions and all raw samples remain available.

Reported p50/p95/p99 point latencies are medians of per-process nearest-rank percentiles over 2,000 timed calls. They include Python dispatch, timestamp overhead, and destruction of the previous returned object when the loop assigns a new result; these costs were not subtracted. They are not production service tail-latency SLAs. Five or three fresh processes do not justify strong significance or long-tail claims.

`process_time_ns` is also recorded, but raw CPU-time samples were quantized to 15.625 ms on this host; medians can interpolate between those ticks. Many short operations therefore report zero CPU time. CPU columns are retained in raw data but are not used for microsecond efficiency conclusions.

Read throughput loops include Python iteration and result consumption. The bulk `edge_get_hit` workload also checks returned weights against a reference dictionary inside the loop. Thus its time is not an isolated native getter microkernel. Single-call latency samples do not include that weight check.

### Memory

Flat post-load RSS/private-byte deltas are captured after initial load inputs are deleted and collected, **before** reference/query data is regenerated. They include the graph, necessary adapter ID maps/payloads, and allocator capacity retained from input preparation. They are not exact object-ownership measurements or bytes-per-edge constants.

The dataset constructs string endpoints independently for edge records. Libraries differ in interning, canonicalization, and retained string references. Earlier smoke benchmarks reused different ID/property layouts; their memory numbers should not be treated as this run's regression baseline.

Windows process peak working set is cumulative. Stage high-water marks may include preceding input preparation, snapshot stages, reference objects, or other results. A later maximum is not proof of that operation's isolated allocation requirement.

Nested footprint numbers additionally retain node/path maps, handles, scopes, and a relationship oracle. The flattened NetworkX model stores synthetic containment relationships. **Nested RSS numbers are benchmark-fixture footprints, not a clean graph-only memory comparison.**

Isolated lifecycle controls were added to measure index growth and clear/release without query/reference oracles. Native capacity estimates are separate from measured process RSS and must never be summed across handles sharing one store.

## 5. Comparator Semantics

| Backend | Storage/API representation used |
| --- | --- |
| FastGraph | Public Python facade, local string IDs, typed native properties, detached reads, scoped validation |
| Native diagnostic | Direct `NativeStore` calls; a benchmark string-to-integer map is retained; no public facade guarantees or handle/result overhead |
| NetworkX | Directed `MultiDiGraph`, relation type used as edge key, Python property dictionaries |
| rustworkx | Directed `PyDiGraph`, external ID map, `(ID, attrs)` node payloads and `(relation, attrs)` edge payloads |
| igraph | Directed C graph, external ID map, property columns, reserved ID/type columns |

The adapters preserve relationship identity, multiplicity, replacement-upsert semantics, and directed reachability. External ID translation and adapter payload construction are included in load timings.

FastGraph/native getters allocate detached properties. NetworkX/rustworkx getters normally expose live dictionaries; igraph assembles shallow dictionaries. Copied-property timings explicitly deep-copy peer outputs. FastGraph also constructs an immutable-identity relationship result, so even the detached tier is not a perfectly identical object-return ABI.

Default BFS payloads differ:

- FastGraph returns node handles, predecessor/depth maps, and lazy discovery-edge IDs.
- NativeStore returns four parallel arrays.
- NetworkX materializes discovery-successor groups, not `bfs_tree()`.
- rustworkx returns adjacency-successor payloads that can repeat reached nodes; the adapter deduplicates to validate the visited count.
- igraph returns native visited/layer/parent arrays.

Default BFS tables therefore measure useful public-library workloads. Supplementary predecessor-array controls provide a narrower result-shape comparison, with their own explicit limitations.

## 6. Datasets

All initial relationship triples are unique. Initial endpoints exist. Graphs are directed and unweighted for path algorithms; edge `weight` is a retrieved property, not a weighted-path request.

| Workload | Nodes / relationships | Characteristics |
| --- | --- | --- |
| Sparse ring scale | 25K/100K, 100K/400K, 250K/1M | Four offsets per source: 1, 7, 37, 181; strongly connected |
| Chain | 20,000/19,999 | Long predecessor/path output; low degree |
| Outgoing star | 25,000/24,999 | One hub, many sinks |
| Disconnected rings | 25,000/100,000 | Ten components; BFS from zero reaches 2,500 nodes |
| Hub-skewed | 25,000/100,000 | Ring backbone plus seeded Pareto-biased targets; synthetic, not an empirical power-law dataset |
| Empty properties | 25,000/100,000 | Topology-only property maps |
| Rich properties | 25,000/100,000 | Strings, lists, nested dictionaries, multiple fields |
| Batch-size control | 2,000/8,000 | Batch sizes 1, 256, and whole load |
| Nested hierarchy | 8,353 or 66,177 nodes | World, departments, teams, repeated local leaf IDs, containment, cross-scope links |
| Depth selection | 4/16/64/256 levels | A chain of compound nodes; path versus cached handle |

Sparse node properties are `group = i % 1000` and `score = i % 10000`. Sparse relationships have an integer weight from 1 through 10. Rich strings and nested values are highly structured and repeated; this is not random text or embedding storage.

## 7. Bulk Construction And Scale

Times below exclude input generation and count validation. Node batches return handles/IDs according to the API. Edge batches return compact results, without eagerly hydrating every FastGraph edge.

### Edge insertion median, milliseconds

| Nodes / edges | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| 25K / 100K | 211.96 | 100.56 | 199.99 | 88.41 | 33.24 |
| 100K / 400K | 846.41 | 455.24 | 817.90 | 444.59 | 144.17 |
| 250K / 1M | 3,192.87 | 1,444.68 | 2,571.00 | 1,075.70 | 378.99 |

### Node insertion median, milliseconds

| Nodes | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| 25K | 32.58 | 20.01 | 16.34 | 6.00 | 8.52 |
| 100K | 216.30 | 94.17 | 80.98 | 30.24 | 39.64 |
| 250K | 557.62 | 277.20 | 227.41 | 79.87 | 107.25 |

The facade adds meaningful validation, mapping/result, and Python allocation costs. Direct native insertion is about 2x faster than the facade in these cases, but igraph/rustworkx remain stronger loading baselines. At one million edges, FastGraph's edge insertion is approximately 24% slower than NetworkX in this workload.

For the 100K-node case, edge-load min/median/max was 840.01/846.41/877.50 ms for FastGraph. Its coefficient of variation across five workers was 1.81%. This is reasonably stable locally, not a universal hardware-independent result.

### Batch-size control: 8,000 edge records, milliseconds

| Batch size | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 15.45 | 8.31 | 10.08 | 4.88 | 214.42 |
| 256 | 8.21 | 4.73 | 7.79 | 1.86 | 3.26 |
| Whole load | 9.28 | 5.26 | 7.78 | 2.15 | 2.35 |

Batch size 1 means one record per **batch API call**, not FastGraph's singular `add_edge()` API with hydrated return objects. Do not extrapolate these tiny-load timings to a universal optimum of 256: allocation and warm-state effects are substantial at this scale. The reliable conclusion is to avoid per-record FFI/library calls for bulk construction.

## 8. Memory Footprint And Property Cost

### Post-load RSS increase, MiB

| Nodes / edges | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| 25K / 100K | 35.79 | 41.54 | 103.05 | 53.28 | 29.54 |
| 100K / 400K | 119.39 | 158.18 | 404.61 | 203.98 | 78.41 |
| 250K / 1M | 322.28 | 421.77 | 1,002.64 | 501.54 | 174.38 |

At one million edges, private-byte increases were 333.63 MiB for FastGraph, 434.15 MiB for the native diagnostic, 1,004.26 MiB for NetworkX, 503.71 MiB for rustworkx, and 172.80 MiB for igraph.

The direct native row is **not** a stripped native-arena minimum: its benchmark adapter retains a redundant Python external-ID map. This explains why its process footprint can exceed the public facade's despite less execution overhead.

For this sparse profile, FastGraph's RSS increase is about 68% below NetworkX's and 36% below rustworkx's at 1M edges, but approximately 85% above igraph's. Do not interpret those percentages as exact native object sizes or estimates for other property/ID layouts.

### Property profile at 25K nodes / 100K edges, RSS increase MiB

| Profile | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| Empty | 24.77 | 27.77 | 70.61 | 33.23 | 24.41 |
| Sparse | 35.79 | 41.54 | 103.05 | 53.28 | 29.54 |
| Rich | 163.82 | 181.90 | 142.76 | 130.39 | 108.13 |

**The rich-property case reverses FastGraph's memory advantage over NetworkX.** Native recursive property ownership and conversion have a different sharing/layout cost from Python-backed property dictionaries and igraph columns. Identical logical values do not imply identical physical sharing. This is a priority for profiling before promoting the engine as universally lightweight.

## 9. Traversal And Output Cost

### Default BFS median, milliseconds

| Nodes / edges | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| 25K / 100K | 17.86 | 8.78 | 32.48 | 15.78 | 1.08 |
| 100K / 400K | 203.29 | 67.14 | 447.61 | 124.18 | 6.97 |
| 250K / 1M | 668.24 | 416.49 | 1,144.44 | 330.39 | 25.15 |

At 1M edges, the facade is about 1.71x faster than the NetworkX successor workload, but slower than rustworkx and much slower than igraph's array-returning API. The facade and each peer materialize different payloads; these are not pure kernel speedups.

FastGraph's default BFS retains linear predecessor state. At 100K reached nodes, the measured RSS increment for the retained traversal result was 9.42 MiB; the raw native result increment was 0.91 MiB in that phase. Allocator reuse makes these incremental numbers contextual, not allocation-size formulas.

### Topology sensitivity: default BFS median, milliseconds

| Shape | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chain, 20K reached | 9.20 | 4.31 | 11.36 | 7.69 | 0.66 |
| Star, 25K reached | 9.00 | 2.71 | 10.11 | 1.98 | 0.70 |
| Disconnected, 2.5K reached | 1.36 | 1.19 | 2.21 | 1.19 | 0.12 |
| Hub-skewed, 25K reached | 17.90 | 7.82 | 25.34 | 11.33 | 0.76 |

The low-degree chain and outgoing star have fewer relationships than the ring/hub datasets. Their times must not be compared as if they all scan the same edge count.

### Matched predecessor-array control

Additional runs construct ordered IDs/handles, predecessor and depth arrays, plus an edge-slot array in every backend. The FastGraph facade and all three peers use placeholder edge slots in this control; only direct native results carry real discovery-edge IDs. Rustworkx uses a Python BFS over native successor indices for this control, while its default API table above uses native `bfs_successors`. The control is about result shape and useful overhead boundaries, not an assertion that all kernels are identical.

| Nodes / edges | FastGraph facade | Native arrays | NetworkX arrays | rustworkx successor-loop arrays | igraph BFS plus arrays |
| --- | ---: | ---: | ---: | ---: | ---: |
| 25K / 100K | 19.80 ms | 9.37 ms | 25.55 ms | 8.61 ms | 3.00 ms |
| 100K / 400K | 128.91 ms | 74.53 ms | 222.23 ms | 38.46 ms | 18.89 ms |

The change from default-library payloads to these arrays changes rankings and absolute times. That is exactly why a single BFS marketing multiplier would be misleading.

### FastGraph callback and materialization costs, 25K-node ring

| Operation | Median |
| --- | ---: |
| Default BFS | 17.86 ms |
| Property-filtered BFS, all nodes allowed | 23.98 ms |
| Always-true edge-callback BFS | 72.99 ms |
| DFS | 119.65 ms |
| Hydrate previously unread discovery edges | 50.94 ms |

An edge callback changes the implementation path to Python iteration and hydrates relationships. DFS also uses Python iteration. Native BFS results therefore cannot predict callback or DFS performance. Property filters may preselect allowed IDs across the whole shared store before searching the reachable component.

Explicitly materializing every full path on a chain was intentionally not done: that output is quadratic even with a linear retained predecessor tree. One full shortest path on the 20K-node chain was measured. FastGraph took 13.76 ms, native 4.13 ms, NetworkX 6.88 ms, rustworkx's chosen target Dijkstra API 363.13 ms, and igraph 0.56 ms. Different algorithm/API choices make this a workload result, not proof of an inherent rustworkx limitation.

## 10. Point Operations And Latency

### Burst workload: 30,000 successful checks/reads, milliseconds

| 100K-node ring operation | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| Relationship existence | 28.52 | 22.77 | 62.26 | 44.74 | 64.89 |
| Relationship read plus weight verification | 83.71 | 60.70 | 99.27 | 61.94 | 111.89 |
| Detached relationship-properties tier | 83.71 | 60.70 | 123.86 | 72.21 | 115.83 |
| Node property read | 36.14 | 27.99 | 23.99 | 20.26 | 42.41 |

The detached peer tier adds `deepcopy`; FastGraph/native already detach values. Its loop is not identical to the weight-verification loop, and only scalar weights are present in this sparse profile. Use these results as API-workload evidence, not a precise estimate of deep-copy cost.

At 1M edges, FastGraph's verified relationship-read loop took 152.13 ms versus NetworkX's live-mapping 98.18 ms. The facade is therefore not consistently faster at reads across sizes. Existence checks avoid property hydration and are the more appropriate identity-only path.

### Single-call latency on the 100K-node ring, microseconds

Values are median per-process percentiles, with 2,000 calls per process. Existence latency uses mixed hits/misses; relationship-get latency uses hits.

| Backend | Existence p50 / p95 / p99 | Relationship get p50 / p95 / p99 |
| --- | ---: | ---: |
| FastGraph | 1.1 / 1.5 / 1.7 | 2.5 / 3.1 / 3.6 |
| Native diagnostic | 0.9 / 1.3 / 1.6 | 1.8 / 2.4 / 2.7 |
| NetworkX | 2.0 / 3.1 / 3.8 | 2.0 / 3.1 / 3.7 |
| rustworkx | 1.8 / 2.8 / 3.4 | 2.0 / 3.2 / 4.0 |
| igraph | 2.3 / 3.4 / 4.1 | 3.5 / 4.5 / 5.4 |

These are local hot-memory Python-call measurements. They include adapter ID/type checking, dispatcher cost, and timer overhead. They are not equivalent to graph-server request latencies.

## 11. Property Queries And Indexes

### Query cardinalities

| Predicate | 25K nodes | 100K nodes |
| --- | ---: | ---: |
| `group == 107` | 25 | 100 |
| Missing group `1001` | 0 | 0 |
| `score >= 9990` | 20 | 100 |
| `score >= 5000` | 10,000, or 40% | 50,000, or 50% |
| `group == 107 AND score >= 5000` | 10 | 50 |

NetworkX uses a straightforward Python reference scan here. No rustworkx/igraph property-query ranking is claimed; their alternative query/vector interfaces were not measured in this tier.

### 100K-node query median, milliseconds

| Query | FastGraph scan | FastGraph indexed | Native scan | Native indexed | NetworkX reference scan |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rare equality, 100 outputs | 9.366 | 0.0549 | 7.697 | 0.0043 | 8.217 |
| Equality miss | 9.406 | 0.0036 | 8.005 | 0.0005 | 6.692 |
| Range, 100 outputs | 10.643 | 27.043 | 9.865 | 10.480 | 6.168 |
| Broad range, 50K outputs | 64.500 | 120.718 | 11.934 | 10.915 | 11.440 |
| Equality plus range, 50 outputs | 18.324 | 0.0325 | 8.107 | 0.0051 | 7.164 |
| Rare equality, limit 10 | 1.378 | 0.0083 | 0.304 | 0.0011 | 0.675 |

Both `group` and `score` equality indexes existed in the indexed tier. **Range-only predicates still scan.** The score index is not an ordered range index. Differences between before/after range timings include allocation/cache state and do not demonstrate a range-index benefit.

Native indexed results are IDs; the facade fetches detached properties for each match. For broad selections, output conversion is a major cost. NetworkX's reference returns live mappings, so its broad-query time is not a copied-property comparator.

### Index build and isolated memory growth

| Nodes | Facade/native group build | Facade/native score build | Isolated FastGraph RSS increase for both indexes |
| --- | ---: | ---: | ---: |
| 25K | 2.993 / 3.182 ms | 3.638 / 4.256 ms | 2.53 MiB |
| 100K | 34.806 / 20.394 ms | 41.043 / 19.196 ms | 3.37 MiB |

Index builds are measured independently, not attributed to insertion. Both process contexts invoke the same direct native `create_index` operation to isolate construction; the facade column does not include an additional Python index-manager call. The isolated memory increase can be below estimated capacity because an allocator reuses already-committed pages. It is not a portable index-size formula.

For the selective 100-match query, the 100K-node group index's build cost is amortized after approximately four similar facade queries under these measurements. That calculation does not apply to range-only or high-output queries.

## 12. Mutation, Clear, And Selection Views

The mutation workload uses 25K nodes/100K edges. It replaces 1,000 existing relationships, updates 1,000 nodes, deletes 1,000 relationships, then deletes 500 nodes and validates all incident cleanup.

| Operation | FastGraph | Native diagnostic | NetworkX | rustworkx | igraph |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,000 relationship replacement upserts | 1.75 ms | 1.28 ms | 0.33 ms | 0.69 ms | 1.68 ms |
| 1,000 node score changes | 2.24 ms | 1.38 ms | 0.38 ms | 0.36 ms | 1.70 ms |
| 1,000 relationship deletions | 4.31 ms | 1.01 ms | 0.90 ms | 0.48 ms | 3.42 ms |
| 500 node deletions | 2.20 ms | 2.24 ms | 1.25 ms | 0.53 ms | 4.96 ms |
| Clear remaining graph | 49.75 ms | 49.87 ms | 37.72 ms | 6.27 ms | 2.06 ms |

The mutation tier is not a transactional comparison. Native node updates/deletions use batch/direct APIs where available; the facade calls checked methods. Peer updates replace relationship properties explicitly rather than NetworkX's default merge behavior. Igraph's ID-map rebuilding after vertex renumbering is included.

No duplicate-edge count drift, ghost relationship, or incident-edge cleanup mismatch occurred in these trials.

### Isolated FastGraph memory lifecycle, absolute RSS MiB

These controls retain no query/reference oracle. Both equality indexes are built before deletion.

| Stage | 25K / 100K edges | 100K / 400K edges |
| --- | ---: | ---: |
| Before graph/input construction | 31.44 | 31.38 |
| Loaded, input references freed | 63.14 | 146.64 |
| Two indexes built | 65.83 | 149.99 |
| Half the nodes deleted | 59.87 | 127.23 |
| Graph cleared | 52.30 | 100.99 |
| Root closed and adapter released | 34.84 | 35.27 |

`clear()` does not trim all native capacity or intern pools. At the larger scale, the cleared graph remains roughly 70 MiB above the initial process RSS, while closing/releasing the store approaches the baseline. This is retained capacity/allocator behavior; it is not evidence that cleared logical nodes still exist.

### Fixed-membership views

| Metric | 25K-node graph | 100K-node graph |
| --- | ---: | ---: |
| Select 10% of nodes | 3.60 ms | 14.80 ms |
| Count selected live nodes | 0.122 ms | 0.530 ms |
| Materialize induced edges | 10.83 ms | 55.88 ms |
| View BFS | 0.49 ms | 2.24 ms |

The selected views contain 2,500/10,000 nodes and 6,375/25,500 induced relationships. Only 100 nodes are reachable from zero inside each induced selection. View BFS times must not be compared with whole-graph BFS as if they visit the same data.

## 13. Nested Graphs

The hierarchy has a world node, department scopes, four team scopes per department, and repeated local leaf IDs. Each leaf scope has a three-offset ring. Sparse explicit cross-scope links connect leaf groups in a cycle.

| Dataset | Departments | Teams | Leaves | Total nodes | Stored real relationships | Child scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Small | 32 | 128 | 8,192 | 8,353 | 24,704 | 161 |
| Large | 128 | 512 | 65,536 | 66,177 | 197,120 | 641 |

NetworkX stores qualified tuple IDs and 8,352/66,176 additional explicit containment relationships. It is a **flattened semantic reference**, not a native nested-scope implementation.

### Final corrected nested timings, milliseconds

| Operation | Small FastGraph | Small native | Small flattened NX | Large FastGraph | Large native | Large flattened NX |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Build hierarchy/model | 58.12 | 30.65 | 65.90 | 547.28 | 325.95 | 850.47 |
| Nested BFS from world | 3.86 | 2.17 | 1.10 | 71.72 | 33.17 | 10.52 |
| Parent-only traversal | 0.0033 | 0.0007 | 0.0054 | 0.0037 | 0.0007 | 0.0158 |
| Nested traversal capped at depth 2 | 0.043 | 0.014 | 0.020 | 0.149 | 0.041 | 0.072 |
| Leaf-start cross-scope BFS, no containment | 4.09 | 1.89 | 2.46 | 71.24 | 35.84 | 27.89 |
| 10,000 qualified leaf-property reads | 22.30 | 12.76 | 4.86 | 28.63 | 18.59 | 10.65 |
| 10,000 cached-handle reads | 7.68 | 4.55 | 4.12 | 15.55 | 11.10 | 10.52 |

The parent-only control actually executes traversal in every backend. It visits the world node only; containment requires explicit opt-in. The depth-2 control reaches 161/641 nodes, not the leaf layer.

The cross-scope control starts at a leaf with containment disabled and must reach all 8,192/65,536 leaves while excluding compound owners. Removing the explicit cross links would change that result, so this control genuinely validates forward cross-scope traversal rather than relying on world-to-leaf containment.

Nested FastGraph BFS is slower than the flattened NetworkX reference here. The reference returns distances on an already-expanded graph; FastGraph returns scoped handles and predecessor state while discovering child scopes. Neither that time difference nor fixture-memory differences isolate the cost of the nested abstraction alone.

The large recursive property query selected 32,768 leaves. It took approximately 90.7 ms in the original facade trial set versus 11.3 ms for native IDs; the raw files retain this output-conversion diagnostic. Nested query results should be projected or limited when full detached properties and qualified paths are unnecessary.

### Nesting depth: microseconds per operation

| Depth | Facade absolute-path property lookup | Native path walk | Facade cached-handle read | Reopen existing child graph handle |
| --- | ---: | ---: | ---: | ---: |
| 4 | 1.62 | 0.66 | 0.264 | 7.67 |
| 16 | 4.16 | 2.26 | 0.269 | 7.80 |
| 64 | 14.11 | 8.86 | 0.264 | 7.73 |
| 256 | 54.90 | 35.64 | 0.265 | 7.80 |

Qualified lookup is approximately linear in hierarchy depth. A checked cached node handle avoids repeated path walking. Existing child scope selection is idempotent in the release tests; the depth benchmark checks that reopen calls do not add nodes, not a complete scope-identity proof. Constructing a new facade handle/managers on each `.graph` access has a measurable fixed cost. Reuse scope handles in hot loops.

## 14. In-Memory Transactions

These are snapshot-backed, serialized in-memory transactions, **not WAL commits**.

| Graph size | Empty transaction | Commit ten node merges | Roll back ten node merges |
| --- | ---: | ---: | ---: |
| 25K nodes / 100K edges | 24.94 ms | 23.87 ms | 22.97 ms |
| 100K nodes / 400K edges | 100.77 ms | 98.95 ms | 137.11 ms |

Entry clones the entire native store even when no mutation occurs. The table demonstrates fixed graph-size-dependent cost; the ten merges themselves are not responsible for most of this duration. A commit being slightly below the empty median is normal run variation, not evidence that additional writes are free.

Rollback restores properties and invalidates old handles through the epoch. The facade lock remains held across the user context, so readers of any scope in that store wait. Per-small-operation transactions are not an efficient workload for this design.

## 15. Persistence And Warm-Cache Load

Persistence benchmarks include a group equality index and validate counts, properties, and post-load index maintenance. JSON and MessagePack use the same versioned hierarchy schema. Compression is gzip at the implementation's default level. Each save includes full capture, validation, encoding, atomic replacement, and optional fsync.

### Durable snapshots: median time and file size

| Nodes / edges | Format | gzip | File MiB | Save ms | Full warm load ms |
| --- | --- | --- | ---: | ---: | ---: |
| 25K / 100K | JSON | No | 8.66 | 628.73 | 491.97 |
| 25K / 100K | JSON | Yes | 0.93 | 656.82 | 500.71 |
| 25K / 100K | MessagePack | No | 5.64 | 303.50 | 468.36 |
| 25K / 100K | MessagePack | Yes | 0.85 | 869.35 | 466.83 |
| 100K / 400K | JSON | No | 35.28 | 3,067.80 | 3,844.99 |
| 100K / 400K | JSON | Yes | 3.75 | 4,795.75 | 3,876.11 |
| 100K / 400K | MessagePack | No | 23.59 | 2,343.36 | 3,577.06 |
| 100K / 400K | MessagePack | Yes | 3.38 | 5,914.33 | 3,632.50 |

The larger rows have only two fresh-process repetitions. Compression ratios are favorable because the dataset contains highly structured repetitive values. Random text, embeddings, or precompressed values can behave differently.

MessagePack without gzip is the fastest save path in this dataset. MessagePack plus gzip is smaller but slower than gzip JSON here. Compression therefore must not be presented as a blanket throughput improvement.

### Non-fsynced versus fsynced save, 25K / 100K, milliseconds

| Format | No fsync | fsync enabled |
| --- | ---: | ---: |
| JSON | 653.81 | 628.73 |
| JSON + gzip | 658.33 | 656.82 |
| MessagePack | 298.50 | 303.50 |
| MessagePack + gzip | 864.20 | 869.35 |

The fsync signal is small relative to capture/encoding cost and local variation. The JSON ordering is not evidence that fsync makes saves faster. On Windows, the implementation fsyncs the file but skips POSIX directory fsync. No power-loss durability or crash-consistency experiment was performed.

### Stage decomposition at 100K / 400K

- Native JSON snapshot serialization: approximately 145-148 ms.
- Facade snapshot creation, including JSON-to-Python envelope staging: approximately 985-1,014 ms.
- Warm file decoding/validation: approximately 2,014-2,217 ms.
- Native reconstruction from an already prepared store JSON string: approximately 804-832 ms.

These phases were measured as diagnostics, not added together to predict full I/O time: staging overlaps, allocation state differs, and full load performs additional conversion/publication work. The architectural finding is nevertheless clear: multiple complete representations and validation/conversion passes dominate more than the final file write.

Cumulative process peak RSS reached roughly **552-553 MiB** by the save stage and **785 MiB** by the full-load stage in the larger workers. Those peaks include prior reference/staging work and coexisting source/restored graphs; they are not isolated per-operation allocation requirements. Budget extra memory for persistence instead of assuming retained native graph RSS is sufficient.

Every load followed a save/decoding sequence. These are **filesystem-warm** results. Fresh Python processes do not evict the OS cache. No cold-storage, recovery-log, or database-commit comparison is claimed.

The facade's default load limit is 256 MiB for both encoded and decompressed input. The harness explicitly uses 512 MiB for these loads and records it. Successful save does not imply a larger snapshot can be reloaded under the default cap.

## 16. Same-Store Read Concurrency

Point tests perform 20,000 existence checks in total, divided across workers. BFS tests perform two full traversals **per worker**, so total work increases with thread count. Executor setup/scheduling is included. This is not a fixed-total-work BFS latency table.

### Point checks, total wall milliseconds

| Threads | FastGraph facade | Native diagnostic | NetworkX |
| --- | ---: | ---: | ---: |
| 1 | 18.60 | 15.52 | 25.43 |
| 2 | 15.66 | 13.05 | 24.87 |
| 4 | 16.31 | 12.33 | 23.28 |
| 8 | 16.44 | 13.66 | 22.31 |

This small workload does not scale linearly. Scheduling, cache state, attached native point operations, and the GIL limit interpretation of small differences. Do not report the sub-2x variation as an eight-core speedup.

### Two full BFS traversals per worker, total wall milliseconds

| Threads / total traversals | FastGraph facade | Native diagnostic | NetworkX |
| --- | ---: | ---: | ---: |
| 1 / 2 | 42.08 | 23.41 | 119.11 |
| 2 / 4 | 85.88 | 23.68 | 252.37 |
| 4 / 8 | 163.33 | 25.74 | 632.58 |
| 8 / 16 | 329.64 | 31.66 | 1,620.68 |

The facade spends approximately the same time per traversal as more work is added: its shared `RLock` serializes same-store operations. Native readers complete much more total work in a similar time window because long reads release the GIL under shared read locks. Output conversion still requires the GIL.

The public facade's read concurrency and direct native concurrency must be discussed separately. Independent-store multiprocessing, mixed read/write workloads, tail latency under load, and saturation throughput were not measured.

## 17. Variability And Evidence Limits

| 100K-node metric | FastGraph min / median / max | NetworkX min / median / max |
| --- | ---: | ---: |
| Edge load | 840.01 / 846.41 / 877.50 ms | 812.35 / 817.90 / 856.51 ms |
| Default BFS | 195.65 / 203.29 / 256.05 ms | 440.52 / 447.61 / 458.32 ms |

FastGraph's BFS coefficient of variation was 13.61% in that five-worker case, compared with NetworkX's 1.55%. The median is preferable to a best-case headline; the observed range should remain visible.

Additional limits:

- Synthetic topologies and structured properties are not a production workload trace.
- Equality/range predicates used ordinary positive integers; typed/null correctness is covered by release tests and adapter smoke checks, not a full performance matrix over every JSON type.
- Not every library has the same schema, mutation, transaction, nested-graph, or persistence guarantees.
- Property-query comparisons did not cover native peer vector-selection APIs.
- The native diagnostic retains an extra benchmark ID map and is not a production facade.
- Input allocation and Python/native allocator reuse affect RSS and latency even after collection.
- Nested fixture memory retains oracles/handles and a flattened comparator's containment edges; it is intentionally excluded from clean footprint conclusions.
- Snapshot peaks are cumulative and include staging; no dedicated cold-cache or disk-failure run occurred.
- The supported RAM guard did not trigger, but the host was memory-occupied and not CPU-isolated.
- Microsecond CPU accounting was too coarse; no energy-per-operation conclusion is available.
- The count microbenchmark uses native `store.stats()` for FastGraph/native, not facade `node_count`/`edge_count`; it is a count diagnostic, not public-API count latency.
- No Neo4j, Memgraph, distributed service, WAL recovery, or ACID-equivalent workload was benchmarked.

## 18. Prioritized Improvements Suggested By Measurements

These are recommendations, not changes made during the benchmark.

1. **Reduce facade materialization.** Native IDs/query results are much cheaper than hydrated handles/properties. Add projected, cursor/batch, and count-only paths without weakening detached-read guarantees.
2. **Profile rich property storage.** Rich strings/lists/dictionaries erase the sparse-memory advantage. Consider string/value sharing policies, compact typed columns, or cold property storage based on measured access patterns.
3. **Optimize traversal kernels and output layout.** Igraph remains much faster, including the predecessor-array control. Study queue/visited layout, adjacency locality, sorting, map lookups, and unnecessary result copies before promising native-library-leading speed.
4. **Separate facade read locking from write isolation.** Native same-store readers overlap, but the facade serializes them. A verified consistent-read design is needed before changing this lock; removing it blindly would trade correctness for throughput.
5. **Keep indexes selective and explicit.** Equality indexes pay off quickly for low-cardinality outputs. Range indexes are a separate missing capability. Broad queries need projection/limits more than another equality index.
6. **Replace full-store transaction clones for write-heavy use.** Empty transaction overhead is material and graph-size dependent. A journal/delta transaction model and explicit durable semantics should precede database claims.
7. **Use one native persistence representation.** Avoid native JSON -> Python object graph -> encoded snapshot -> Python parse -> native reconstruction where possible. Streaming/native codecs and bounded buffer reuse should reduce both time and peak memory.
8. **Reuse nested handles and add inexpensive selection paths.** Absolute paths are useful identities but expensive hot-loop keys at depth 256. Existing scope-handle reopening also has a fixed construction cost worth reducing.
9. **Add explicit compaction/release policy.** Clear retains useful capacity, but users need a documented way to release it without confusing logical emptiness with fresh-store memory.

## 19. Reproduce The Runs

Use an isolated environment. A source build needs Rust and a platform linker. Do not install comparator libraries into the application environment just to reproduce this report.

```powershell
python -m venv .venv-benchmark
.venv-benchmark\Scripts\python.exe -m pip install maturin==1.15.0 psutil==7.2.2 networkx==3.6.1 rustworkx==0.18.1 igraph==1.0.0 numpy==2.4.6 msgpack==1.2.3 pyyaml==6.0.3 click==8.5.0
.venv-benchmark\Scripts\maturin.exe build --release --locked --out benchmark-wheel
.venv-benchmark\Scripts\python.exe -m pip install benchmark-wheel\fastgx-3.0.0-cp310-abi3-win_amd64.whl
```

Use absolute output/scratch paths and run from the isolated environment, not a source-importing Python session. The harness checks that FastGraph comes from `site-packages`. The relative forms below work from the repository root because the controller and child processes resolve the shared paths before changing worker directories.

```powershell
.venv-benchmark\Scripts\python.exe -B benchmarks\in_depth.py --smoke --output benchmark-results\smoke --scratch benchmark-scratch
.venv-benchmark\Scripts\python.exe -B benchmarks\in_depth.py --only flat --output benchmark-results\flat --scratch benchmark-scratch
.venv-benchmark\Scripts\python.exe -B benchmarks\in_depth.py --only query,transaction,view,mutation,nested,depth,persistence,concurrency --output benchmark-results\features --scratch benchmark-scratch
.venv-benchmark\Scripts\python.exe -B benchmarks\in_depth.py --supplement --output benchmark-results\supplement --scratch benchmark-scratch
.venv-benchmark\Scripts\python.exe -B benchmarks\analyze_results.py benchmark-results\flat\results.json benchmark-results\features\results.json benchmark-results\supplement\results.json --output benchmark-results
```

For comparison with these checked-in raw files, use their engine revision, package versions, per-run harness hashes, and original commands. The final harness contains the corrected nested controls and supplements. It is not byte-identical to the initial harness, which is why manifests are preserved rather than rewritten.

The original nested fixture incorrectly timed a NetworkX no-op for parent-only traversal and imported FastGraph/native during NetworkX construction. Those measurements are superseded. Final reruns execute actual parent-only adjacency walks, target-only imports, and a leaf-start cross-scope proof. The raw history and replacement count remain visible for audit.

## 20. Bottom Line

FastGraph v3 demonstrates a real sparse-memory advantage over NetworkX, effective selective equality indexing, and functional nested graph traversal. Its public API has substantial overhead relative to the native store, rich properties need work, and mature native libraries remain stronger loading/traversal baselines.

**The evidence supports continued focused engineering, not a claim that this engine is already faster, better, and lighter than Neo4j or every native graph library.**

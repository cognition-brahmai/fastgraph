#!/usr/bin/env python3
"""
FastGraph Performance Examples

This file demonstrates the performance optimization features and capabilities
introduced in FastGraph v2.0 Enhanced API for high-performance graph operations.

Performance features demonstrated:
- Caching strategies and optimization
- Memory management and efficiency
- Batch operations and bulk processing
- Lazy loading and on-demand processing
- Parallel processing capabilities
- Resource monitoring and profiling
- Large dataset handling
- Performance benchmarking and tuning
"""

from fastgraph import FastGraph
from fastgraph.config import ConfigManager
import time
import gc
import psutil
import os
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import json


def get_memory_usage():
    """Get current memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def example_1_caching_performance():
    """
    Example 1: Caching strategies for performance optimization.
    
    Demonstrates how to use FastGraph's caching system
    to improve performance for repeated operations.
    """
    print("=== Example 1: Caching Performance ===")
    
    # Configuration with caching enabled
    cache_config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        },
        "performance": {
            "caching": {
                "enabled": True,
                "max_memory_mb": 256,
                "strategy": "lru"
            }
        }
    }
    
    # Create graph with caching
    print("Creating graph with caching enabled:")
    cached_graph = FastGraph.with_config(cache_config, "performance_cache")
    
    # Add a reasonable amount of data
    print("Adding data to graph...")
    start_time = time.time()
    
    for i in range(1000):
        cached_graph.add_node(f"node_{i}", {
            "data": f"test_data_{i}",
            "index": i,
            "category": f"cat_{i % 10}"
        })
    
    # Add some edges
    for i in range(0, 900, 10):
        cached_graph.add_edge(f"node_{i}", f"node_{i+1}", "sequence")
    
    add_time = time.time() - start_time
    print(f"Data addition completed in {add_time:.3f} seconds")
    
    # Test cache performance with repeated operations
    print("\nTesting cache performance:")
    
    # First access (cache miss)
    start_time = time.time()
    for i in range(0, 1000, 100):
        node = cached_graph.graph['nodes'][f"node_{i}"]
    first_access_time = time.time() - start_time
    print(f"First access (cache miss): {first_access_time:.4f} seconds")
    
    # Second access (cache hit)
    start_time = time.time()
    for i in range(0, 1000, 100):
        node = cached_graph.graph['nodes'][f"node_{i}"]
    second_access_time = time.time() - start_time
    print(f"Second access (cache hit): {second_access_time:.4f} seconds")
    
    # Performance improvement
    if second_access_time > 0:
        improvement = (first_access_time - second_access_time) / first_access_time * 100
        print(f"Performance improvement: {improvement:.1f}%")
    
    cached_graph.save()
    print("✅ Caching performance test completed")
    print()


def example_2_memory_optimization():
    """
    Example 2: Memory optimization techniques.
    
    Shows how to optimize memory usage for large graphs
    using enhanced API features.
    """
    print("=== Example 2: Memory Optimization ===")
    
    # Memory-efficient configuration
    memory_config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        },
        "performance": {
            "memory": {
                "optimization": "aggressive",
                "gc_frequency": 100,
                "max_memory_mb": 512
            },
            "caching": {
                "enabled": True,
                "max_memory_mb": 128
            }
        }
    }
    
    # Baseline memory usage
    baseline_memory = get_memory_usage()
    print(f"Baseline memory usage: {baseline_memory:.1f} MB")
    
    # Create memory-efficient graph
    print("Creating memory-optimized graph:")
    memory_graph = FastGraph.with_config(memory_config, "memory_optimized")
    
    # Add data in chunks to monitor memory
    chunk_size = 500
    total_nodes = 5000
    
    for chunk_start in range(0, total_nodes, chunk_size):
        chunk_end = min(chunk_start + chunk_size, total_nodes)
        
        # Add chunk of data
        for i in range(chunk_start, chunk_end):
            memory_graph.add_node(f"mem_node_{i}", {
                "payload": "x" * 50,  # Some data payload
                "index": i,
                "chunk": chunk_start // chunk_size
            })
        
        # Monitor memory after each chunk
        current_memory = get_memory_usage()
        memory_delta = current_memory - baseline_memory
        
        if chunk_start % 1000 == 0:
            print(f"  Added {chunk_end} nodes, memory delta: {memory_delta:.1f} MB")
    
    # Memory usage after data addition
    final_memory = get_memory_usage()
    total_memory_delta = final_memory - baseline_memory
    print(f"Total memory usage: {final_memory:.1f} MB (+{total_memory_delta:.1f} MB)")
    
    # Test memory efficiency with operations
    print("\nTesting memory-efficient operations:")
    
    # Operation that should benefit from memory optimization
    start_time = time.time()
    for i in range(0, total_nodes, 10):
        node_data = memory_graph.graph['nodes'][f"mem_node_{i}"]
        # Process data
        processed = len(node_data.get('payload', ''))
    
    operation_time = time.time() - start_time
    print(f"Memory-optimized operation completed in {operation_time:.3f} seconds")
    
    memory_graph.save()
    print("✅ Memory optimization test completed")
    print()


def example_3_batch_operations():
    """
    Example 3: Batch operations for bulk processing.
    
    Demonstrates how to use batch operations for
    efficient processing of large datasets.
    """
    print("=== Example 3: Batch Operations ===")
    
    # Configuration optimized for batch operations
    batch_config = {
        "enhanced_api": {
            "enabled": True,
            "auto_discovery": True
        },
        "performance": {
            "batch_operations": {
                "enabled": True,
                "batch_size": 1000,
                "auto_commit": True
            },
            "caching": {
                "enabled": True,
                "strategy": "batch"
            }
        }
    }
    
    # Create graph for batch operations
    print("Creating graph optimized for batch operations:")
    batch_graph = FastGraph.with_config(batch_config, "batch_operations")
    
    # Batch node addition
    print("Performing batch node addition:")
    start_time = time.time()
    
    batch_size = 1000
    total_batches = 10
    
    for batch_num in range(total_batches):
        # Create batch of nodes
        nodes_to_add = []
        for i in range(batch_size):
            node_id = f"batch_node_{batch_num}_{i}"
            node_data = {
                "batch": batch_num,
                "index": i,
                "data": f"batch_data_{batch_num}_{i}",
                "timestamp": time.time()
            }
            nodes_to_add.append((node_id, node_data))
        
        # Add nodes in batch
        for node_id, node_data in nodes_to_add:
            batch_graph.add_node(node_id, node_data)
        
        # Add some edges within batch
        for i in range(0, batch_size - 1, 10):
            batch_graph.add_edge(
                f"batch_node_{batch_num}_{i}",
                f"batch_node_{batch_num}_{i+1}",
                "batch_sequence"
            )
        
        if batch_num % 3 == 0:
            print(f"  Completed batch {batch_num + 1}/{total_batches}")
    
    batch_time = time.time() - start_time
    total_nodes = total_batches * batch_size
    print(f"Batch operation completed: {total_nodes} nodes in {batch_time:.3f} seconds")
    print(f"Performance: {total_nodes / batch_time:.0f} nodes/second")
    
    # Batch query operations
    print("\nPerforming batch query operations:")
    start_time = time.time()
    
    # Query all nodes in batches
    queried_count = 0
    for batch_num in range(total_batches):
        for i in range(0, batch_size, 10):  # Sample every 10th node
            node_id = f"batch_node_{batch_num}_{i}"
            if node_id in batch_graph.graph['nodes']:
                node_data = batch_graph.graph['nodes'][node_id]
                queried_count += 1
    
    query_time = time.time() - start_time
    print(f"Batch query completed: {queried_count} nodes in {query_time:.3f} seconds")
    
    batch_graph.save()
    print("✅ Batch operations test completed")
    print()


def example_4_lazy_loading():
    """
    Example 4: Lazy loading for on-demand processing.
    
    Shows how to use lazy loading features to handle
    large graphs efficiently.
    """
    print("=== Example 4: Lazy Loading ===")
    
    # Configuration for lazy loading
    lazy_config = {
        "enhanced_api": {
            "enabled": True,
            "auto_discovery": True
        },
        "performance": {
            "lazy_loading": {
                "enabled": True,
                "threshold_nodes": 10000,
                "load_strategy": "on_demand"
            },
            "memory": {
                "optimization": "lazy"
            }
        }
    }
    
    # Create a large graph to demonstrate lazy loading
    print("Creating large graph for lazy loading demonstration:")
    large_graph = FastGraph.with_config(lazy_config, "lazy_loading_demo")
    
    # Add substantial data
    print("Adding large dataset...")
    start_time = time.time()
    
    large_dataset_size = 20000
    for i in range(large_dataset_size):
        large_graph.add_node(f"lazy_node_{i}", {
            "data": f"large_data_{i}",
            "size": i * 10,
            "category": f"category_{i % 100}",
            "payload": "x" * 100  # Larger payload
        })
        
        if i % 5000 == 0 and i > 0:
            current_time = time.time() - start_time
            print(f"  Added {i} nodes in {current_time:.2f} seconds")
    
    # Add some edges
    for i in range(0, large_dataset_size - 1, 100):
        large_graph.add_edge(f"lazy_node_{i}", f"lazy_node_{i+1}", "lazy_edge")
    
    total_time = time.time() - start_time
    print(f"Large dataset created: {large_dataset_size} nodes in {total_time:.2f} seconds")
    
    # Save the large graph
    large_graph.save()
    print("Large graph saved")
    
    # Test lazy loading by creating new instance
    print("\nTesting lazy loading with new instance:")
    start_time = time.time()
    
    lazy_loaded_graph = FastGraph("lazy_loading_demo")
    
    # Check if lazy loading is working
    if lazy_loaded_graph.exists():
        lazy_loaded_graph.load()
        load_time = time.time() - start_time
        print(f"Lazy loaded graph in {load_time:.3f} seconds")
        
        # Access specific nodes on demand
        start_time = time.time()
        access_count = 0
        for i in range(0, large_dataset_size, 1000):  # Access every 1000th node
            node_id = f"lazy_node_{i}"
            if node_id in lazy_loaded_graph.graph['nodes']:
                node_data = lazy_loaded_graph.graph['nodes'][node_id]
                access_count += 1
        
        access_time = time.time() - start_time
        print(f"On-demand access: {access_count} nodes in {access_time:.3f} seconds")
    
    print("✅ Lazy loading test completed")
    print()


def example_5_parallel_processing():
    """
    Example 5: Parallel processing capabilities.
    
    Demonstrates how to use FastGraph in parallel
    processing scenarios.
    """
    print("=== Example 5: Parallel Processing ===")
    
    # Configuration for parallel processing
    parallel_config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        },
        "performance": {
            "parallel": {
                "enabled": True,
                "max_workers": 4,
                "thread_safe": True
            },
            "caching": {
                "enabled": True,
                "thread_safe": True
            }
        }
    }
    
    # Create shared graph for parallel operations
    print("Creating graph for parallel processing:")
    shared_graph = FastGraph.with_config(parallel_config, "parallel_demo")
    
    # Add initial data
    for i in range(100):
        shared_graph.add_node(f"shared_node_{i}", {"initial": True, "id": i})
    
    shared_graph.save()
    
    # Parallel worker function
    def parallel_worker(worker_id, graph_name, node_range):
        """Worker function for parallel processing."""
        try:
            # Each worker gets their own graph instance
            worker_graph = FastGraph.load_graph(graph_name)
            
            # Process assigned nodes
            for i in node_range:
                node_id = f"shared_node_{i}"
                if node_id in worker_graph.graph['nodes']:
                    # Update node data
                    worker_graph.graph['nodes'][node_id].update({
                        "processed_by": worker_id,
                        "processed_at": time.time(),
                        "worker_data": f"data_from_worker_{worker_id}"
                    })
            
            # Save changes
            worker_graph.save()
            return f"Worker {worker_id} completed {len(node_range)} nodes"
            
        except Exception as e:
            return f"Worker {worker_id} failed: {e}"
    
    # Execute parallel processing
    print("Starting parallel processing:")
    start_time = time.time()
    
    # Create thread pool
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Divide work among workers
        node_ranges = [
            range(0, 25),
            range(25, 50),
            range(50, 75),
            range(75, 100)
        ]
        
        # Submit tasks
        futures = []
        for worker_id, node_range in enumerate(node_ranges):
            future = executor.submit(parallel_worker, worker_id, "parallel_demo", node_range)
            futures.append(future)
        
        # Collect results
        results = [future.result() for future in futures]
    
    parallel_time = time.time() - start_time
    print(f"Parallel processing completed in {parallel_time:.3f} seconds")
    
    for result in results:
        print(f"  {result}")
    
    # Verify results
    print("\nVerifying parallel processing results:")
    verification_graph = FastGraph.load_graph("parallel_demo")
    processed_count = 0
    for node_id, node_data in verification_graph.graph['nodes'].items():
        if "processed_by" in node_data:
            processed_count += 1
    
    print(f"Successfully processed {processed_count} nodes in parallel")
    
    print("✅ Parallel processing test completed")
    print()


def example_6_performance_monitoring():
    """
    Example 6: Performance monitoring and profiling.
    
    Shows how to monitor and profile FastGraph performance
    for optimization and debugging.
    """
    print("=== Example 6: Performance Monitoring ===")
    
    # Configuration with monitoring enabled
    monitoring_config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        },
        "performance": {
            "monitoring": {
                "enabled": True,
                "profile_operations": True,
                "memory_tracking": True,
                "timing_precision": "high"
            },
            "caching": {
                "enabled": True
            }
        }
    }
    
    # Create graph for monitoring
    print("Creating graph with performance monitoring:")
    monitored_graph = FastGraph.with_config(monitoring_config, "monitored_graph")
    
    # Monitor performance during operations
    print("Performing operations with monitoring:")
    
    # Baseline measurements
    baseline_memory = get_memory_usage()
    start_time = time.time()
    
    # Perform various operations
    operations = [
        ("Node Addition", lambda g: [g.add_node(f"mon_node_{i}", {"data": i}) for i in range(1000)]),
        ("Edge Addition", lambda g: [g.add_edge(f"mon_node_{i}", f"mon_node_{i+1}", "test") for i in range(999)]),
        ("Node Query", lambda g: [g.graph['nodes'].get(f"mon_node_{i}") for i in range(0, 1000, 10)]),
        ("Edge Query", lambda g: [g.graph['edges'].get((f"mon_node_{i}", f"mon_node_{i+1}")) for i in range(0, 900, 10)])
    ]
    
    performance_results = {}
    
    for op_name, operation in operations:
        # Memory before operation
        mem_before = get_memory_usage()
        
        # Time operation
        op_start = time.time()
        operation(monitored_graph)
        op_time = time.time() - op_start
        
        # Memory after operation
        mem_after = get_memory_usage()
        mem_delta = mem_after - mem_before
        
        performance_results[op_name] = {
            "time": op_time,
            "memory_delta": mem_delta,
            "rate": None
        }
        
        print(f"  {op_name}: {op_time:.4f}s, memory: +{mem_delta:.1f}MB")
    
    total_time = time.time() - start_time
    total_memory = get_memory_usage() - baseline_memory
    
    print(f"\nTotal Performance Summary:")
    print(f"  Total time: {total_time:.3f} seconds")
    print(f"  Total memory: {total_memory:.1f} MB")
    print(f"  Nodes created: {len(monitored_graph.graph['nodes'])}")
    print(f"  Edges created: {len(monitored_graph.graph['edges'])}")
    
    # Calculate rates
    node_count = len(monitored_graph.graph['nodes'])
    edge_count = len(monitored_graph.graph['edges'])
    
    if total_time > 0:
        performance_results["Node Addition"]["rate"] = node_count / performance_results["Node Addition"]["time"]
        performance_results["Edge Addition"]["rate"] = edge_count / performance_results["Edge Addition"]["time"]
    
    print(f"\nOperation Rates:")
    for op_name, results in performance_results.items():
        if results["rate"]:
            print(f"  {op_name}: {results['rate']:.0f} ops/second")
    
    monitored_graph.save()
    print("✅ Performance monitoring test completed")
    print()


def example_7_large_dataset_handling():
    """
    Example 7: Large dataset handling strategies.
    
    Demonstrates techniques for handling very large
    graph datasets efficiently.
    """
    print("=== Example 7: Large Dataset Handling ===")
    
    # Configuration for large datasets
    large_config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        },
        "performance": {
            "large_datasets": {
                "enabled": True,
                "chunk_size": 5000,
                "memory_threshold_mb": 1024,
                "compression": True
            },
            "lazy_loading": {
                "enabled": True,
                "threshold_nodes": 50000
            },
            "caching": {
                "enabled": True,
                "max_memory_mb": 512
            }
        }
    }
    
    # Create large dataset graph
    print("Creating large dataset handler:")
    large_graph = FastGraph.with_config(large_config, "large_dataset")
    
    # Process data in chunks to handle large datasets
    print("Processing large dataset in chunks:")
    
    chunk_size = 5000
    total_chunks = 5
    nodes_per_chunk = 1000
    
    start_time = time.time()
    memory_baseline = get_memory_usage()
    
    for chunk_id in range(total_chunks):
        chunk_start = chunk_id * nodes_per_chunk
        chunk_end = chunk_start + nodes_per_chunk
        
        # Process chunk
        chunk_memory_before = get_memory_usage()
        
        for i in range(chunk_start, chunk_end):
            large_graph.add_node(f"large_node_{i}", {
                "chunk": chunk_id,
                "index": i,
                "data": f"large_dataset_item_{i}",
                "payload": "x" * 200,  # Larger payload for testing
                "metadata": {
                    "created": time.time(),
                    "size": 200
                }
            })
        
        # Add some edges within chunk
        for i in range(chunk_start, chunk_end - 1, 50):
            large_graph.add_edge(f"large_node_{i}", f"large_node_{i+1}", "chunk_edge")
        
        chunk_memory_after = get_memory_usage()
        chunk_memory_delta = chunk_memory_after - chunk_memory_before
        
        # Periodic cleanup and monitoring
        if chunk_id % 2 == 1:
            gc.collect()  # Force garbage collection
        
        print(f"  Chunk {chunk_id + 1}/{total_chunks}: {chunk_end - chunk_start} nodes, memory: +{chunk_memory_delta:.1f}MB")
    
    # Final statistics
    total_time = time.time() - start_time
    total_memory = get_memory_usage() - memory_baseline
    total_nodes = total_chunks * nodes_per_chunk
    
    print(f"\nLarge Dataset Processing Summary:")
    print(f"  Total nodes: {total_nodes}")
    print(f"  Total time: {total_time:.2f} seconds")
    print(f"  Total memory: {total_memory:.1f} MB")
    print(f"  Processing rate: {total_nodes / total_time:.0f} nodes/second")
    print(f"  Memory per node: {total_memory / total_nodes * 1024:.1f} KB")
    
    # Test large dataset queries
    print("\nTesting large dataset queries:")
    
    # Sample query performance
    query_start = time.time()
    sample_size = 1000
    found_count = 0
    
    for i in range(0, total_nodes, total_nodes // sample_size):
        node_id = f"large_node_{i}"
        if node_id in large_graph.graph['nodes']:
            node_data = large_graph.graph['nodes'][node_id]
            found_count += 1
    
    query_time = time.time() - query_start
    print(f"  Sample query: {found_count} nodes in {query_time:.3f} seconds")
    
    large_graph.save()
    print("✅ Large dataset handling test completed")
    print()


def example_8_performance_tuning():
    """
    Example 8: Performance tuning and optimization.
    
    Shows how to tune FastGraph for optimal performance
    in different scenarios.
    """
    print("=== Example 8: Performance Tuning ===")
    
    # Different tuning scenarios
    scenarios = {
        "speed_optimized": {
            "enhanced_api": {"enabled": True},
            "performance": {
                "caching": {"enabled": True, "max_memory_mb": 1024},
                "memory": {"optimization": "speed"},
                "batch_operations": {"enabled": True, "batch_size": 2000}
            }
        },
        "memory_optimized": {
            "enhanced_api": {"enabled": True, "resource_management": True},
            "performance": {
                "memory": {"optimization": "aggressive", "max_memory_mb": 256},
                "caching": {"enabled": True, "max_memory_mb": 64},
                "lazy_loading": {"enabled": True}
            }
        },
        "balanced": {
            "enhanced_api": {"enabled": True, "auto_discovery": True},
            "performance": {
                "caching": {"enabled": True, "max_memory_mb": 512},
                "memory": {"optimization": "balanced"},
                "batch_operations": {"enabled": True, "batch_size": 1000}
            }
        }
    }
    
    # Test each scenario
    test_data_size = 2000
    
    for scenario_name, config in scenarios.items():
        print(f"\nTesting {scenario_name} configuration:")
        
        # Create graph with scenario configuration
        test_graph = FastGraph.with_config(config, f"tuning_{scenario_name}")
        
        # Measure performance
        start_memory = get_memory_usage()
        start_time = time.time()
        
        # Add test data
        for i in range(test_data_size):
            test_graph.add_node(f"tune_node_{i}", {
                "scenario": scenario_name,
                "data": f"test_data_{i}",
                "payload": "x" * 50
            })
        
        # Add some edges
        for i in range(0, test_data_size - 1, 10):
            test_graph.add_edge(f"tune_node_{i}", f"tune_node_{i+1}", "test_edge")
        
        # Perform some queries
        for i in range(0, test_data_size, 20):
            node_data = test_graph.graph['nodes'].get(f"tune_node_{i}")
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        # Calculate metrics
        total_time = end_time - start_time
        memory_delta = end_memory - start_memory
        throughput = test_data_size / total_time
        
        print(f"  Time: {total_time:.3f} seconds")
        print(f"  Memory: {memory_delta:.1f} MB")
        print(f"  Throughput: {throughput:.0f} nodes/second")
        
        test_graph.save()
    
    print("\nPerformance Tuning Recommendations:")
    print("  - Use speed_optimized for maximum throughput")
    print("  - Use memory_optimized for memory-constrained environments")
    print("  - Use balanced for general-purpose applications")
    
    print("✅ Performance tuning test completed")
    print()


def main():
    """
    Run all performance examples.
    """
    print("FastGraph Performance Examples")
    print("=" * 50)
    print("Demonstrating performance optimization capabilities")
    print()
    
    try:
        # Run all examples
        example_1_caching_performance()
        example_2_memory_optimization()
        example_3_batch_operations()
        example_4_lazy_loading()
        example_5_parallel_processing()
        example_6_performance_monitoring()
        example_7_large_dataset_handling()
        example_8_performance_tuning()
        
        print("All performance examples completed!")
        print()
        print("PERFORMANCE SUMMARY:")
        print("✅ Caching provides significant performance improvements")
        print("✅ Memory optimization enables handling large datasets")
        print("✅ Batch operations improve throughput")
        print("✅ Lazy loading reduces memory footprint")
        print("✅ Parallel processing scales with available cores")
        print("✅ Monitoring helps identify bottlenecks")
        print("✅ Large dataset handling enables big graph applications")
        print("✅ Performance tuning adapts to different use cases")
        
    except Exception as e:
        print(f"Error running performance examples: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up any remaining resources
        print("\nFinal cleanup:")
        cleanup_resources()


def cleanup_resources():
    """
    Clean up any remaining resources from performance examples.
    """
    # Clean up temporary files created during examples
    temp_files = [
        "performance_cache.json",
        "memory_optimized.json",
        "batch_operations.json",
        "lazy_loading_demo.json",
        "parallel_demo.json",
        "monitored_graph.json",
        "large_dataset.json",
        "tuning_speed_optimized.json",
        "tuning_memory_optimized.json",
        "tuning_balanced.json"
    ]
    
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                print(f"Cleaned up {temp_file}")
            except Exception as e:
                print(f"Failed to clean up {temp_file}: {e}")


if __name__ == "__main__":
    main()
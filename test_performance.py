"""
Performance regression tests for FastGraph.

This module contains tests to ensure that performance does not
regress as new features are added and the system evolves.
"""

import time
import threading
import tempfile
import pytest
import psutil
import gc
from pathlib import Path
from unittest.mock import Mock
import sys

# Add the fastgraph package to the path
sys.path.insert(0, '.')

from fastgraph.core.graph import FastGraph
from fastgraph.utils.path_resolver import PathResolver
from fastgraph.utils.resource_manager import ResourceManager


class TestPerformanceBenchmarks:
    """Performance benchmark tests with regression detection."""
    
    def setup_method(self):
        """Set up performance test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss
    
    def teardown_method(self):
        """Clean up after performance tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        gc.collect()  # Force garbage collection
    
    def test_node_operations_performance(self):
        """Test node addition and retrieval performance."""
        config = {
            "enhanced_api": {"enabled": True},
            "memory": {"query_cache_size": 0}  # Disable cache for pure performance test
        }
        
        graph = FastGraph(name="perf_test", config=config)
        
        # Test single node additions
        node_count = 10000
        start_time = time.time()
        
        for i in range(node_count):
            graph.add_node(f"node_{i}", 
                         name=f"Node {i}",
                         value=i,
                         category=f"cat_{i % 10}")
        
        single_add_time = time.time() - start_time
        
        # Test batch node additions
        graph2 = FastGraph(name="perf_test_batch", config=config)
        
        start_time = time.time()
        batch = []
        batch_size = 100
        
        for i in range(node_count):
            batch.append((f"node_{i}", {
                "name": f"Node {i}",
                "value": i,
                "category": f"cat_{i % 10}"
            }))
            
            if len(batch) >= batch_size:
                graph2.add_nodes_batch(batch)
                batch = []
        
        if batch:
            graph2.add_nodes_batch(batch)
        
        batch_add_time = time.time() - start_time
        
        # Test node retrieval performance
        start_time = time.time()
        for i in range(node_count):
            node = graph.get_node(f"node_{i}")
            assert node is not None
        retrieval_time = time.time() - start_time
        
        # Performance assertions
        # These are baseline expectations - adjust as needed
        assert single_add_time < 2.0, f"Single node addition too slow: {single_add_time:.3f}s"
        assert batch_add_time < 0.5, f"Batch node addition too slow: {batch_add_time:.3f}s"
        assert retrieval_time < 1.0, f"Node retrieval too slow: {retrieval_time:.3f}s"
        
        # Batch should be faster than single
        assert batch_add_time < single_add_time, "Batch operations should be faster than single operations"
        
        # Verify data integrity
        assert len(graph) == node_count
        assert len(graph2) == node_count
    
    def test_edge_operations_performance(self):
        """Test edge addition and retrieval performance."""
        config = {
            "enhanced_api": {"enabled": True},
            "memory": {"query_cache_size": 0}
        }
        
        graph = FastGraph(name="edge_perf_test", config=config)
        
        # Add nodes first
        node_count = 5000
        for i in range(node_count):
            graph.add_node(f"node_{i}")
        
        # Test single edge additions
        edge_count = 10000
        start_time = time.time()
        
        for i in range(edge_count):
            src = f"node_{i % node_count}"
            dst = f"node_{(i + 1) % node_count}"
            graph.add_edge(src, dst, f"relation_{i % 5}", weight=i)
        
        single_edge_time = time.time() - start_time
        
        # Test batch edge additions
        graph2 = FastGraph(name="edge_perf_test_batch", config=config)
        for i in range(node_count):
            graph2.add_node(f"node_{i}")
        
        start_time = time.time()
        edge_batch = []
        batch_size = 100
        
        for i in range(edge_count):
            src = f"node_{i % node_count}"
            dst = f"node_{(i + 1) % node_count}"
            edge_batch.append((src, dst, f"relation_{i % 5}", {"weight": i}))
            
            if len(edge_batch) >= batch_size:
                graph2.add_edges_batch(edge_batch)
                edge_batch = []
        
        if edge_batch:
            graph2.add_edges_batch(edge_batch)
        
        batch_edge_time = time.time() - start_time
        
        # Test edge retrieval performance
        start_time = time.time()
        for i in range(0, edge_count, 10):  # Sample 10% of edges
            src = f"node_{i % node_count}"
            dst = f"node_{(i + 1) % node_count}"
            edge = graph.get_edge(src, dst, f"relation_{i % 5}")
            assert edge is not None
        edge_retrieval_time = time.time() - start_time
        
        # Performance assertions
        assert single_edge_time < 3.0, f"Single edge addition too slow: {single_edge_time:.3f}s"
        assert batch_edge_time < 1.0, f"Batch edge addition too slow: {batch_edge_time:.3f}s"
        assert edge_retrieval_time < 0.5, f"Edge retrieval too slow: {edge_retrieval_time:.3f}s"
        
        # Batch should be faster
        assert batch_edge_time < single_edge_time, "Batch edge operations should be faster"
    
    def test_query_performance(self):
        """Test query performance with various data sizes."""
        config = {
            "enhanced_api": {"enabled": True},
            "memory": {"query_cache_size": 128}
        }
        
        graph = FastGraph(name="query_perf_test", config=config)
        
        # Add test data
        node_count = 10000
        categories = ["A", "B", "C", "D", "E"]
        
        for i in range(node_count):
            graph.add_node(f"node_{i}",
                         category=categories[i % len(categories)],
                         value=i,
                         active=i % 2 == 0,
                         priority=i % 10)
        
        # Test various query types
        queries = [
            # Simple attribute query
            lambda g: g.find_nodes(category="A"),
            
            # Range query
            lambda g: g.find_nodes(value__gt=5000),
            
            # Multiple attributes
            lambda g: g.find_nodes(category="B", active=True),
            
            # Complex query
            lambda g: g.find_nodes(category="C", priority__lt=5, active=True)
        ]
        
        # First run (cache misses)
        first_run_times = []
        for query_func in queries:
            start_time = time.time()
            results = query_func(graph)
            query_time = time.time() - start_time
            first_run_times.append(query_time)
            assert len(results) > 0  # Should find something
        
        # Second run (should hit cache)
        second_run_times = []
        for query_func in queries:
            start_time = time.time()
            results = query_func(graph)
            query_time = time.time() - start_time
            second_run_times.append(query_time)
            assert len(results) > 0
        
        # Cache should improve performance
        for i, (first, second) in enumerate(zip(first_run_times, second_run_times)):
            assert second <= first, f"Query {i} should be faster or equal on cache hit"
        
        # Overall performance should be reasonable
        avg_first_run = sum(first_run_times) / len(first_run_times)
        avg_second_run = sum(second_run_times) / len(second_run_times)
        
        assert avg_first_run < 0.1, f"Average query time too slow: {avg_first_run:.4f}s"
        assert avg_second_run < 0.01, f"Cached query time too slow: {avg_second_run:.4f}s"
    
    def test_persistence_performance(self):
        """Test save/load performance with different data sizes."""
        config = {"enhanced_api": {"enabled": True}}
        
        data_sizes = [1000, 5000, 10000]
        formats = ["json", "msgpack", "pickle"]
        
        for size in data_sizes:
            for fmt in formats:
                graph = FastGraph(name=f"perf_persistence_{size}_{fmt}", config=config)
                
                # Add test data
                for i in range(size):
                    graph.add_node(f"node_{i}",
                                 name=f"Node {i}",
                                 data="x" * 50,  # Some payload
                                 value=i)
                
                # Add some edges
                for i in range(0, size - 1, 10):
                    graph.add_edge(f"node_{i}", f"node_{i+1}", "sequence")
                
                # Test save performance
                temp_path = Path(self.temp_dir) / f"test_{size}.{fmt}"
                start_time = time.time()
                saved_path = graph.save(temp_path, format=fmt)
                save_time = time.time() - start_time
                
                # Test load performance
                graph2 = FastGraph(config=config)
                start_time = time.time()
                graph2.load(saved_path)
                load_time = time.time() - start_time
                
                # Performance assertions (scaled by data size)
                save_time_per_node = save_time / size
                load_time_per_node = load_time / size
                
                assert save_time_per_node < 0.001, f"Save too slow for {fmt}: {save_time_per_node:.6f}s per node"
                assert load_time_per_node < 0.001, f"Load too slow for {fmt}: {load_time_per_node:.6f}s per node"
                
                # Verify data integrity
                assert len(graph2) == size
                assert len(graph2._edges) > 0
    
    def test_memory_usage_scaling(self):
        """Test memory usage scales linearly with data size."""
        config = {"enhanced_api": {"enabled": True}}
        
        data_sizes = [1000, 2000, 5000, 10000]
        memory_measurements = []
        
        for size in data_sizes:
            # Force garbage collection before measurement
            gc.collect()
            
            initial_memory = self.process.memory_info().rss
            
            graph = FastGraph(name=f"memory_test_{size}", config=config)
            
            # Add data
            for i in range(size):
                graph.add_node(f"node_{i}",
                             data="x" * 100,  # 100 bytes per node
                             value=i)
            
            final_memory = self.process.memory_info().rss
            memory_used = final_memory - initial_memory
            memory_per_node = memory_used / size
            
            memory_measurements.append((size, memory_used, memory_per_node))
            
            # Clean up
            graph.cleanup()
            del graph
            gc.collect()
        
        # Memory usage should scale reasonably
        # Allow for some overhead but should be roughly linear
        for size, total_memory, per_node in memory_measurements:
            # Each node should use reasonable memory (less than 1KB including overhead)
            assert per_node < 1024, f"Memory per node too high: {per_node} bytes for {size} nodes"
        
        # Check linear scaling (correlation)
        if len(memory_measurements) >= 2:
            # Simple linear regression check
            sizes = [m[0] for m in memory_measurements]
            memories = [m[1] for m in memory_measurements]
            
            # Calculate correlation (simplified)
            avg_size = sum(sizes) / len(sizes)
            avg_mem = sum(memories) / len(memories)
            
            numerator = sum((s - avg_size) * (m - avg_mem) for s, m in zip(sizes, memories))
            size_variance = sum((s - avg_size) ** 2 for s in sizes)
            
            if size_variance > 0:
                correlation = numerator / size_variance
                # Positive correlation indicates linear scaling
                assert correlation > 0, "Memory usage should scale with data size"


class TestConcurrencyPerformance:
    """Performance tests for concurrent operations."""
    
    def test_concurrent_operations_performance(self):
        """Test performance under concurrent load."""
        config = {
            "enhanced_api": {"enabled": True},
            "memory": {"query_cache_size": 64}
        }
        
        graph = FastGraph(name="concurrent_perf_test", config=config)
        
        # Add initial data
        for i in range(1000):
            graph.add_node(f"base_node_{i}", category=f"cat_{i % 5}")
        
        operation_times = []
        errors = []
        
        def worker_operation(worker_id, operation_count):
            """Worker function for concurrent operations."""
            try:
                start_time = time.time()
                
                for i in range(operation_count):
                    # Mix of operations
                    if i % 4 == 0:
                        # Add nodes
                        graph.add_node(f"worker_{worker_id}_node_{i}",
                                     category=f"cat_{i % 5}")
                    elif i % 4 == 1:
                        # Add edges
                        try:
                            graph.add_edge(f"base_node_{i % 1000}",
                                         f"worker_{worker_id}_node_{i}",
                                         "worker_relation")
                        except Exception:
                            pass  # Node might not exist yet
                    elif i % 4 == 2:
                        # Query operations
                        graph.find_nodes(category=f"cat_{i % 5}")
                    else:
                        # Get operations
                        graph.get_node(f"base_node_{i % 1000}")
                
                end_time = time.time()
                operation_times.append(end_time - start_time)
                
            except Exception as e:
                errors.append(str(e))
        
        # Run concurrent workers
        worker_count = 5
        operations_per_worker = 200
        
        threads = []
        start_time = time.time()
        
        for worker_id in range(worker_count):
            t = threading.Thread(target=worker_operation,
                               args=(worker_id, operations_per_worker))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        total_time = time.time() - start_time
        
        # Performance assertions
        assert len(errors) == 0, f"Concurrent operations had errors: {errors}"
        assert len(operation_times) == worker_count
        
        avg_worker_time = sum(operation_times) / len(operation_times)
        total_operations = worker_count * operations_per_worker
        ops_per_second = total_operations / total_time
        
        # Should achieve reasonable throughput
        assert ops_per_second > 100, f"Concurrent operations too slow: {ops_per_second:.1f} ops/sec"
        assert avg_worker_time < 5.0, f"Worker average time too high: {avg_worker_time:.3f}s"
    
    def test_resource_manager_performance(self):
        """Test resource manager performance under load."""
        config = {
            "enhanced_api": {"enabled": True},
            "resource_management": {
                "max_open_graphs": 50,
                "auto_cleanup": False
            }
        }
        
        # Test graph registration/unregistration performance
        registration_times = []
        
        for i in range(100):
            start_time = time.time()
            
            graph = FastGraph(name=f"perf_test_{i}", config=config)
            graph.add_node("test", value=i)
            
            # Register and immediately unregister
            graph.cleanup()
            
            end_time = time.time()
            registration_times.append(end_time - start_time)
        
        avg_registration_time = sum(registration_times) / len(registration_times)
        
        # Registration should be fast
        assert avg_registration_time < 0.01, f"Graph registration too slow: {avg_registration_time:.4f}s"


class TestScalabilityLimits:
    """Test scalability limits and behavior."""
    
    def test_large_graph_scalability(self):
        """Test behavior with large graphs."""
        config = {
            "enhanced_api": {"enabled": True},
            "memory": {"query_cache_size": 256}
        }
        
        graph = FastGraph(name="scalability_test", config=config)
        
        # Test with increasing data sizes
        sizes = [1000, 10000, 50000]
        
        for size in sizes:
            start_time = time.time()
            
            # Add nodes
            for i in range(size):
                graph.add_node(f"scale_node_{i}",
                             name=f"Node {i}",
                             category=f"cat_{i % 20}",
                             value=i,
                             data="x" * 10)
            
            add_time = time.time() - start_time
            
            # Test query performance
            start_time = time.time()
            results = graph.find_nodes(category="cat_5")
            query_time = time.time() - start_time
            
            # Performance should scale reasonably
            add_time_per_node = add_time / size
            
            # Allow for some degradation but not exponential
            assert add_time_per_node < 0.001, f"Node addition too slow at scale {size}: {add_time_per_node:.6f}s per node"
            assert query_time < 1.0, f"Query too slow at scale {size}: {query_time:.3f}s"
            
            # Verify results
            expected_count = size // 20  # One category out of 20
            assert len(results) == expected_count
    
    def test_memory_efficiency(self):
        """Test memory efficiency with various data patterns."""
        config = {"enhanced_api": {"enabled": True}}
        
        # Test different data patterns
        patterns = [
            # Many small nodes
            ("small_nodes", 10000, lambda i: {"value": i}),
            
            # Few large nodes
            ("large_nodes", 100, lambda i: {"data": "x" * 1000, "value": i}),
            
            # Mixed attributes
            ("mixed_nodes", 1000, lambda i: {
                "name": f"Node {i}",
                "category": f"cat_{i % 10}",
                "active": i % 2 == 0,
                "metadata": {"key": f"value_{i}", "nested": {"deep": i}}
            })
        ]
        
        process = psutil.Process()
        
        for pattern_name, count, data_func in patterns:
            gc.collect()
            initial_memory = process.memory_info().rss
            
            graph = FastGraph(name=f"memory_{pattern_name}", config=config)
            
            # Add data with pattern
            for i in range(count):
                graph.add_node(f"node_{i}", **data_func(i))
            
            final_memory = process.memory_info().rss
            memory_used = final_memory - initial_memory
            memory_per_node = memory_used / count
            
            # Memory efficiency assertions
            assert memory_per_node < 2048, f"Memory per node too high for {pattern_name}: {memory_per_node} bytes"
            
            # Cleanup
            graph.cleanup()
            del graph
            gc.collect()


class TestRegressionDetection:
    """Detect performance regressions compared to baselines."""
    
    def test_performance_regression_detection(self):
        """Test for performance regressions using baselines."""
        # These baselines should be updated as the system evolves
        # They represent the expected minimum performance
        
        baselines = {
            "node_addition_single": 0.0001,  # seconds per node
            "node_addition_batch": 0.00001,  # seconds per node
            "edge_addition_single": 0.0001,  # seconds per edge
            "edge_addition_batch": 0.00001,  # seconds per edge
            "node_retrieval": 0.00001,        # seconds per node
            "edge_retrieval": 0.00001,        # seconds per edge
            "query_simple": 0.001,           # seconds for simple query
            "query_complex": 0.01,           # seconds for complex query
            "save_per_node": 0.00001,        # seconds per node
            "load_per_node": 0.00001,        # seconds per node
        }
        
        config = {"enhanced_api": {"enabled": True}}
        
        # Test node addition performance
        graph = FastGraph(name="regression_test", config=config)
        
        # Single node addition
        start_time = time.time()
        for i in range(1000):
            graph.add_node(f"node_{i}", value=i)
        single_time = (time.time() - start_time) / 1000
        
        # Batch node addition
        graph2 = FastGraph(name="regression_test_batch", config=config)
        batch = [(f"node_{i}", {"value": i}) for i in range(1000)]
        start_time = time.time()
        graph2.add_nodes_batch(batch)
        batch_time = (time.time() - start_time) / 1000
        
        # Node retrieval
        start_time = time.time()
        for i in range(1000):
            graph.get_node(f"node_{i}")
        retrieval_time = (time.time() - start_time) / 1000
        
        # Simple query
        start_time = time.time()
        graph.find_nodes(value__gt=500)
        query_time = time.time() - start_time
        
        # Check against baselines
        assert single_time <= baselines["node_addition_single"], f"Node addition regression: {single_time:.6f} > {baselines['node_addition_single']}"
        assert batch_time <= baselines["node_addition_batch"], f"Batch node addition regression: {batch_time:.6f} > {baselines['node_addition_batch']}"
        assert retrieval_time <= baselines["node_retrieval"], f"Node retrieval regression: {retrieval_time:.6f} > {baselines['node_retrieval']}"
        assert query_time <= baselines["query_simple"], f"Simple query regression: {query_time:.6f} > {baselines['query_simple']}"
        
        # Test persistence performance
        temp_path = Path(self.temp_dir) / "regression_test.msgpack"
        start_time = time.time()
        graph.save(temp_path)
        save_time = (time.time() - start_time) / 1000
        
        graph3 = FastGraph(config=config)
        start_time = time.time()
        graph3.load(temp_path)
        load_time = (time.time() - start_time) / 1000
        
        assert save_time <= baselines["save_per_node"], f"Save performance regression: {save_time:.6f} > {baselines['save_per_node']}"
        assert load_time <= baselines["load_per_node"], f"Load performance regression: {load_time:.6f} > {baselines['load_per_node']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
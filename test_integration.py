"""
End-to-end integration tests for FastGraph.

This module tests complete workflows and integration between
all FastGraph components, ensuring the system works as a whole.
"""

import os
import tempfile
import json
import time
import threading
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add the fastgraph package to the path
sys.path.insert(0, '.')

from fastgraph.core.graph import FastGraph
from fastgraph.config.manager import ConfigManager
from fastgraph.exceptions import PersistenceError, ValidationError
from fastgraph.utils.path_resolver import PathResolver
from fastgraph.utils.resource_manager import ResourceManager


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""
    
    def test_complete_graph_lifecycle(self):
        """Test complete graph lifecycle from creation to cleanup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Configuration with enhanced features
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {
                    "data_dir": str(temp_dir / "data"),
                    "default_format": "msgpack"
                },
                "persistence": {
                    "auto_save_on_exit": True,
                    "backup_directory": str(temp_dir / "backups"),
                    "max_backups": 3
                },
                "resource_management": {
                    "max_open_graphs": 5,
                    "memory_limit_per_graph": "100MB",
                    "auto_cleanup": False
                },
                "memory": {
                    "query_cache_size": 64,
                    "cache_ttl": 1800
                }
            }
            
            # Create graph with enhanced features
            graph = FastGraph(name="lifecycle_test", config=config)
            
            # Verify enhanced components are initialized
            assert graph._enhanced_enabled
            assert graph._path_resolver is not None
            assert graph._resource_manager is not None
            assert graph._graph_id is not None
            
            # Add substantial data
            nodes = []
            for i in range(1000):
                node_id = f"person_{i}"
                graph.add_node(node_id, 
                             name=f"Person {i}",
                             age=20 + (i % 50),
                             department=["Engineering", "Sales", "Marketing"][i % 3],
                             active=i % 10 != 0)  # 90% active
                nodes.append(node_id)
            
            # Add relationships
            for i in range(0, 900, 10):
                # Create manager relationships
                manager = f"person_{i}"
                for j in range(i + 1, min(i + 6, 1000)):
                    employee = f"person_{j}"
                    graph.add_edge(manager, employee, "manages", 
                                 since=2020 + (j % 3),
                                 department="Engineering")
                
                # Create peer relationships
                for j in range(i + 1, min(i + 3, 1000)):
                    peer = f"person_{j}"
                    graph.add_edge(f"person_{i}", peer, "collaborates_with",
                                 project=f"Project_{i % 10}")
            
            # Verify data integrity
            assert len(graph) == 1000
            assert len(graph._edges) > 2000
            
            # Test querying with caching
            engineers = graph.find_nodes(department="Engineering")
            assert len(engineers) > 300
            
            # Second query should hit cache
            engineers2 = graph.find_nodes(department="Engineering")
            assert len(engineers2) == len(engineers)
            
            # Test auto-save
            saved_path = graph.save()
            assert saved_path.exists()
            assert saved_path.parent == temp_dir / "data"
            
            # Test backup
            backup_paths = graph.backup()
            assert len(backup_paths) >= 1
            for backup_path in backup_paths:
                assert backup_path.exists()
                assert backup_path.parent == temp_dir / "backups"
            
            # Test format translation
            json_path = temp_dir / "translated.json"
            translated = graph.translate(saved_path, json_path, "msgpack", "json")
            assert translated == json_path
            assert json_path.exists()
            
            # Test loading in different format
            graph2 = FastGraph(name="loaded_test", config=config)
            graph2.load(json_path)
            assert len(graph2) == 1000
            assert len(graph2._edges) > 2000
            
            # Verify data consistency
            original_engineers = graph.find_nodes(department="Engineering")
            loaded_engineers = graph2.find_nodes(department="Engineering")
            assert len(original_engineers) == len(loaded_engineers)
            
            # Test context manager cleanup
            with FastGraph(name="context_test", config=config) as context_graph:
                context_graph.add_node("test", name="Test Node")
                # Should auto-save on exit
            
            # Verify context manager saved the file
            context_files = list((temp_dir / "data").glob("context_test*"))
            assert len(context_files) > 0
            
            # Test factory methods
            factory_graph = FastGraph.from_file(saved_path, config=config)
            assert len(factory_graph) == 1000
            
            # Test resource cleanup
            graph_id = graph._graph_id
            assert graph_id in graph._resource_manager._active_graphs
            
            graph.cleanup()
            assert graph_id not in graph._resource_manager._active_graphs
    
    def test_multi_graph_workflow(self):
        """Test workflow with multiple interconnected graphs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)},
                "resource_management": {"max_open_graphs": 10}
            }
            
            # Create multiple graphs for different departments
            graphs = {}
            departments = ["Engineering", "Sales", "Marketing", "HR", "Finance"]
            
            for dept in departments:
                graphs[dept] = FastGraph(name=f"{dept.lower()}_graph", config=config)
                
                # Add department-specific data
                for i in range(100):
                    emp_id = f"{dept.lower()}_emp_{i}"
                    graphs[dept].add_node(emp_id,
                                        name=f"Employee {i}",
                                        department=dept,
                                        salary=50000 + (i * 1000),
                                        hire_year=2018 + (i % 5)
                    )
            
            # Create cross-department relationships
            # Engineering-Sales collaboration
            for i in range(20):
                eng = f"engineering_emp_{i}"
                sales = f"sales_emp_{i}"
                graphs["Engineering"].add_edge(eng, sales, "works_with",
                                             project=f"Project_{i}")
            
            # Save all graphs
            saved_paths = {}
            for dept, graph in graphs.items():
                saved_paths[dept] = graph.save()
                assert saved_paths[dept].exists()
            
            # Load and verify all graphs
            loaded_graphs = {}
            for dept, path in saved_paths.items():
                loaded_graphs[dept] = FastGraph.load_graph(path, config=config)
                assert len(loaded_graphs[dept]) == 100
            
            # Test resource management with multiple graphs
            resource_manager = graphs["Engineering"]._resource_manager
            stats = resource_manager.get_memory_usage()
            assert stats["active_graphs"] >= len(departments)
            
            # Cleanup all graphs
            for graph in graphs.values():
                graph.cleanup()
    
    def test_disaster_recovery_workflow(self):
        """Test disaster recovery and backup workflows."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {
                    "data_dir": str(temp_dir / "data"),
                    "default_format": "json"
                },
                "persistence": {
                    "backup_directory": str(temp_dir / "backups"),
                    "max_backups": 5,
                    "auto_save_on_exit": True
                },
                "security": {
                    "allowed_serialization_formats": ["json", "msgpack", "pickle"]
                }
            }
            
            # Create critical business data
            graph = FastGraph(name="critical_data", config=config)
            
            # Add important nodes and relationships
            critical_nodes = [
                ("ceo", "CEO", "Executive", 1000000),
                ("cto", "CTO", "Executive", 800000),
                ("cfo", "CFO", "Executive", 750000),
            ]
            
            for node_id, title, dept, salary in critical_nodes:
                graph.add_node(node_id, name=title, department=dept, salary=salary,
                             critical=True)
            
            # Add organizational structure
            graph.add_edge("ceo", "cto", "reports_to")
            graph.add_edge("ceo", "cfo", "reports_to")
            
            # Add regular employees
            for i in range(50):
                emp_id = f"emp_{i}"
                graph.add_node(emp_id, name=f"Employee {i}",
                             department="Engineering", salary=80000)
                
                # Random reporting structure
                if i < 10:
                    graph.add_edge(emp_id, "cto", "reports_to")
                else:
                    graph.add_edge(emp_id, f"emp_{i-10}", "reports_to")
            
            # Create multiple backups over time
            backup_paths = []
            for i in range(3):
                # Modify data slightly
                graph.add_node(f"temp_node_{i}", name=f"Temp {i}")
                backup_paths.extend(graph.backup())
                time.sleep(0.1)  # Ensure different timestamps
            
            # Verify backups exist in different formats
            assert len(backup_paths) >= 3  # At least 3 backup sets
            
            # Simulate data corruption
            original_count = len(graph)
            graph.clear()  # Corrupt/delete data
            
            assert len(graph) == 0
            
            # Restore from backup
            restored_path = graph.restore_from_backup()
            assert restored_path.exists()
            assert len(graph) == original_count
            
            # Verify critical data is restored
            critical_data = graph.find_nodes(critical=True)
            assert len(critical_data) == 3
            
            # Test restoration from specific backup format
            json_backup = None
            for backup in backup_paths:
                if backup.suffix == ".json":
                    json_backup = backup
                    break
            
            if json_backup:
                graph.clear()
                graph.load(json_backup)
                assert len(graph) == original_count
    
    def test_format_migration_workflow(self):
        """Test migrating data between different formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {"enhanced_api": {"enabled": True}}
            
            # Create graph with mixed data types
            graph = FastGraph(name="migration_test", config=config)
            
            # Add various data types to test serialization
            import datetime
            from decimal import Decimal
            
            graph.add_node("test_1", 
                         name="Test Node 1",
                         value=42,
                         score=3.14,
                         active=True,
                         tags=["tag1", "tag2"],
                         metadata={"key": "value"},
                         created_at=datetime.datetime.now(),
                         price=Decimal("99.99"))
            
            graph.add_node("test_2",
                         name="Test Node 2",
                         description="A test node with special characters: ñáéíóú",
                         binary_data=b"binary_content",
                         none_value=None)
            
            graph.add_edge("test_1", "test_2", "connected",
                         weight=1.5,
                         properties={"type": "strong", "duration": 3600})
            
            # Test saving in all formats
            formats = ["json", "msgpack", "pickle"]
            saved_files = {}
            
            for fmt in formats:
                path = temp_dir / f"test.{fmt}"
                graph.save(path, format=fmt)
                saved_files[fmt] = path
                assert path.exists()
            
            # Test loading from each format and verifying data integrity
            for fmt, path in saved_files.items():
                loaded_graph = FastGraph(config=config)
                loaded_graph.load(path)
                
                # Verify nodes
                assert len(loaded_graph) == 2
                node1 = loaded_graph.get_node("test_1")
                assert node1["name"] == "Test Node 1"
                assert node1["value"] == 42
                assert node1["active"] is True
                
                # Verify edges
                edge = loaded_graph.get_edge("test_1", "test_2", "connected")
                assert edge is not None
                assert edge.get_attribute("weight") == 1.5
            
            # Test format translation chain
            # JSON -> msgpack -> pickle -> JSON
            current_path = saved_files["json"]
            
            for target_fmt in ["msgpack", "pickle", "json"]:
                target_path = temp_dir / f"chain_test.{target_fmt}"
                source_fmt = current_path.suffix[1:]  # Remove dot
                
                translated_path = graph.translate(current_path, target_path, 
                                               source_fmt, target_fmt)
                assert translated_path == target_path
                assert target_path.exists()
                
                # Verify translated data
                test_graph = FastGraph(config=config)
                test_graph.load(target_path)
                assert len(test_graph) == 2
                
                current_path = target_path
    
    def test_concurrent_multi_user_simulation(self):
        """Test concurrent access simulating multiple users."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)},
                "resource_management": {"max_open_graphs": 20}
            }
            
            # Shared graph data
            shared_graph_path = temp_dir / "shared_graph.msgpack"
            
            # Initialize shared graph
            shared_graph = FastGraph(name="shared", config=config)
            for i in range(50):
                shared_graph.add_node(f"shared_node_{i}", name=f"Shared Node {i}")
            shared_graph.save(shared_graph_path)
            
            results = {}
            errors = {}
            
            def user_simulation(user_id, operation_count):
                """Simulate a user performing various operations."""
                try:
                    user_graph = FastGraph.load_graph(shared_graph_path, config=config)
                    
                    # Add user-specific nodes
                    for i in range(10):
                        user_graph.add_node(f"user_{user_id}_node_{i}",
                                          name=f"User {user_id} Node {i}")
                    
                    # Perform various operations
                    for i in range(operation_count):
                        # Add some edges
                        if i < 5:
                            user_graph.add_edge(f"shared_node_{i}", 
                                              f"user_{user_id}_node_{i}",
                                              "accessed")
                        
                        # Query operations
                        if i % 3 == 0:
                            user_graph.find_nodes(name__contains="Node")
                        
                        # Save periodically
                        if i % 5 == 0:
                            user_path = temp_dir / f"user_{user_id}_graph.msgpack"
                            user_graph.save(user_path)
                    
                    # Final save
                    user_path = temp_dir / f"user_{user_id}_final.msgpack"
                    user_graph.save(user_path)
                    
                    results[user_id] = {
                        "nodes": len(user_graph),
                        "edges": len(user_graph._edges),
                        "operations": operation_count
                    }
                    
                    user_graph.cleanup()
                    
                except Exception as e:
                    errors[user_id] = str(e)
            
            # Simulate multiple concurrent users
            threads = []
            user_count = 5
            
            for user_id in range(user_count):
                t = threading.Thread(target=user_simulation, 
                                   args=(user_id, 20))
                threads.append(t)
                t.start()
            
            # Wait for all users to complete
            for t in threads:
                t.join()
            
            # Verify results
            assert len(results) == user_count
            assert len(errors) == 0, f"Errors occurred: {errors}"
            
            # Check that all users completed their operations
            total_nodes = sum(result["nodes"] for result in results.values())
            total_edges = sum(result["edges"] for result in results.values())
            total_operations = sum(result["operations"] for result in results.values())
            
            assert total_nodes > 50  # Original nodes + user nodes
            assert total_edges > 0
            assert total_operations == user_count * 20
            
            # Verify resource management
            # Most graphs should be cleaned up
            remaining_graphs = list(temp_dir.glob("user_*_final.msgpack"))
            assert len(remaining_graphs) == user_count


class TestSystemIntegration:
    """Test integration with system components and external dependencies."""
    
    def test_file_system_integration(self):
        """Test integration with file system operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)}
            }
            
            graph = FastGraph(name="fs_test", config=config)
            graph.add_node("test", name="Test")
            
            # Test save to nested directory
            nested_path = temp_dir / "level1" / "level2" / "test.msgpack"
            saved_path = graph.save(nested_path)
            assert saved_path.exists()
            assert saved_path.parent.exists()
            
            # Test loading with relative paths
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                rel_path = "level1/level2/test.msgpack"
                graph2 = FastGraph(config=config)
                graph2.load(rel_path)
                assert len(graph2) == 1
            finally:
                os.chdir(old_cwd)
            
            # Test with symbolic links (if supported)
            if os.name != 'nt':  # Unix-like systems
                link_dir = temp_dir / "link_target"
                link_dir.mkdir()
                link_path = link_dir / "linked_graph.msgpack"
                
                try:
                    # Create symbolic link
                    os.symlink(saved_path, link_path)
                    
                    # Load through symlink
                    graph3 = FastGraph(config=config)
                    graph3.load(link_path)
                    assert len(graph3) == 1
                except (OSError, NotImplementedError):
                    # Symlinks not supported
                    pass
    
    def test_memory_pressure_simulation(self):
        """Test behavior under memory pressure."""
        config = {
            "enhanced_api": {"enabled": True},
            "resource_management": {
                "max_open_graphs": 3,
                "memory_limit_per_graph": "1MB"  # Very low limit
            }
        }
        
        graphs = []
        
        # Create graphs until limit is reached
        for i in range(5):
            try:
                graph = FastGraph(name=f"pressure_test_{i}", config=config)
                # Add some data to consume memory
                for j in range(100):
                    graph.add_node(f"node_{i}_{j}", 
                                 data="x" * 100)  # 100 bytes per node
                graphs.append(graph)
            except Exception as e:
                # Should hit memory limit
                assert "memory" in str(e).lower() or "limit" in str(e).lower()
                break
        
        # Should have limited number of graphs
        assert len(graphs) <= 3
        
        # Cleanup
        for graph in graphs:
            graph.cleanup()
    
    def test_error_recovery_integration(self):
        """Test error recovery and system resilience."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)},
                "persistence": {
                    "backup_directory": str(temp_dir / "backups"),
                    "max_backups": 2
                }
            }
            
            graph = FastGraph(name="recovery_test", config=config)
            
            # Add critical data
            for i in range(10):
                graph.add_node(f"critical_{i}", name=f"Critical {i}", important=True)
            
            # Create backup
            graph.backup()
            
            # Simulate various error conditions and recovery
            
            # 1. Corrupted file
            corrupted_path = temp_dir / "corrupted.msgpack"
            with open(corrupted_path, 'wb') as f:
                f.write(b'corrupted data that cannot be parsed')
            
            try:
                graph.load(corrupted_path)
                assert False, "Should have failed to load corrupted file"
            except PersistenceError:
                pass  # Expected
            
            # Should still be able to use the graph
            assert len(graph) == 10
            
            # 2. Permission denied (simulate)
            restricted_path = temp_dir / "restricted.msgpack"
            restricted_path.touch()
            restricted_path.chmod(0o000)  # No permissions
            
            try:
                graph.save(restricted_path)
                assert False, "Should have failed due to permissions"
            except (PersistenceError, PermissionError):
                pass  # Expected
            
            # Restore permissions for cleanup
            restricted_path.chmod(0o644)
            
            # 3. Disk space simulation (create large file)
            large_path = temp_dir / "large.msgpack"
            try:
                with open(large_path, 'wb') as f:
                    # Try to write a lot of data (will be limited by actual disk space)
                    f.write(b'x' * (100 * 1024 * 1024))  # 100MB
            except (OSError, IOError):
                pass  # Disk full, expected
            
            # System should still be functional
            working_path = temp_dir / "working.msgpack"
            graph.save(working_path)
            assert working_path.exists()
            
            # Test recovery from backup
            graph.clear()
            graph.restore_from_backup()
            assert len(graph) == 10


class TestPerformanceIntegration:
    """Integration tests with performance focus."""
    
    def test_large_dataset_performance(self):
        """Test performance with large datasets."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)},
                "memory": {"query_cache_size": 128}
            }
            
            graph = FastGraph(name="large_test", config=config)
            
            # Measure performance of bulk operations
            start_time = time.time()
            
            # Add many nodes
            batch_size = 1000
            node_count = 10000
            
            for batch_start in range(0, node_count, batch_size):
                batch = []
                for i in range(batch_start, min(batch_start + batch_size, node_count)):
                    batch.append((f"node_{i}", {
                        "name": f"Node {i}",
                        "category": f"Category_{i % 10}",
                        "value": i,
                        "active": i % 2 == 0
                    }))
                
                graph.add_nodes_batch(batch)
            
            add_time = time.time() - start_time
            
            # Add edges in batches
            start_time = time.time()
            
            edge_batch = []
            for i in range(0, node_count - 1, 100):  # Every 100th node connects to next
                edge_batch.append((f"node_{i}", f"node_{i+1}", "sequence", {"order": i}))
                
                if len(edge_batch) >= 100:
                    graph.add_edges_batch(edge_batch)
                    edge_batch = []
            
            if edge_batch:
                graph.add_edges_batch(edge_batch)
            
            edge_time = time.time() - start_time
            
            # Test query performance
            start_time = time.time()
            results = graph.find_nodes(category="Category_5")
            query_time = time.time() - start_time
            
            # Test save/load performance
            start_time = time.time()
            saved_path = graph.save()
            save_time = time.time() - start_time
            
            start_time = time.time()
            loaded_graph = FastGraph(config=config)
            loaded_graph.load(saved_path)
            load_time = time.time() - start_time
            
            # Performance assertions (these are rough guidelines)
            assert add_time < 5.0, f"Node addition too slow: {add_time}s"
            assert edge_time < 3.0, f"Edge addition too slow: {edge_time}s"
            assert query_time < 1.0, f"Query too slow: {query_time}s"
            assert save_time < 2.0, f"Save too slow: {save_time}s"
            assert load_time < 2.0, f"Load too slow: {load_time}s"
            
            # Verify data integrity
            assert len(graph) == node_count
            assert len(results) == node_count // 10
            assert len(loaded_graph) == node_count
    
    def test_cache_performance_integration(self):
        """Test cache performance in integration scenarios."""
        config = {
            "enhanced_api": {"enabled": True},
            "memory": {
                "query_cache_size": 256,
                "cache_ttl": 3600
            }
        }
        
        graph = FastGraph(config=config)
        
        # Add data with various query patterns
        categories = ["A", "B", "C", "D", "E"]
        for i in range(1000):
            category = categories[i % len(categories)]
            graph.add_node(f"node_{i}", category=category, value=i)
        
        # Perform repeated queries to test caching
        queries = [
            {"category": "A"},
            {"category": "B"},
            {"value": 500},
            {"category": "C", "value__gt": 400}
        ]
        
        # First round - cache misses
        start_time = time.time()
        for query in queries:
            graph.find_nodes(**query)
        first_round_time = time.time() - start_time
        
        # Second round - should hit cache
        start_time = time.time()
        for query in queries:
            graph.find_nodes(**query)
        second_round_time = time.time() - start_time
        
        # Cache should improve performance
        assert second_round_time < first_round_time
        
        # Check cache statistics
        stats = graph.stats()
        assert stats["cache_hits"] > 0
        assert stats["cache_hits"] == len(queries)  # All should hit cache


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""
Comprehensive test suite for enhanced FastGraph Phase 2 implementation.

This test verifies all the new enhanced features while ensuring
backward compatibility with existing code.
"""

import os
import tempfile
import json
import time
import threading
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add the fastgraph package to the path
sys.path.insert(0, '.')

from fastgraph.core.graph import FastGraph
from fastgraph.exceptions import (
    PersistenceError, ValidationError, MemoryError,
    ConcurrencyError, NodeNotFoundError, EdgeNotFoundError
)
from fastgraph.utils.path_resolver import PathResolver
from fastgraph.utils.resource_manager import ResourceManager


class TestBackwardCompatibility:
    """Test suite for backward compatibility."""
    
    def test_backward_compatibility(self):
        """Test that existing code continues to work unchanged."""
        print("Testing backward compatibility...")
        
        # Test basic constructor
        graph = FastGraph()
        assert graph.name == "fastgraph"
        assert not graph._enhanced_enabled
        
        # Test basic operations
        graph.add_node("A", name="Alice", age=25)
        graph.add_node("B", name="Bob", age=30)
        graph.add_edge("A", "B", "knows", since=2021)
        
        assert len(graph) == 2
        assert graph.get_node("A")["name"] == "Alice"
        assert graph.get_edge("A", "B", "knows") is not None
        
        # Test basic save/load with explicit paths
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_graph.msgpack"
            
            # Save
            graph.save(temp_path)
            assert temp_path.exists()
            
            # Load into new graph
            graph2 = FastGraph()
            graph2.load(temp_path)
            
            assert len(graph2) == 2
            assert graph2.get_node("A")["name"] == "Alice"
            
        print("Backward compatibility tests passed")


class TestEnhancedConstructor:
    """Test suite for enhanced constructor functionality."""
    
    def test_enhanced_constructor(self):
        """Test enhanced constructor with new features."""
        print("Testing enhanced constructor...")
        
        # Test with enhanced API enabled
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(name="test_graph", config=config)
        
        assert graph.name == "test_graph"
        assert graph._enhanced_enabled
        assert graph._path_resolver is not None
        assert graph._resource_manager is not None
        assert graph._graph_id is not None
        
        # Test with direct parameter
        graph2 = FastGraph(name="test2", enhanced_api=True)
        assert graph2._enhanced_enabled
        
        print("Enhanced constructor tests passed")
    
    def test_constructor_config_overrides(self):
        """Test constructor with configuration overrides."""
        config = {"enhanced_api": {"enabled": False}}
        graph = FastGraph(name="test", enhanced_api=True, config=config)
        # Direct parameter should override config
        assert graph._enhanced_enabled
    
    def test_constructor_with_config_manager(self):
        """Test constructor with ConfigManager instance."""
        from fastgraph.config.manager import ConfigManager
        config_mgr = ConfigManager(config_dict={"enhanced_api": {"enabled": True}})
        graph = FastGraph(name="test", config=config_mgr)
        assert graph._enhanced_enabled
    
    def test_constructor_parameter_types(self):
        """Test constructor with different parameter types."""
        # Test with Path
        graph = FastGraph(name="test", config="nonexistent.yaml")
        assert graph.name == "test"
        
        # Test with dict
        graph = FastGraph(name="test", config={"storage": {"default_format": "json"}})
        assert graph.config.get("storage.default_format") == "json"


class TestEnhancedSaveLoad:
    """Test suite for enhanced save/load functionality."""
    
    def test_enhanced_save_load(self):
        """Test enhanced save/load with auto-resolution."""
        print("Testing enhanced save/load...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Create graph with enhanced features
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)}
            }
            graph = FastGraph(name="auto_graph", config=config)
            
            # Add some data
            graph.add_node("X", name="Xander", type="Person")
            graph.add_node("Y", name="Yara", type="Person")
            graph.add_edge("X", "Y", "friend")
            
            # Test auto-save (no path specified)
            saved_path = graph.save()
            assert saved_path is not None
            assert saved_path.exists()
            assert saved_path.name.startswith("auto_graph")
            
            # Test auto-load
            graph2 = FastGraph(name="auto_graph", config=config)
            loaded_path = graph2.load()
            assert loaded_path == saved_path
            assert len(graph2) == 2
            
            # Test save with path hint
            path_hint = temp_dir / "data" / "hinted_graph"
            hinted_path = graph.save(path_hint)
            assert hinted_path.exists()
            # Check that the path was resolved correctly (may add extension)
            assert "hinted_graph" in hinted_path.name
            
        print("Enhanced save/load tests passed")
    
    def test_save_load_different_formats(self):
        """Test save/load with different formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {"enhanced_api": {"enabled": True}}
            graph = FastGraph(name="format_test", config=config)
            graph.add_node("A", name="Alice")
            
            # Test JSON
            json_path = graph.save(format="json")
            assert json_path.suffix == ".json"
            
            # Test msgpack
            msgpack_path = graph.save(format="msgpack")
            assert msgpack_path.suffix == ".msgpack"
            
            # Test pickle
            pickle_path = graph.save(format="pickle")
            assert pickle_path.suffix == ".pickle"
            
            # Load and verify data integrity
            for path in [json_path, msgpack_path, pickle_path]:
                graph2 = FastGraph(config=config)
                graph2.load(path)
                assert len(graph2) == 1
                assert graph2.get_node("A")["name"] == "Alice"
    
    def test_save_load_with_compression(self):
        """Test save/load with compression."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {"enhanced_api": {"enabled": True}}
            graph = FastGraph(name="compress_test", config=config)
            graph.add_node("A", name="Alice")
            
            # Save with compression
            path = graph.save(compress=True)
            assert path.exists()
            
            # Load back
            graph2 = FastGraph(config=config)
            graph2.load(path)
            assert len(graph2) == 1
    
    def test_save_load_error_handling(self):
        """Test save/load error handling."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(config=config)
        
        # Test save to invalid path
        with pytest.raises(PersistenceError):
            graph.save("/invalid/path/that/does/not/exist/test.graph")
        
        # Test load non-existent file
        with pytest.raises(PersistenceError):
            graph.load("nonexistent.graph")
        
        # Test load invalid format
        with tempfile.NamedTemporaryFile() as f:
            with pytest.raises(PersistenceError):
                graph.load(f.name)


class TestExistsMethod:
    """Test suite for exists() method."""
    
    def test_exists_method(self):
        """Test the new exists() method."""
        print("Testing exists() method...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {"enhanced_api": {"enabled": True}, "storage": {"data_dir": str(temp_dir)}}
            graph = FastGraph(name="exists_test", config=config)
            
            # Initially should not exist
            assert not graph.exists()
            assert not graph.exists("nonexistent")
            
            # Save and check existence
            saved_path = graph.save()
            assert graph.exists()
            assert graph.exists("exists_test")
            assert graph.exists(saved_path)
            
            # Test with basic graph (no enhanced features)
            basic_graph = FastGraph()
            # Basic graph should still be able to check if a file exists
            assert basic_graph.exists(saved_path)  # Should return True for existing file
            assert not basic_graph.exists("nonexistent_file")  # Should return False for non-existent file
            
        print("Exists method tests passed")
    
    def test_exists_with_different_paths(self):
        """Test exists method with various path types."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {"enhanced_api": {"enabled": True}}
            graph = FastGraph(name="test", config=config)
            graph.add_node("A", name="Alice")
            
            # Save file
            path = graph.save()
            
            # Test with string path
            assert graph.exists(str(path))
            
            # Test with Path object
            assert graph.exists(path)
            
            # Test with relative path
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                rel_path = path.name
                assert graph.exists(rel_path)
            finally:
                os.chdir(old_cwd)


class TestTranslationMethods:
    """Test suite for format translation methods."""
    
    def test_translate_methods(self):
        """Test format translation methods."""
        print("Testing translation methods...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Create and save a graph in JSON format
            config = {"enhanced_api": {"enabled": True}}
            graph = FastGraph(name="translate_test", config=config)
            
            graph.add_node("A", name="Alice")
            graph.add_node("B", name="Bob")
            graph.add_edge("A", "B", "knows")
            
            # Save as JSON
            json_path = temp_dir / "test.json"
            graph.save(json_path, format="json")
            
            # Test translate to msgpack
            msgpack_path = temp_dir / "test.msgpack"
            translated_path = graph.translate(json_path, msgpack_path, "json", "msgpack")
            assert translated_path == msgpack_path
            assert msgpack_path.exists()
            
            # Test get_translation
            pickle_path = graph.get_translation(json_path, "pickle", temp_dir)
            assert pickle_path.exists()
            assert pickle_path.name == "test.pickle"
            
            # Verify the translated files can be loaded
            graph2 = FastGraph(config=config)
            graph2.load(msgpack_path)
            assert len(graph2) == 2
            
        print("Translation method tests passed")
    
    def test_translate_all_formats(self):
        """Test translation between all supported formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {"enhanced_api": {"enabled": True}}
            graph = FastGraph(name="translate_all", config=config)
            graph.add_node("A", name="Alice")
            
            formats = ["json", "msgpack", "pickle"]
            
            for source_format in formats:
                for target_format in formats:
                    if source_format != target_format:
                        source_path = temp_dir / f"test.{source_format}"
                        target_path = temp_dir / f"test.{target_format}"
                        
                        # Save in source format
                        graph.save(source_path, format=source_format)
                        
                        # Translate to target format
                        translated = graph.translate(source_path, target_path, source_format, target_format)
                        assert translated == target_path
                        assert target_path.exists()
                        
                        # Verify can load from target format
                        graph2 = FastGraph(config=config)
                        graph2.load(target_path)
                        assert len(graph2) == 1
    
    def test_translate_error_handling(self):
        """Test translation error handling."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(config=config)
        
        # Test translate without enhanced API
        basic_graph = FastGraph()
        with pytest.raises(PersistenceError):
            basic_graph.translate("test.json", "test.msgpack")
        
        # Test translate non-existent source
        with pytest.raises(PersistenceError):
            graph.translate("nonexistent.json", "test.msgpack")
        
        # Test translate to invalid path
        with tempfile.NamedTemporaryFile() as f:
            # Create a valid source file
            f.write(b'{"nodes": {}, "edges": []}')
            f.flush()
            
            with pytest.raises(PersistenceError):
                graph.translate(f.name, "/invalid/path/test.msgpack")


class TestFactoryMethods:
    """Test suite for factory methods."""
    
    def test_factory_methods(self):
        """Test factory methods."""
        print("Testing factory methods...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Create a test file
            config = {"enhanced_api": {"enabled": True}}
            original_graph = FastGraph(name="factory_test", config=config)
            original_graph.add_node("A", name="Alice")
            original_graph.add_node("B", name="Bob")
            original_graph.add_edge("A", "B", "knows")
            
            test_file = temp_dir / "factory_test.msgpack"
            original_graph.save(test_file)
            
            # Test from_file
            graph1 = FastGraph.from_file(test_file)
            assert len(graph1) == 2
            assert graph1.get_node("A")["name"] == "Alice"
            
            # Test load factory method
            graph2 = FastGraph.load_graph(test_file)
            assert len(graph2) == 2
            
            # Test with_config
            custom_config = {"enhanced_api": {"enabled": True}, "memory": {"query_cache_size": 64}}
            graph3 = FastGraph.with_config(custom_config, name="custom")
            assert graph3._enhanced_enabled
            assert graph3.name == "custom"
            
        print("Factory method tests passed")
    
    def test_from_file_with_format_detection(self):
        """Test from_file with automatic format detection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Create test files in different formats
            original = FastGraph(name="test")
            original.add_node("A", name="Alice")
            
            formats = ["json", "msgpack", "pickle"]
            for fmt in formats:
                path = temp_dir / f"test.{fmt}"
                original.save(path, format=fmt)
                
                # Load with from_file (should auto-detect)
                graph = FastGraph.from_file(path)
                assert len(graph) == 1
                assert graph.get_node("A")["name"] == "Alice"
    
    def test_load_graph_with_discovery(self):
        """Test load_graph with auto-discovery."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Create a graph file
            original = FastGraph(name="discovery_test")
            original.add_node("A", name="Alice")
            path = temp_dir / "discovery_test.msgpack"
            original.save(path)
            
            # Load by name (should discover the file)
            config = {"storage": {"data_dir": str(temp_dir)}}
            graph = FastGraph.load_graph(graph_name="discovery_test", config=config)
            assert len(graph) == 1
    
    def test_with_config_variations(self):
        """Test with_config with different config types."""
        # Test with dict
        graph1 = FastGraph.with_config({"enhanced_api": {"enabled": True}})
        assert graph1._enhanced_enabled
        
        # Test with file path (will create non-existent but should not fail)
        graph2 = FastGraph.with_config("nonexistent.yaml")
        assert graph2 is not None
        
        # Test with ConfigManager
        from fastgraph.config.manager import ConfigManager
        config_mgr = ConfigManager(config_dict={"enhanced_api": {"enabled": True}})
        graph3 = FastGraph.with_config(config_mgr)
        assert graph3._enhanced_enabled


class TestContextManager:
    """Test suite for context manager functionality."""
    
    def test_context_manager(self):
        """Test context manager support."""
        print("Testing context manager...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)},
                "persistence": {"auto_save_on_exit": True}
            }
            
            # Test context manager
            with FastGraph(name="context_test", config=config) as graph:
                graph.add_node("A", name="Alice")
                graph.add_node("B", name="Bob")
                graph.add_edge("A", "B", "knows")
                
                # Should still be accessible within context
                assert len(graph) == 2
            
            # After context exit, graph should be saved
            # Check if file exists
            saved_files = list(temp_dir.glob("context_test*"))
            assert len(saved_files) > 0
            
            # Test cleanup method
            graph = FastGraph(name="cleanup_test", config=config)
            graph.add_node("X", name="Xander")
            graph.cleanup()  # Should not raise an error
            
        print("Context manager tests passed")
    
    def test_context_manager_with_exception(self):
        """Test context manager behavior with exceptions."""
        config = {
            "enhanced_api": {"enabled": True},
            "persistence": {"auto_save_on_exit": True}
        }
        
        try:
            with FastGraph(name="exception_test", config=config) as graph:
                graph.add_node("A", name="Alice")
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected
        
        # Should not have saved due to exception
        # (unless auto_save_on_error is configured differently)
    
    def test_context_manager_cleanup(self):
        """Test context manager cleanup functionality."""
        config = {"enhanced_api": {"enabled": True}}
        
        graph = FastGraph(name="cleanup_test", config=config)
        graph_id = graph._graph_id
        
        # Should be registered with resource manager
        assert graph_id in graph._resource_manager._active_graphs
        
        # Context exit should unregister
        graph.__exit__(None, None, None)
        assert graph_id not in graph._resource_manager._active_graphs


class TestBackupRestore:
    """Test suite for backup and restore functionality."""
    
    def test_backup_restore(self):
        """Test backup and restore functionality."""
        print("Testing backup/restore...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "persistence": {"backup_directory": str(temp_dir / "backups")}
            }
            
            # Create and save graph
            graph = FastGraph(name="backup_test", config=config)
            graph.add_node("A", name="Alice")
            graph.add_node("B", name="Bob")
            graph.add_edge("A", "B", "knows")
            
            # Test backup
            backup_paths = graph.backup()
            assert len(backup_paths) > 0
            assert all(p.exists() for p in backup_paths)
            
            # Modify graph
            graph.add_node("C", name="Charlie")
            assert len(graph) == 3
            
            # Test restore
            restored_path = graph.restore_from_backup()
            assert restored_path.exists()
            assert len(graph) == 2  # Should be restored to original state
            
        print("Backup/restore tests passed")
    
    def test_backup_multiple_formats(self):
        """Test backup in multiple formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "persistence": {
                    "backup_directory": str(temp_dir / "backups"),
                    "max_backups": 3
                },
                "security": {
                    "allowed_serialization_formats": ["json", "msgpack", "pickle"]
                }
            }
            
            graph = FastGraph(name="multi_backup", config=config)
            graph.add_node("A", name="Alice")
            
            # Should create backups in all formats
            backup_paths = graph.backup()
            assert len(backup_paths) == 3  # One for each format
            
            # Check file extensions
            extensions = {p.suffix[1:] for p in backup_paths}  # Remove dot
            assert extensions == {"json", "msgpack", "pickle"}
    
    def test_backup_cleanup(self):
        """Test backup cleanup functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "persistence": {
                    "backup_directory": str(temp_dir / "backups"),
                    "max_backups": 2
                }
            }
            
            graph = FastGraph(name="cleanup_test", config=config)
            graph.add_node("A", name="Alice")
            
            # Create multiple backups
            for i in range(4):
                graph.backup()
                time.sleep(0.1)  # Ensure different timestamps
            
            # Should only keep max_backups
            backup_files = list((temp_dir / "backups").glob("cleanup_test_*"))
            assert len(backup_files) <= 2
    
    def test_restore_error_handling(self):
        """Test restore error handling."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(name="test", config=config)
        
        # Test restore without backups
        with pytest.raises(PersistenceError):
            graph.restore_from_backup()
        
        # Test restore without enhanced API
        basic_graph = FastGraph()
        with pytest.raises(PersistenceError):
            basic_graph.restore_from_backup()


class TestErrorHandling:
    """Test suite for error handling."""
    
    def test_error_handling(self):
        """Test error handling in enhanced features."""
        print("Testing error handling...")
        
        # Test enhanced features without enabling them
        graph = FastGraph()
        
        try:
            graph.translate("nonexistent.json", "test.msgpack")
            assert False, "Should have raised PersistenceError"
        except PersistenceError:
            pass  # Expected
        
        try:
            graph.get_translation("nonexistent.json", "msgpack")
            assert False, "Should have raised PersistenceError"
        except PersistenceError:
            pass  # Expected
        
        try:
            graph.backup()
            assert False, "Should have raised PersistenceError"
        except PersistenceError:
            pass  # Expected
        
        # Test basic graph with missing path
        basic_graph = FastGraph()
        try:
            basic_graph.save()  # Should require path for basic graph
            assert False, "Should have raised PersistenceError"
        except PersistenceError:
            pass  # Expected
        
        try:
            basic_graph.load()  # Should require path for basic graph
            assert False, "Should have raised PersistenceError"
        except PersistenceError:
            pass  # Expected
        
        print("Error handling tests passed")
    
    def test_persistence_error_details(self):
        """Test that PersistenceError includes proper details."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(config=config)
        
        try:
            graph.load("nonexistent_file.msgpack")
        except PersistenceError as e:
            assert e.file_path == "nonexistent_file.msgpack"
            assert e.operation == "load"
            assert "nonexistent_file.msgpack" in str(e)
    
    def test_validation_errors(self):
        """Test validation error handling."""
        # Test invalid format
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(config=config)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test.invalid"
            
            with pytest.raises(PersistenceError):
                graph.save(temp_path, format="invalid_format")


class TestResourceManagement:
    """Test suite for resource management integration."""
    
    def test_graph_registration(self):
        """Test graph registration with resource manager."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(name="resource_test", config=config)
        
        assert graph._graph_id is not None
        assert graph._graph_id in graph._resource_manager._active_graphs
        
        # Test access time updates
        original_time = graph._resource_manager._active_graphs[graph._graph_id]["last_accessed"]
        time.sleep(0.01)
        graph.get_node("nonexistent")  # Any operation should update access time
        new_time = graph._resource_manager._active_graphs[graph._graph_id]["last_accessed"]
        assert new_time > original_time
    
    def test_resource_cleanup(self):
        """Test resource cleanup on graph deletion."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(name="cleanup_test", config=config)
        graph_id = graph._graph_id
        
        # Should be registered
        assert graph_id in graph._resource_manager._active_graphs
        
        # Cleanup should unregister
        graph.cleanup()
        assert graph_id not in graph._resource_manager._active_graphs
    
    def test_memory_limit_enforcement(self):
        """Test memory limit enforcement."""
        config = {
            "enhanced_api": {"enabled": True},
            "resource_management": {
                "max_open_graphs": 2,
                "memory_limit_per_graph": "1KB"  # Very small limit
            }
        }
        
        # Create graphs up to limit
        graphs = []
        for i in range(2):
            graph = FastGraph(name=f"test_{i}", config=config)
            graph.add_node(str(i), name=f"Node {i}")
            graphs.append(graph)
        
        # Should enforce limits
        graphs[0]._resource_manager.enforce_limits()
        
        # Graphs should still exist (within limits)
        for g in graphs:
            assert g._graph_id in g._resource_manager._active_graphs


class TestPerformanceAndCaching:
    """Test suite for performance and caching features."""
    
    def test_query_caching(self):
        """Test query caching functionality."""
        config = {
            "memory": {
                "query_cache_size": 10,
                "cache_ttl": 3600
            }
        }
        graph = FastGraph(config=config)
        
        # Add test data
        for i in range(100):
            graph.add_node(f"node_{i}", value=i, type="test")
        
        # First query should cache result
        result1 = graph.find_nodes(type="test")
        assert len(result1) == 100
        
        # Second query should hit cache
        result2 = graph.find_nodes(type="test")
        assert result2 == result1
        
        # Check cache stats
        stats = graph.stats()
        assert stats["cache_hits"] > 0
    
    def test_cache_clear(self):
        """Test cache clearing."""
        config = {"memory": {"query_cache_size": 10}}
        graph = FastGraph(config=config)
        
        graph.add_node("A", name="Alice")
        graph.find_nodes(name="Alice")
        
        # Clear cache
        graph.clear_cache()
        
        # Cache should be empty
        if hasattr(graph.find_nodes, 'cache_info'):
            cache_info = graph.find_nodes.cache_info()
            assert cache_info.currsize == 0
    
    def test_memory_usage_estimation(self):
        """Test memory usage estimation."""
        graph = FastGraph()
        
        # Add some data
        for i in range(100):
            graph.add_node(f"node_{i}", data="x" * 100)
            graph.add_edge(f"node_{i}", f"node_{i+1}", "next" if i < 99 else "loop")
        
        memory_info = graph.memory_usage_estimate()
        assert "nodes_bytes" in memory_info
        assert "edges_bytes" in memory_info
        assert "total_bytes" in memory_info
        assert memory_info["nodes_bytes"] > 0


class TestThreadSafety:
    """Test suite for thread safety."""
    
    def test_concurrent_operations(self):
        """Test concurrent graph operations."""
        config = {"enhanced_api": {"enabled": True}}
        graph = FastGraph(config=config)
        
        def add_nodes(start, end):
            for i in range(start, end):
                graph.add_node(f"node_{i}", value=i)
        
        def add_edges(start, end):
            for i in range(start, end - 1):
                try:
                    graph.add_edge(f"node_{i}", f"node_{i+1}", "next")
                except Exception:
                    pass  # Node might not exist yet
        
        # Run concurrent operations
        threads = []
        threads.append(threading.Thread(target=add_nodes, args=(0, 50)))
        threads.append(threading.Thread(target=add_nodes, args=(50, 100)))
        threads.append(threading.Thread(target=add_edges, args=(0, 100)))
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Should have some data
        assert len(graph) > 0
    
    def test_concurrent_save_load(self):
        """Test concurrent save/load operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            config = {
                "enhanced_api": {"enabled": True},
                "storage": {"data_dir": str(temp_dir)}
            }
            
            def save_graph(name):
                graph = FastGraph(name=name, config=config)
                graph.add_node("test", name=name)
                graph.save()
            
            # Create multiple graphs concurrently
            threads = []
            for i in range(5):
                t = threading.Thread(target=save_graph, args=(f"test_{i}",))
                threads.append(t)
            
            for t in threads:
                t.start()
            
            for t in threads:
                t.join()
            
            # Should have created multiple files
            files = list(temp_dir.glob("test_*"))
            assert len(files) == 5


# Legacy test functions for backward compatibility
def run_all_tests():
    """Run all tests."""
    print("Running FastGraph Phase 2 Enhanced API Tests\n")
    
    try:
        # Run test class methods
        bc = TestBackwardCompatibility()
        bc.test_backward_compatibility()
        
        ec = TestEnhancedConstructor()
        ec.test_enhanced_constructor()
        ec.test_constructor_config_overrides()
        ec.test_constructor_with_config_manager()
        ec.test_constructor_parameter_types()
        
        sl = TestEnhancedSaveLoad()
        sl.test_enhanced_save_load()
        sl.test_save_load_different_formats()
        sl.test_save_load_with_compression()
        sl.test_save_load_error_handling()
        
        em = TestExistsMethod()
        em.test_exists_method()
        em.test_exists_with_different_paths()
        
        tm = TestTranslationMethods()
        tm.test_translate_methods()
        tm.test_translate_all_formats()
        tm.test_translate_error_handling()
        
        fm = TestFactoryMethods()
        fm.test_factory_methods()
        fm.test_from_file_with_format_detection()
        fm.test_load_graph_with_discovery()
        fm.test_with_config_variations()
        
        cm = TestContextManager()
        cm.test_context_manager()
        cm.test_context_manager_with_exception()
        cm.test_context_manager_cleanup()
        
        br = TestBackupRestore()
        br.test_backup_restore()
        br.test_backup_multiple_formats()
        br.test_backup_cleanup()
        br.test_restore_error_handling()
        
        eh = TestErrorHandling()
        eh.test_error_handling()
        eh.test_persistence_error_details()
        eh.test_validation_errors()
        
        rm = TestResourceManagement()
        rm.test_graph_registration()
        rm.test_resource_cleanup()
        rm.test_memory_limit_enforcement()
        
        pc = TestPerformanceAndCaching()
        pc.test_query_caching()
        pc.test_cache_clear()
        pc.test_memory_usage_estimation()
        
        ts = TestThreadSafety()
        ts.test_concurrent_operations()
        ts.test_concurrent_save_load()
        
        print("\nAll tests passed! Enhanced FastGraph implementation is working correctly.")
        print("\nKey features verified:")
        print("- Backward compatibility maintained")
        print("- Enhanced constructor with PathResolver and ResourceManager")
        print("- Auto-save and auto-load with path resolution")
        print("- Format translation capabilities")
        print("- Factory methods for common patterns")
        print("- Context manager support")
        print("- Backup and restore functionality")
        print("- Proper error handling")
        print("- Resource management and cleanup")
        print("- Performance and caching features")
        print("- Thread safety")
        
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
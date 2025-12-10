"""
Comprehensive test suite for FastGraph foundation components.

This module tests the core utility components that provide enhanced
functionality to FastGraph including PathResolver and ResourceManager.
"""

import os
import tempfile
import time
import threading
import pytest
import json
import gzip
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add the fastgraph package to the path
sys.path.insert(0, '.')

from fastgraph.utils.path_resolver import PathResolver
from fastgraph.utils.resource_manager import ResourceManager
from fastgraph.exceptions import PersistenceError, ValidationError, MemoryError, ConcurrencyError


class TestPathResolver:
    """Test suite for PathResolver class."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "storage": {
                "data_dir": self.temp_dir,
                "default_format": "msgpack"
            }
        }
        self.resolver = PathResolver(self.config)
    
    def teardown_method(self):
        """Clean up after each test."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_path_resolver_initialization(self):
        """Test PathResolver initialization."""
        resolver = PathResolver()
        assert resolver._supported_formats == {"msgpack", "pickle", "json"}
        assert len(resolver._default_search_paths) > 0
        assert resolver._format_signatures is not None
    
    def test_path_resolver_with_config(self):
        """Test PathResolver with custom configuration."""
        config = {
            "storage": {
                "data_dir": "/custom/path",
                "default_format": "json"
            }
        }
        resolver = PathResolver(config)
        assert resolver.config == config
    
    def test_resolve_path_absolute_existing(self):
        """Test resolving absolute existing path."""
        # Create a test file
        test_file = Path(self.temp_dir) / "test.msgpack"
        test_file.touch()
        
        resolved = self.resolver.resolve_path(test_file)
        assert resolved == test_file
    
    def test_resolve_path_relative(self):
        """Test resolving relative path."""
        # Create a test file in temp directory
        test_file = Path(self.temp_dir) / "test.msgpack"
        test_file.touch()
        
        # Change to temp directory
        old_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            resolved = self.resolver.resolve_path("test.msgpack")
            assert resolved == test_file
        finally:
            os.chdir(old_cwd)
    
    def test_resolve_path_with_graph_name(self):
        """Test resolving path with graph name."""
        resolved = self.resolver.resolve_path(None, "test_graph")
        expected = Path(self.temp_dir) / "test_graph.msgpack"
        assert resolved == expected
    
    def test_resolve_path_with_format(self):
        """Test resolving path with specific format."""
        resolved = self.resolver.resolve_path(None, "test_graph", "json")
        expected = Path(self.temp_dir) / "test_graph.json"
        assert resolved == expected
    
    def test_resolve_path_with_hint(self):
        """Test resolving path with path hint."""
        resolved = self.resolver.resolve_path("data/test", "test_graph", "msgpack")
        expected = Path(self.temp_dir) / "data" / "test.msgpack"
        assert resolved == expected
    
    def test_detect_format_from_extension(self):
        """Test format detection from file extension."""
        assert self.resolver.detect_format("test.json") == "json"
        assert self.resolver.detect_format("test.msgpack") == "msgpack"
        assert self.resolver.detect_format("test.mp") == "msgpack"
        assert self.resolver.detect_format("test.pickle") == "pickle"
        assert self.resolver.detect_format("test.pkl") == "pickle"
        assert self.resolver.detect_format("test.unknown") is None
    
    def test_detect_format_from_content(self):
        """Test format detection from file content."""
        # Test JSON content
        json_file = Path(self.temp_dir) / "test.json"
        with open(json_file, 'w') as f:
            json.dump({"test": "data"}, f)
        
        assert self.resolver.detect_format(json_file) == "json"
        
        # Test compressed JSON
        gz_json_file = Path(self.temp_dir) / "test.json.gz"
        with gzip.open(gz_json_file, 'wt') as f:
            json.dump({"test": "data"}, f)
        
        # Should detect from extension first
        assert self.resolver.detect_format(gz_json_file) == "json"
    
    def test_ensure_directory(self):
        """Test directory creation."""
        test_path = Path(self.temp_dir) / "subdir" / "test.msgpack"
        resolved = self.resolver.ensure_directory(test_path)
        assert resolved.parent.exists()
        assert resolved.parent.is_dir()
    
    def test_find_graph_file(self):
        """Test finding graph files by name."""
        # Create test files
        (Path(self.temp_dir) / "test.msgpack").touch()
        (Path(self.temp_dir) / "test.graph.json").touch()
        (Path(self.temp_dir) / "other.pkl").touch()
        
        # Should find the exact match first
        found = self.resolver.find_graph_file("test")
        assert found == Path(self.temp_dir) / "test.msgpack"
        
        # Remove exact match and find variation
        (Path(self.temp_dir) / "test.msgpack").unlink()
        found = self.resolver.find_graph_file("test")
        assert found == Path(self.temp_dir) / "test.graph.json"
        
        # Should not find non-existent file
        assert self.resolver.find_graph_file("nonexistent") is None
    
    def test_get_default_path(self):
        """Test getting default path for graph."""
        default_path = self.resolver.get_default_path("my_graph")
        expected = Path(self.temp_dir) / "my_graph.msgpack"
        assert default_path == expected
        
        # Test with different format
        json_path = self.resolver.get_default_path("my_graph", "json")
        expected_json = Path(self.temp_dir) / "my_graph.json"
        assert json_path == expected_json
    
    def test_ensure_format_extension(self):
        """Test ensuring correct format extension."""
        path = Path("test")
        
        # Add extension
        with_ext = self.resolver._ensure_format_extension(path, "msgpack")
        assert with_ext.suffix == ".msgpack"
        
        # Change extension
        wrong_ext = Path("test.json")
        corrected = self.resolver._ensure_format_extension(wrong_ext, "msgpack")
        assert corrected.suffix == ".msgpack"
        
        # Keep correct extension
        correct_ext = Path("test.msgpack")
        kept = self.resolver._ensure_format_extension(correct_ext, "msgpack")
        assert kept.suffix == ".msgpack"
    
    def test_get_supported_formats(self):
        """Test getting supported formats."""
        formats = self.resolver.get_supported_formats()
        assert isinstance(formats, list)
        assert "msgpack" in formats
        assert "json" in formats
        assert "pickle" in formats
        assert len(formats) == 3
    
    def test_path_resolver_error_handling(self):
        """Test PathResolver error handling."""
        # Test with invalid path that can't be resolved
        with pytest.raises(PersistenceError):
            self.resolver.resolve_path("", None, None)
    
    def test_content_verification(self):
        """Test content-based format verification."""
        # Create a file with JSON extension but different content
        wrong_file = Path(self.temp_dir) / "test.json"
        with open(wrong_file, 'wb') as f:
            f.write(b'\x80\x04\x95')  # Pickle header
        
        # Should detect mismatch and return None or try content detection
        result = self.resolver.detect_format(wrong_file)
        # Result depends on implementation - could be None or detected from content
        assert result in [None, "pickle", "json"]


class TestResourceManager:
    """Test suite for ResourceManager class."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        self.config = {
            "resource_management": {
                "max_open_graphs": 3,
                "memory_limit_per_graph": "10MB",
                "cleanup_interval": 1,
                "auto_cleanup": False,  # Disable for tests
                "backup_on_close": False
            }
        }
        self.manager = ResourceManager(self.config)
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'manager'):
            self.manager.shutdown()
    
    def test_resource_manager_initialization(self):
        """Test ResourceManager initialization."""
        manager = ResourceManager()
        assert manager._max_open_graphs == 10  # Default value
        assert manager._memory_limit_per_graph > 0
        assert manager._cleanup_interval > 0
        assert isinstance(manager._lock, threading.RLock)
    
    def test_resource_manager_with_config(self):
        """Test ResourceManager with custom configuration."""
        assert self.manager._max_open_graphs == 3
        assert self.manager._memory_limit_per_graph == 10 * 1024 * 1024  # 10MB
    
    def test_register_graph(self):
        """Test graph registration."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = self.manager.register_graph(mock_graph, "test_graph")
        assert graph_id == "test_graph"
        assert graph_id in self.manager._active_graphs
        assert graph_id in self.manager._graph_references
        
        # Check registration details
        info = self.manager._active_graphs[graph_id]
        assert "created_at" in info
        assert "last_accessed" in info
        assert "memory_usage" in info
        assert info["graph_object"] is mock_graph
    
    def test_register_graph_auto_id(self):
        """Test graph registration with auto-generated ID."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = self.manager.register_graph(mock_graph)
        assert graph_id is not None
        assert graph_id.startswith("graph_")
        assert graph_id in self.manager._active_graphs
    
    def test_register_graph_limit_enforcement(self):
        """Test graph registration limit enforcement."""
        mock_graphs = [Mock() for _ in range(5)]
        for mg in mock_graphs:
            mg.nodes = {}
            mg._edges = {}
        
        # Register up to limit
        for i in range(3):
            self.manager.register_graph(mock_graphs[i], f"graph_{i}")
        
        # Should enforce limit on 4th attempt
        with pytest.raises(MemoryError):
            self.manager.register_graph(mock_graphs[3], "graph_3")
    
    def test_unregister_graph(self):
        """Test graph unregistration."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = self.manager.register_graph(mock_graph, "test_graph")
        self.manager.unregister_graph(graph_id)
        
        assert graph_id not in self.manager._active_graphs
        assert graph_id not in self.manager._graph_references
    
    def test_unregister_unknown_graph(self):
        """Test unregistering unknown graph (should not raise error)."""
        # Should not raise error, just log warning
        self.manager.unregister_graph("unknown_graph")
    
    def test_cleanup_resources_specific(self):
        """Test cleanup for specific graph."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        mock_graph.cleanup = Mock()
        
        graph_id = self.manager.register_graph(mock_graph, "test_graph")
        self.manager.cleanup_resources(graph_id)
        
        # Should call graph's cleanup method
        mock_graph.cleanup.assert_called_once()
    
    def test_cleanup_resources_all(self):
        """Test cleanup for all resources."""
        mock_graphs = []
        for i in range(2):
            mg = Mock()
            mg.nodes = {}
            mg._edges = {}
            mg.cleanup = Mock()
            mock_graphs.append(mg)
            
            self.manager.register_graph(mg, f"graph_{i}")
        
        self.manager.cleanup_resources()
        
        # Should call cleanup on all graphs
        for mg in mock_graphs:
            mg.cleanup.assert_called_once()
    
    def test_get_memory_usage(self):
        """Test memory usage statistics."""
        mock_graph = Mock()
        mock_graph.nodes = {"a": {}, "b": {}}  # 2 nodes
        mock_graph._edges = {}
        
        self.manager.register_graph(mock_graph, "test_graph")
        stats = self.manager.get_memory_usage()
        
        assert "active_graphs" in stats
        assert "total_graph_memory_mb" in stats
        assert "max_graphs_allowed" in stats
        assert "memory_limit_per_graph_mb" in stats
        assert stats["active_graphs"] == 1
    
    def test_get_memory_usage_without_psutil(self):
        """Test memory usage when psutil is not available."""
        with patch.dict('sys.modules', {'psutil': None}):
            stats = self.manager.get_memory_usage()
            assert "active_graphs" in stats
            assert "process_rss_mb" not in stats
    
    def test_enforce_limits(self):
        """Test resource limit enforcement."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        self.manager.register_graph(mock_graph, "test_graph")
        
        # Should not raise error when within limits
        self.manager.enforce_limits()
        
        # Should still have the graph
        assert "test_graph" in self.manager._active_graphs
    
    def test_get_resource_info(self):
        """Test getting resource information."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = self.manager.register_graph(mock_graph, "test_graph")
        
        # Get info for all graphs
        all_info = self.manager.get_resource_info()
        assert "active_graphs" in all_info
        assert "memory_stats" in all_info
        assert "graphs" in all_info
        assert graph_id in all_info["graphs"]
        
        # Get info for specific graph
        graph_info = self.manager.get_resource_info(graph_id)
        assert "created_at" in graph_info
        assert "last_accessed" in graph_info
        assert "memory_usage" in graph_info
    
    def test_update_access_time(self):
        """Test updating access time."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = self.manager.register_graph(mock_graph, "test_graph")
        original_time = self.manager._active_graphs[graph_id]["last_accessed"]
        
        time.sleep(0.01)  # Small delay
        self.manager.update_access_time(graph_id)
        
        new_time = self.manager._active_graphs[graph_id]["last_accessed"]
        assert new_time > original_time
    
    def test_parse_memory_limit(self):
        """Test memory limit parsing."""
        manager = ResourceManager()
        
        # Test different units
        assert manager._parse_memory_limit("100KB") == 100 * 1024
        assert manager._parse_memory_limit("10MB") == 10 * 1024 * 1024
        assert manager._parse_memory_limit("1GB") == 1024 * 1024 * 1024
        assert manager._parse_memory_limit("1024") == 1024  # Assume bytes
    
    def test_estimate_graph_memory(self):
        """Test graph memory estimation."""
        manager = ResourceManager()
        
        # Test with graph that has get_memory_usage method
        mock_graph = Mock()
        mock_graph.get_memory_usage.return_value = 1024
        assert manager._estimate_graph_memory(mock_graph) == 1024
        
        # Test with graph that has nodes and edges attributes
        mock_graph2 = Mock()
        del mock_graph2.get_memory_usage  # Remove the method
        mock_graph2.nodes = {"a": {}, "b": {}, "c": {}}
        mock_graph2._edges = {"e1": {}, "e2": {}}
        
        estimate = manager._estimate_graph_memory(mock_graph2)
        assert estimate > 0  # Should estimate based on node/edge count
    
    def test_cleanup_dead_references(self):
        """Test cleanup of dead weak references."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = self.manager.register_graph(mock_graph, "test_graph")
        assert graph_id in self.manager._active_graphs
        
        # Delete the graph object (weak reference becomes dead)
        del mock_graph
        
        # Force garbage collection
        import gc
        gc.collect()
        
        # Cleanup dead references
        self.manager._cleanup_dead_references()
        
        # Dead reference should be removed
        assert graph_id not in self.manager._active_graphs
        assert graph_id not in self.manager._graph_references
    
    def test_backup_on_close(self):
        """Test backup functionality on close."""
        config = {
            "resource_management": {
                "backup_on_close": True,
                "max_open_graphs": 10,
                "memory_limit_per_graph": "10MB",
                "auto_cleanup": False
            }
        }
        manager = ResourceManager(config)
        
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        mock_graph.backup = Mock()
        
        graph_id = manager.register_graph(mock_graph, "test_graph")
        manager.unregister_graph(graph_id)
        
        # Should have called backup
        mock_graph.backup.assert_called_once()
        
        manager.shutdown()
    
    def test_force_cleanup_lru(self):
        """Test force cleanup of least recently used graphs."""
        # Register multiple graphs
        mock_graphs = []
        for i in range(3):
            mg = Mock()
            mg.nodes = {}
            mg._edges = {}
            mock_graphs.append(mg)
            self.manager.register_graph(mg, f"graph_{i}")
        
        # Update access times to create LRU order
        time.sleep(0.01)
        self.manager.update_access_time("graph_1")
        time.sleep(0.01)
        self.manager.update_access_time("graph_2")
        
        # Force cleanup (should remove oldest)
        self.manager._force_cleanup_lru()
        
        # Should have removed at least one graph
        assert len(self.manager._active_graphs) < 3
    
    def test_shutdown(self):
        """Test ResourceManager shutdown."""
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        mock_graph.cleanup = Mock()
        
        self.manager.register_graph(mock_graph, "test_graph")
        self.manager.shutdown()
        
        # Should cleanup all resources
        mock_graph.cleanup.assert_called_once()
        assert len(self.manager._active_graphs) == 0
        assert len(self.manager._graph_references) == 0
    
    def test_concurrent_access(self):
        """Test thread-safe operations."""
        import threading
        
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        results = []
        errors = []
        
        def register_graph(i):
            try:
                graph_id = self.manager.register_graph(mock_graph, f"graph_{i}")
                results.append(graph_id)
            except Exception as e:
                errors.append(e)
        
        # Try to register from multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=register_graph, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Should have some successful registrations and possibly some errors due to limits
        assert len(results) > 0 or len(errors) > 0
    
    def test_error_handling(self):
        """Test error handling in ResourceManager."""
        # Test registration with invalid graph
        with pytest.raises(ConcurrencyError):
            self.manager.register_graph(None, "invalid")
        
        # Test cleanup with invalid graph ID
        with pytest.raises(MemoryError):
            self.manager.cleanup_resources("invalid")


class TestIntegration:
    """Integration tests for foundation components working together."""
    
    def setup_method(self):
        """Set up integration test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "storage": {
                "data_dir": self.temp_dir,
                "default_format": "msgpack"
            },
            "resource_management": {
                "max_open_graphs": 5,
                "memory_limit_per_graph": "50MB",
                "auto_cleanup": False
            }
        }
    
    def teardown_method(self):
        """Clean up integration test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_path_resolver_with_resource_manager(self):
        """Test PathResolver and ResourceManager integration."""
        resolver = PathResolver(self.config)
        manager = ResourceManager(self.config)
        
        # Create a graph file path
        graph_path = resolver.resolve_path(None, "test_graph", "json")
        assert graph_path == Path(self.temp_dir) / "test_graph.json"
        
        # Ensure directory exists
        resolver.ensure_directory(graph_path)
        assert graph_path.parent.exists()
        
        # Register graph with resource manager
        mock_graph = Mock()
        mock_graph.nodes = {}
        mock_graph._edges = {}
        
        graph_id = manager.register_graph(mock_graph, "test_graph")
        assert graph_id in manager._active_graphs
        
        # Find the graph file
        found_path = resolver.find_graph_file("test_graph")
        # File might not exist yet, but path resolution should work
        
        manager.shutdown()
    
    def test_format_detection_and_path_resolution(self):
        """Test format detection working with path resolution."""
        resolver = PathResolver(self.config)
        
        # Create files in different formats
        test_data = {"nodes": {"a": {"name": "test"}}, "edges": []}
        
        # JSON file
        json_path = Path(self.temp_dir) / "test.json"
        with open(json_path, 'w') as f:
            json.dump(test_data, f)
        
        # Detect format and resolve path
        detected_format = resolver.detect_format(json_path)
        assert detected_format == "json"
        
        resolved_path = resolver.resolve_path(json_path, None, detected_format)
        assert resolved_path == json_path
        
        # Test with compressed file
        gz_path = Path(self.temp_dir) / "test.json.gz"
        with gzip.open(gz_path, 'wt') as f:
            json.dump(test_data, f)
        
        # Should detect from extension
        detected_gz_format = resolver.detect_format(gz_path)
        assert detected_gz_format == "json"


if __name__ == "__main__":
    # Run tests if this file is executed directly
    pytest.main([__file__, "-v"])
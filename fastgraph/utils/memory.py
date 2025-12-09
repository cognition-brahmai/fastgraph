"""
Memory utilities for FastGraph

This module provides memory estimation, monitoring, and optimization
utilities for efficient graph operations.
"""

import sys
import gc
import psutil
import time
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from ..exceptions import MemoryError


class MemoryUtils:
    """
    Utilities for memory monitoring and optimization.
    
    Provides memory estimation, monitoring, and optimization
    functionality for FastGraph operations.
    """
    
    def __init__(self):
        """Initialize memory utils."""
        self._baseline_memory = None
        self._memory_snapshots: List[Dict[str, Any]] = []
        self._process = psutil.Process()
    
    def get_memory_usage(self) -> Dict[str, int]:
        """
        Get current memory usage information.
        
        Returns:
            Dictionary with memory usage statistics in bytes
        """
        try:
            memory_info = self._process.memory_info()
            memory_stats = self._process.memory_stats()
            
            return {
                "rss": memory_info.rss,  # Resident Set Size
                "vms": memory_info.vms,  # Virtual Memory Size
                "shared": memory_info.shared or 0,
                "text": getattr(memory_stats, 'text', 0),
                "data": getattr(memory_stats, 'data', 0),
                "libs": getattr(memory_stats, 'libs', 0),
                "heap": getattr(memory_stats, 'heap', 0)
            }
        except Exception:
            # Fallback to sys methods
            return {
                "rss": 0,
                "vms": 0,
                "shared": 0,
                "text": 0,
                "data": 0,
                "libs": 0,
                "heap": 0
            }
    
    def get_system_memory(self) -> Dict[str, int]:
        """
        Get system-wide memory information.
        
        Returns:
            Dictionary with system memory statistics
        """
        try:
            virtual_memory = psutil.virtual_memory()
            return {
                "total": virtual_memory.total,
                "available": virtual_memory.available,
                "used": virtual_memory.used,
                "free": virtual_memory.free,
                "percentage": virtual_memory.percent
            }
        except Exception:
            return {
                "total": 0,
                "available": 0,
                "used": 0,
                "free": 0,
                "percentage": 0
            }
    
    def estimate_object_size(self, obj: Any) -> int:
        """
        Estimate memory usage of an object.
        
        Args:
            obj: Object to measure
            
        Returns:
            Estimated size in bytes
        """
        try:
            # For basic objects
            if isinstance(obj, (int, float, str, bool, type(None))):
                return sys.getsizeof(obj)
            
            # For containers, estimate recursively
            elif isinstance(obj, (list, tuple, set)):
                size = sys.getsizeof(obj)
                for item in obj:
                    size += self.estimate_object_size(item)
                return size
            
            elif isinstance(obj, dict):
                size = sys.getsizeof(obj)
                for key, value in obj.items():
                    size += self.estimate_object_size(key)
                    size += self.estimate_object_size(value)
                return size
            
            # For custom objects
            else:
                return sys.getsizeof(obj)
        
        except Exception:
            return sys.getsizeof(obj)
    
    def estimate_graph_memory(self, graph) -> Dict[str, int]:
        """
        Estimate memory usage of a FastGraph instance.
        
        Args:
            graph: FastGraph instance
            
        Returns:
            Dictionary with memory estimates by component
        """
        estimates = {}
        
        try:
            # Nodes memory
            if hasattr(graph, 'graph') and 'nodes' in graph.graph:
                nodes_size = 0
                for node_id, attrs in graph.graph['nodes'].items():
                    nodes_size += self.estimate_object_size(node_id)
                    nodes_size += self.estimate_object_size(attrs)
                estimates['nodes'] = nodes_size
            
            # Edges memory
            if hasattr(graph, '_edges'):
                edges_size = sum(self.estimate_object_size(edge) 
                               for edge in graph._edges.values())
                estimates['edges'] = edges_size
            
            # Indexes memory
            if hasattr(graph, 'index_manager'):
                indexes_size = 0
                for index in graph.index_manager.node_indexes.values():
                    indexes_size += self.estimate_object_size(index)
                estimates['indexes'] = indexes_size
            
            # Adjacency lists
            if hasattr(graph, '_out_edges'):
                out_edges_size = sum(self.estimate_object_size(edges) 
                                   for edges in graph._out_edges.values())
                estimates['out_edges'] = out_edges_size
            
            if hasattr(graph, '_in_edges'):
                in_edges_size = sum(self.estimate_object_size(edges) 
                                  for edges in graph._in_edges.values())
                estimates['in_edges'] = in_edges_size
            
            # Relation index
            if hasattr(graph, '_rel_index'):
                rel_index_size = sum(self.estimate_object_size(edges) 
                                   for edges in graph._rel_index.values())
                estimates['rel_index'] = rel_index_size
            
            # Metadata
            if hasattr(graph, 'graph') and 'metadata' in graph.graph:
                estimates['metadata'] = self.estimate_object_size(graph.graph['metadata'])
            
            # Total
            estimates['total'] = sum(estimates.values())
            
        except Exception as e:
            estimates['error'] = str(e)
            estimates['total'] = 0
        
        return estimates
    
    def memory_snapshot(self, label: str = "") -> Dict[str, Any]:
        """
        Take a memory snapshot for comparison.
        
        Args:
            label: Label for the snapshot
            
        Returns:
            Snapshot data
        """
        snapshot = {
            "timestamp": time.time(),
            "label": label,
            "memory_usage": self.get_memory_usage(),
            "system_memory": self.get_system_memory()
        }
        
        self._memory_snapshots.append(snapshot)
        return snapshot
    
    def get_memory_increase(self, from_snapshot: int = 0, to_snapshot: int = -1) -> Dict[str, int]:
        """
        Calculate memory increase between snapshots.
        
        Args:
            from_snapshot: Starting snapshot index
            to_snapshot: Ending snapshot index
            
        Returns:
            Memory increase by component
        """
        if len(self._memory_snapshots) < 2:
            return {}
        
        if to_snapshot == -1:
            to_snapshot = len(self._memory_snapshots) - 1
        
        if from_snapshot >= len(self._memory_snapshots) or to_snapshot >= len(self._memory_snapshots):
            return {}
        
        start_memory = self._memory_snapshots[from_snapshot]['memory_usage']
        end_memory = self._memory_snapshots[to_snapshot]['memory_usage']
        
        increase = {}
        for key in start_memory:
            increase[key] = end_memory.get(key, 0) - start_memory.get(key, 0)
        
        return increase
    
    def monitor_memory_limit(self, limit_mb: int, check_interval: float = 1.0):
        """
        Context manager to monitor memory usage limit.
        
        Args:
            limit_mb: Memory limit in MB
            check_interval: Check interval in seconds
        """
        return MemoryLimitContext(limit_mb, check_interval)
    
    def force_garbage_collection(self) -> Dict[str, Any]:
        """
        Force garbage collection and return results.
        
        Returns:
            Garbage collection statistics
        """
        # Collect before
        before_objects = len(gc.get_objects())
        
        # Force collection
        collected = gc.collect()
        
        # Collect after
        after_objects = len(gc.get_objects())
        
        return {
            "objects_before": before_objects,
            "objects_after": after_objects,
            "objects_collected": before_objects - after_objects,
            "garbage_cycles_collected": collected
        }
    
    def optimize_memory(self) -> Dict[str, Any]:
        """
        Optimize memory usage.
        
        Returns:
            Optimization results
        """
        results = {}
        
        # Force garbage collection
        results['garbage_collection'] = self.force_garbage_collection()
        
        # Clear memory snapshots if too many
        if len(self._memory_snapshots) > 100:
            results['snapshots_cleared'] = len(self._memory_snapshots)
            self._memory_snapshots = self._memory_snapshots[-10:]  # Keep last 10
        
        results['current_memory'] = self.get_memory_usage()
        return results
    
    def set_memory_baseline(self) -> None:
        """Set current memory as baseline reference."""
        self._baseline_memory = self.get_memory_usage()
    
    def get_memory_from_baseline(self) -> Dict[str, int]:
        """
        Get memory increase from baseline.
        
        Returns:
            Memory increase since baseline
        """
        if self._baseline_memory is None:
            self.set_memory_baseline()
            return {}
        
        current = self.get_memory_usage()
        increase = {}
        
        for key in self._baseline_memory:
            increase[key] = current.get(key, 0) - self._baseline_memory.get(key, 0)
        
        return increase
    
    def format_memory_size(self, bytes_size: int) -> str:
        """
        Format memory size in human-readable format.
        
        Args:
            bytes_size: Size in bytes
            
        Returns:
            Formatted string
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
    
    def get_memory_pressure(self) -> float:
        """
        Get memory pressure indicator (0.0 to 1.0).
        
        Returns:
            Memory pressure value
        """
        try:
            system_memory = self.get_system_memory()
            return system_memory.get('percentage', 0) / 100.0
        except Exception:
            return 0.0
    
    def is_memory_low(self, threshold_mb: int = 100) -> bool:
        """
        Check if available memory is low.
        
        Args:
            threshold_mb: Threshold in MB
            
        Returns:
            True if memory is low
        """
        try:
            system_memory = self.get_system_memory()
            available_mb = system_memory.get('available', 0) / (1024 * 1024)
            return available_mb < threshold_mb
        except Exception:
            return False


class MemoryLimitContext:
    """Context manager for monitoring memory limits."""
    
    def __init__(self, limit_mb: int, check_interval: float = 1.0):
        """
        Initialize memory limit context.
        
        Args:
            limit_mb: Memory limit in MB
            check_interval: Check interval in seconds
        """
        self.limit_bytes = limit_mb * 1024 * 1024
        self.check_interval = check_interval
        self.memory_utils = MemoryUtils()
        self.start_memory = None
        self.last_check = 0
    
    def __enter__(self):
        """Enter context."""
        self.start_memory = self.memory_utils.get_memory_usage()
        self.last_check = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        # Memory limit exceeded will raise MemoryError before we get here
        pass
    
    def check_limit(self):
        """Check if memory limit is exceeded."""
        current_time = time.time()
        
        if current_time - self.last_check >= self.check_interval:
            current_memory = self.memory_utils.get_memory_usage()
            memory_usage = current_memory.get('rss', 0)
            
            if memory_usage > self.limit_bytes:
                raise MemoryError(
                    f"Memory limit exceeded: {self.memory_utils.format_memory_size(memory_usage)} "
                    f"> {self.memory_utils.format_memory_size(self.limit_bytes)}",
                    operation="memory_limit_check",
                    memory_required=memory_usage
                )
            
            self.last_check = current_time


# Global memory utilities instance
_global_memory_utils: Optional[MemoryUtils] = None


def get_global_memory_utils() -> MemoryUtils:
    """
    Get global memory utilities instance.
    
    Returns:
        MemoryUtils instance
    """
    global _global_memory_utils
    if _global_memory_utils is None:
        _global_memory_utils = MemoryUtils()
    return _global_memory_utils


def estimate_memory_usage(obj: Any) -> int:
    """
    Estimate memory usage of an object.
    
    Args:
        obj: Object to measure
        
    Returns:
        Estimated size in bytes
    """
    return get_global_memory_utils().estimate_object_size(obj)


def memory_monitor(limit_mb: int = 1000):
    """
    Decorator for memory monitoring.
    
    Args:
        limit_mb: Memory limit in MB
        
    Returns:
        Decorated function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            memory_utils = get_global_memory_utils()
            
            with memory_utils.monitor_memory_limit(limit_mb):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def check_memory_usage(threshold_mb: int = 500) -> bool:
    """
    Check if memory usage exceeds threshold.
    
    Args:
        threshold_mb: Threshold in MB
        
    Returns:
        True if threshold exceeded
    """
    memory_utils = get_global_memory_utils()
    memory_usage = memory_utils.get_memory_usage()
    usage_mb = memory_usage.get('rss', 0) / (1024 * 1024)
    return usage_mb > threshold_mb


def optimize_graph_memory(graph) -> Dict[str, Any]:
    """
    Optimize memory usage of a graph.
    
    Args:
        graph: FastGraph instance
        
    Returns:
        Optimization results
    """
    memory_utils = get_global_memory_utils()
    
    # Clear caches
    if hasattr(graph, 'clear_cache'):
        graph.clear_cache()
    
    # Force garbage collection
    gc_results = memory_utils.force_garbage_collection()
    
    # Get current memory estimate
    before_memory = memory_utils.estimate_graph_memory(graph)
    
    # Optimize indexes if needed
    if hasattr(graph, 'index_manager'):
        graph.index_manager.optimize_indexes(graph.graph.get('nodes', {}))
    
    # Get memory after optimization
    after_memory = memory_utils.estimate_graph_memory(graph)
    
    return {
        "garbage_collection": gc_results,
        "memory_before": before_memory,
        "memory_after": after_memory,
        "memory_saved": {
            key: before_memory.get(key, 0) - after_memory.get(key, 0)
            for key in before_memory
        }
    }
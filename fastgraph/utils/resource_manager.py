"""
Resource management utilities for FastGraph

This module provides resource tracking, lifecycle management, and
cleanup capabilities for FastGraph instances.
"""

import gc
import time
import threading
import weakref
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
import logging

from ..types import MemoryStats, PerformanceMetrics
from ..exceptions import MemoryError, ConcurrencyError


logger = logging.getLogger(__name__)


class ResourceManager:
    """
    Manages graph lifecycle and resources for FastGraph.
    
    Provides resource tracking, automatic cleanup, memory monitoring,
    and enforcement of resource limits across multiple graph instances.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize ResourceManager with configuration.
        
        Args:
            config: Configuration dictionary containing resource settings
        """
        self.config = config or {}
        
        # Resource tracking
        self._active_graphs: Dict[str, Dict[str, Any]] = {}
        self._graph_references: Dict[str, weakref.ref] = {}
        self._lock = threading.RLock()
        
        # Configuration
        self._max_open_graphs = self.config.get("resource_management", {}).get("max_open_graphs", 10)
        self._memory_limit_per_graph = self._parse_memory_limit(
            self.config.get("resource_management", {}).get("memory_limit_per_graph", "100MB")
        )
        self._cleanup_interval = self.config.get("resource_management", {}).get("cleanup_interval", 300)
        self._auto_cleanup = self.config.get("resource_management", {}).get("auto_cleanup", True)
        self._backup_on_close = self.config.get("resource_management", {}).get("backup_on_close", False)
        
        # Cleanup tracking
        self._last_cleanup = time.time()
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()
        
        # Start cleanup thread if auto-cleanup is enabled
        if self._auto_cleanup:
            self._start_cleanup_thread()
    
    def register_graph(self, graph: Any, graph_id: str = None) -> str:
        """
        Register a graph instance for resource tracking.
        
        Args:
            graph: FastGraph instance to register
            graph_id: Optional unique identifier for the graph
            
        Returns:
            Unique graph identifier
            
        Raises:
            MemoryError: If resource limits would be exceeded
            ConcurrencyError: If graph registration fails
        """
        try:
            with self._lock:
                # Generate ID if not provided
                if not graph_id:
                    graph_id = f"graph_{len(self._active_graphs)}_{int(time.time())}"
                
                # Check if we're at the limit
                if len(self._active_graphs) >= self._max_open_graphs:
                    # Try to cleanup first
                    self._cleanup_dead_references()
                    if len(self._active_graphs) >= self._max_open_graphs:
                        raise MemoryError(f"Maximum open graphs limit ({self._max_open_graphs}) reached",
                                       operation="register_graph")
                
                # Register the graph
                self._active_graphs[graph_id] = {
                    "created_at": time.time(),
                    "last_accessed": time.time(),
                    "memory_usage": self._estimate_graph_memory(graph),
                    "graph_object": graph,
                }
                
                # Store weak reference
                self._graph_references[graph_id] = weakref.ref(graph, self._graph_deleted_callback)
                
                logger.info(f"Registered graph {graph_id}")
                return graph_id
                
        except Exception as e:
            if isinstance(e, (MemoryError, ConcurrencyError)):
                raise
            raise ConcurrencyError(f"Failed to register graph: {e}", operation="register_graph")
    
    def unregister_graph(self, graph_id: str) -> None:
        """
        Unregister a graph instance and cleanup resources.
        
        Args:
            graph_id: Graph identifier to unregister
            
        Raises:
            ConcurrencyError: If unregistration fails
        """
        try:
            with self._lock:
                if graph_id in self._active_graphs:
                    graph_info = self._active_graphs[graph_id]
                    
                    # Perform backup if enabled
                    if self._backup_on_close and hasattr(graph_info["graph_object"], 'backup'):
                        try:
                            graph_info["graph_object"].backup()
                        except Exception as e:
                            logger.warning(f"Backup failed for graph {graph_id}: {e}")
                    
                    # Remove from tracking
                    del self._active_graphs[graph_id]
                    if graph_id in self._graph_references:
                        del self._graph_references[graph_id]
                    
                    logger.info(f"Unregistered graph {graph_id}")
                else:
                    logger.warning(f"Attempted to unregister unknown graph {graph_id}")
                    
        except Exception as e:
            raise ConcurrencyError(f"Failed to unregister graph {graph_id}: {e}", 
                                operation="unregister_graph")
    
    def cleanup_resources(self, graph_id: Optional[str] = None) -> None:
        """
        Cleanup resources for a specific graph or all graphs.
        
        Args:
            graph_id: Specific graph to cleanup, or None for all
            
        Raises:
            MemoryError: If cleanup fails
        """
        try:
            with self._lock:
                if graph_id:
                    self._cleanup_graph_resources(graph_id)
                else:
                    self._cleanup_all_resources()
                    
        except Exception as e:
            raise MemoryError(f"Resource cleanup failed: {e}", operation="cleanup_resources")
    
    def get_memory_usage(self) -> MemoryStats:
        """
        Get current memory usage statistics.
        
        Returns:
            Dictionary with memory usage information
        """
        try:
            import psutil
            process = psutil.Process()
            
            # Get system memory info
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Calculate graph-specific memory
            total_graph_memory = sum(
                info["memory_usage"] for info in self._active_graphs.values()
            )
            
            return {
                "process_rss_mb": memory_info.rss / 1024 / 1024,
                "process_vms_mb": memory_info.vms / 1024 / 1024,
                "memory_percent": memory_percent,
                "active_graphs": len(self._active_graphs),
                "total_graph_memory_mb": total_graph_memory / 1024 / 1024,
                "avg_graph_memory_mb": (total_graph_memory / len(self._active_graphs) / 1024 / 1024) 
                                    if self._active_graphs else 0,
                "max_graphs_allowed": self._max_open_graphs,
                "memory_limit_per_graph_mb": self._memory_limit_per_graph / 1024 / 1024,
            }
            
        except ImportError:
            # Fallback if psutil not available
            logger.warning("psutil not available, limited memory information")
            return {
                "active_graphs": len(self._active_graphs),
                "total_graph_memory_mb": 0,
                "max_graphs_allowed": self._max_open_graphs,
                "memory_limit_per_graph_mb": self._memory_limit_per_graph / 1024 / 1024,
            }
    
    def enforce_limits(self) -> None:
        """
        Enforce resource limits and cleanup if necessary.
        
        Raises:
            MemoryError: If limits are exceeded and cannot be resolved
        """
        try:
            with self._lock:
                # Check graph count limit
                if len(self._active_graphs) > self._max_open_graphs:
                    logger.warning(f"Graph count limit exceeded: {len(self._active_graphs)}/{self._max_open_graphs}")
                    self._cleanup_dead_references()
                    
                    if len(self._active_graphs) > self._max_open_graphs:
                        # Force cleanup of least recently used graphs
                        self._force_cleanup_lru()
                
                # Check memory limits
                memory_stats = self.get_memory_usage()
                for graph_id, info in self._active_graphs.items():
                    if info["memory_usage"] > self._memory_limit_per_graph:
                        logger.warning(f"Graph {graph_id} exceeds memory limit: {info['memory_usage']/1024/1024:.1f}MB")
                        # Could implement memory reduction strategies here
                
                # Update last cleanup time
                self._last_cleanup = time.time()
                
        except Exception as e:
            raise MemoryError(f"Failed to enforce resource limits: {e}", operation="enforce_limits")
    
    def get_resource_info(self, graph_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get resource information for a specific graph or all graphs.
        
        Args:
            graph_id: Specific graph ID, or None for all graphs
            
        Returns:
            Resource information dictionary
        """
        with self._lock:
            if graph_id:
                if graph_id in self._active_graphs:
                    return self._active_graphs[graph_id].copy()
                else:
                    return {}
            else:
                return {
                    "active_graphs": len(self._active_graphs),
                    "memory_stats": self.get_memory_usage(),
                    "graphs": {
                        gid: {
                            "created_at": info["created_at"],
                            "last_accessed": info["last_accessed"],
                            "memory_usage": info["memory_usage"],
                        }
                        for gid, info in self._active_graphs.items()
                    }
                }
    
    def update_access_time(self, graph_id: str) -> None:
        """Update the last accessed time for a graph."""
        with self._lock:
            if graph_id in self._active_graphs:
                self._active_graphs[graph_id]["last_accessed"] = time.time()
    
    def _parse_memory_limit(self, limit_str: str) -> int:
        """Parse memory limit string to bytes."""
        limit_str = limit_str.upper().strip()
        
        if limit_str.endswith('KB'):
            return int(limit_str[:-2]) * 1024
        elif limit_str.endswith('MB'):
            return int(limit_str[:-2]) * 1024 * 1024
        elif limit_str.endswith('GB'):
            return int(limit_str[:-2]) * 1024 * 1024 * 1024
        else:
            # Assume bytes if no unit
            return int(limit_str)
    
    def _estimate_graph_memory(self, graph: Any) -> int:
        """Estimate memory usage of a graph."""
        try:
            # Try to get size from graph if available
            if hasattr(graph, 'get_memory_usage'):
                return graph.get_memory_usage()
            
            # Rough estimation based on graph attributes
            size = 0
            if hasattr(graph, 'nodes'):
                size += len(getattr(graph, 'nodes', {})) * 100  # Rough estimate per node
            if hasattr(graph, '_edges'):
                size += len(getattr(graph, '_edges', {})) * 200  # Rough estimate per edge
            
            return size
            
        except Exception:
            return 0  # Fallback
    
    def _cleanup_dead_references(self) -> None:
        """Cleanup graphs that have been garbage collected."""
        dead_ids = []
        
        for graph_id, ref in self._graph_references.items():
            if ref() is None:
                dead_ids.append(graph_id)
        
        for graph_id in dead_ids:
            logger.debug(f"Cleaning up dead reference for {graph_id}")
            if graph_id in self._active_graphs:
                del self._active_graphs[graph_id]
            if graph_id in self._graph_references:
                del self._graph_references[graph_id]
    
    def _cleanup_graph_resources(self, graph_id: str) -> None:
        """Cleanup resources for a specific graph."""
        if graph_id in self._active_graphs:
            graph_info = self._active_graphs[graph_id]
            graph = graph_info.get("graph_object")
            
            # Trigger graph-specific cleanup if available
            if hasattr(graph, 'cleanup'):
                try:
                    graph.cleanup()
                except Exception as e:
                    logger.warning(f"Graph cleanup failed for {graph_id}: {e}")
    
    def _cleanup_all_resources(self) -> None:
        """Cleanup resources for all graphs."""
        # First cleanup dead references
        self._cleanup_dead_references()
        
        # Then cleanup each active graph
        for graph_id in list(self._active_graphs.keys()):
            self._cleanup_graph_resources(graph_id)
        
        # Force garbage collection
        gc.collect()
    
    def _force_cleanup_lru(self) -> None:
        """Force cleanup of least recently used graphs."""
        if not self._active_graphs:
            return
        
        # Sort by last accessed time
        sorted_graphs = sorted(
            self._active_graphs.items(),
            key=lambda x: x[1]["last_accessed"]
        )
        
        # Remove oldest graphs until under limit
        to_remove = len(self._active_graphs) - self._max_open_graphs + 1
        for i in range(min(to_remove, len(sorted_graphs))):
            graph_id = sorted_graphs[i][0]
            logger.warning(f"Force cleanup of LRU graph: {graph_id}")
            self.unregister_graph(graph_id)
    
    def _graph_deleted_callback(self, ref: weakref.ref) -> None:
        """Callback when a graph is garbage collected."""
        # Find the graph ID by reference
        graph_id = None
        for gid, graph_ref in self._graph_references.items():
            if graph_ref is ref:
                graph_id = gid
                break
        
        if graph_id:
            logger.debug(f"Graph {graph_id} garbage collected")
            with self._lock:
                if graph_id in self._active_graphs:
                    del self._active_graphs[graph_id]
                if graph_id in self._graph_references:
                    del self._graph_references[graph_id]
    
    def _start_cleanup_thread(self) -> None:
        """Start background cleanup thread."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_worker,
                daemon=True,
                name="ResourceManager-Cleanup"
            )
            self._cleanup_thread.start()
    
    def _cleanup_worker(self) -> None:
        """Background cleanup worker thread."""
        while not self._stop_cleanup.wait(self._cleanup_interval):
            try:
                self._cleanup_dead_references()
                self.enforce_limits()
            except Exception as e:
                logger.error(f"Cleanup worker error: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the resource manager and cleanup all resources."""
        logger.info("Shutting down ResourceManager")
        
        # Stop cleanup thread
        self._stop_cleanup.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        
        # Cleanup all resources
        try:
            self._cleanup_all_resources()
        except Exception as e:
            logger.error(f"Final cleanup failed: {e}")
        
        # Clear all tracking
        with self._lock:
            self._active_graphs.clear()
            self._graph_references.clear()
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            self.shutdown()
        except Exception:
            pass  # Ignore errors during destruction
    
    def __repr__(self) -> str:
        """String representation."""
        return f"ResourceManager(active_graphs={len(self._active_graphs)}, max={self._max_open_graphs})"
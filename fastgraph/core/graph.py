"""
Main FastGraph class implementation

This module contains the core FastGraph class that integrates all
components into a high-performance in-memory graph database.
"""

from __future__ import annotations
import time
import threading
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple, Iterator, Callable, Union
from pathlib import Path
from collections import defaultdict

from ..types import (
    NodeId, NodeAttrs, EdgeKey, EdgeAttrs, NodeBatch, EdgeBatch,
    NodeFilter, EdgeFilter, NodeResult, EdgeResult, Stats
)
from ..config.manager import ConfigManager
from ..exceptions import (
    FastGraphError, NodeNotFoundError, EdgeNotFoundError, 
    IndexingError, PersistenceError, ValidationError
)
from .edge import Edge
from .subgraph import SubgraphView
from .indexing import IndexManager
from .traversal import TraversalOperations
from .persistence import PersistenceManager


class FastGraph:
    """
    FastGraph v2: High-Performance In-Memory Graph Database
    
    Core features:
    - O(1) edge lookups using adjacency lists
    - Automatic indexing for fast queries  
    - Batch operations for bulk data
    - Memory-efficient subgraph views
    - Compressed persistence with msgpack
    - Configuration-driven setup
    - Thread-safe operations
    - Query result caching
    """
    
    def __init__(self, name: str = "fastgraph", config: Union[str, Path, Dict, ConfigManager] = None,
                 **kwargs):
        """
        Initialize FastGraph instance.
        
        Args:
            name: Graph name for identification
            config: Configuration (file path, dict, or ConfigManager)
            **kwargs: Additional configuration parameters to override
            
        Example:
            # Using default config
            graph = FastGraph()
            
            # Using config file
            graph = FastGraph(config="my_config.yaml")
            
            # Using config dict
            graph = FastGraph(config={"memory": {"query_cache_size": 256}})
            
            # Using direct parameters
            graph = FastGraph(name="my_graph", auto_index=True, cache_size=128)
        """
        # Load configuration
        self.config = self._load_config(config, kwargs)
        
        # Initialize core attributes
        self.name = name or self.config.get("engine.name", "fastgraph")
        
        # Core storage
        self.graph: Dict[str, Any] = {
            "nodes": {},
            "metadata": {
                "name": self.name,
                "created_at": time.time(),
                "version": self.config.get("engine.version", "2.0.0")
            }
        }
        
        # Optimization: Edge hash map for O(1) lookup
        self._edges: Dict[EdgeKey, Edge] = {}
        
        # Optimization: Adjacency lists for fast traversal
        self._out_edges: Dict[NodeId, List[Edge]] = defaultdict(list)
        self._in_edges: Dict[NodeId, List[Edge]] = defaultdict(list)
        
        # Optimization: Relation index for fast rel queries
        self._rel_index: Dict[str, List[Edge]] = defaultdict(list)
        
        # Component managers
        self.index_manager = IndexManager(
            auto_index=self.config.get("indexing.auto_index", True)
        )
        self.traversal_ops = TraversalOperations(self)
        self.persistence_manager = PersistenceManager(self._lock)
        
        # Subgraph views (no data duplication)
        self._subgraph_views: Dict[str, SubgraphView] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Query cache
        self._setup_cache(
            cache_size=self.config.get("memory.query_cache_size", 128),
            ttl=self.config.get("memory.cache_ttl", 3600)
        )
        
        # Performance metrics
        self._metrics = {
            "nodes_added": 0,
            "edges_added": 0,
            "queries_executed": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    def _load_config(self, config: Union[str, Path, Dict, ConfigManager], 
                    overrides: Dict) -> ConfigManager:
        """
        Load and process configuration.
        
        Args:
            config: Configuration source
            overrides: Parameter overrides
            
        Returns:
            Loaded configuration manager
        """
        if isinstance(config, ConfigManager):
            cfg_manager = config
        elif isinstance(config, (str, Path)):
            cfg_manager = ConfigManager(config_file=config)
        elif isinstance(config, dict):
            cfg_manager = ConfigManager(config_dict=config)
        else:
            cfg_manager = ConfigManager()
        
        # Apply parameter overrides
        if overrides:
            for key, value in overrides.items():
                cfg_manager.set(key, value)
        
        return cfg_manager
    
    def _setup_cache(self, cache_size: int, ttl: int) -> None:
        """
        Setup LRU cache for queries.
        
        Args:
            cache_size: Maximum cache size
            ttl: Cache time-to-live in seconds
        """
        if cache_size > 0:
            self.find_nodes = lru_cache(maxsize=cache_size)(self._find_nodes_impl)
            self._cache_enabled = True
            self._cache_ttl = ttl
        else:
            self.find_nodes = self._find_nodes_no_cache
            self._cache_enabled = False
    
    def clear_cache(self) -> None:
        """Clear query cache."""
        if self._cache_enabled and hasattr(self.find_nodes, 'cache_clear'):
            self.find_nodes.cache_clear()
    
    # ==================== BATCH OPERATIONS ====================
    
    def add_nodes_batch(self, nodes: NodeBatch) -> None:
        """
        Add multiple nodes in one operation (much faster).
        
        Args:
            nodes: List of (node_id, attributes) tuples
            
        Example:
            graph.add_nodes_batch([
                ("A", {"name": "Alice", "age": 25}),
                ("B", {"name": "Bob", "age": 27})
            ])
        """
        with self._lock:
            for node_id, attrs in nodes:
                self.graph["nodes"][node_id] = dict(attrs)
                self.index_manager.update_node_index(node_id, {}, attrs)
            
            self._metrics["nodes_added"] += len(nodes)
            self.clear_cache()
    
    def add_edges_batch(self, edges: EdgeBatch) -> None:
        """
        Add multiple edges in one operation.
        
        Args:
            edges: List of (src, dst, rel, attrs) tuples
            
        Example:
            graph.add_edges_batch([
                ("A", "B", "friends", {"since": 2021}),
                ("B", "C", "works_at", {"title": "Engineer"})
            ])
        """
        with self._lock:
            for edge_data in edges:
                src, dst, rel = edge_data[0], edge_data[1], edge_data[2]
                attrs = edge_data[3] if len(edge_data) > 3 else {}
                self._add_edge_internal(src, dst, rel, attrs)
            
            self._metrics["edges_added"] += len(edges)
            self.clear_cache()
    
    # ==================== NODE OPERATIONS ====================
    
    def add_node(self, node_id: NodeId, **attrs: Any) -> None:
        """
        Add or update a node.
        
        Args:
            node_id: Unique node identifier
            **attrs: Node attributes
            
        Example:
            graph.add_node("A", name="Alice", age=25, type="Person")
        """
        with self._lock:
            old_attrs = self.graph["nodes"].get(node_id, {})
            self.graph["nodes"][node_id] = dict(attrs)
            
            # Update indexes
            self.index_manager.update_node_index(node_id, old_attrs, attrs)
            
            self._metrics["nodes_added"] += 1
            self.clear_cache()
    
    def get_node(self, node_id: NodeId) -> Optional[NodeAttrs]:
        """
        O(1) node lookup.
        
        Args:
            node_id: Node identifier
            
        Returns:
            Node attributes or None if not found
        """
        return self.graph["nodes"].get(node_id)
    
    def remove_node(self, node_id: NodeId) -> None:
        """
        Remove node and all connected edges.
        
        Args:
            node_id: Node identifier to remove
        """
        with self._lock:
            if node_id not in self.graph["nodes"]:
                return
            
            # Remove from indexes
            attrs = self.graph["nodes"][node_id]
            self.index_manager.remove_from_indexes(node_id, attrs)
            
            # Remove all edges connected to this node
            edges_to_remove = (list(self._out_edges.get(node_id, [])) + 
                             list(self._in_edges.get(node_id, [])))
            for edge in edges_to_remove:
                self._remove_edge_internal(edge)
            
            # Remove node
            del self.graph["nodes"][node_id]
            self.clear_cache()
    
    # ==================== EDGE OPERATIONS ====================
    
    def _add_edge_internal(self, src: NodeId, dst: NodeId, rel: str, attrs: EdgeAttrs) -> None:
        """
        Internal edge addition without lock.
        
        Args:
            src: Source node ID
            dst: Destination node ID
            rel: Edge relation
            attrs: Edge attributes
        """
        if src not in self.graph["nodes"]:
            raise NodeNotFoundError(src)
        if dst not in self.graph["nodes"]:
            raise NodeNotFoundError(dst)
        
        edge = Edge(src, dst, rel, attrs)
        key = edge.key()
        
        # Store in hash map
        self._edges[key] = edge
        
        # Update adjacency lists
        self._out_edges[src].append(edge)
        self._in_edges[dst].append(edge)
        
        # Update relation index
        self._rel_index[rel].append(edge)
    
    def add_edge(self, src: NodeId, dst: NodeId, rel: str, **attrs: Any) -> None:
        """
        Add an edge - O(1) operation.
        
        Args:
            src: Source node ID
            dst: Destination node ID
            rel: Edge relation type
            **attrs: Edge attributes
            
        Example:
            graph.add_edge("A", "B", "friends", since=2021, close=True)
        """
        with self._lock:
            self._add_edge_internal(src, dst, rel, attrs)
            self._metrics["edges_added"] += 1
            self.clear_cache()
    
    def get_edge(self, src: NodeId, dst: NodeId, rel: str) -> Optional[Edge]:
        """
        O(1) edge lookup by key.
        
        Args:
            src: Source node ID
            dst: Destination node ID
            rel: Edge relation
            
        Returns:
            Edge object or None if not found
        """
        return self._edges.get((src, dst, rel))
    
    def _remove_edge_internal(self, edge: Edge) -> None:
        """
        Internal edge removal without lock.
        
        Args:
            edge: Edge to remove
        """
        key = edge.key()
        if key in self._edges:
            del self._edges[key]
            
            # Update adjacency lists
            if edge.src in self._out_edges:
                try:
                    self._out_edges[edge.src].remove(edge)
                except ValueError:
                    pass
            
            if edge.dst in self._in_edges:
                try:
                    self._in_edges[edge.dst].remove(edge)
                except ValueError:
                    pass
            
            # Update relation index
            if edge.rel in self._rel_index:
                try:
                    self._rel_index[edge.rel].remove(edge)
                except ValueError:
                    pass
    
    def remove_edge(self, src: Optional[NodeId] = None, dst: Optional[NodeId] = None,
                   rel: Optional[str] = None) -> int:
        """
        Remove edges matching filters.
        
        Args:
            src: Optional source node filter
            dst: Optional destination node filter
            rel: Optional relation filter
            
        Returns:
            Number of edges removed
        """
        with self._lock:
            edges_to_remove = []
            
            # Use indexes for faster filtering
            if rel and src:
                # Use rel index + filter by src
                edges_to_remove = [e for e in self._rel_index.get(rel, []) if e.src == src]
                if dst:
                    edges_to_remove = [e for e in edges_to_remove if e.dst == dst]
            elif rel:
                edges_to_remove = list(self._rel_index.get(rel, []))
            elif src:
                edges_to_remove = list(self._out_edges.get(src, []))
                if dst:
                    edges_to_remove = [e for e in edges_to_remove if e.dst == dst]
            elif dst:
                edges_to_remove = list(self._in_edges.get(dst, []))
            
            for edge in edges_to_remove:
                self._remove_edge_internal(edge)
            
            self.clear_cache()
            return len(edges_to_remove)
    
    # ==================== GRAPH TRAVERSAL ====================
    
    def neighbors_out(self, node_id: NodeId, rel: Optional[str] = None) -> List[Tuple[NodeId, Edge]]:
        """
        Get outgoing neighbors - O(degree) using adjacency list.
        
        Args:
            node_id: Node ID
            rel: Optional relation filter
            
        Returns:
            List of (neighbor_id, edge) tuples
        """
        return self.traversal_ops.neighbors_out(node_id, rel)
    
    def neighbors_in(self, node_id: NodeId, rel: Optional[str] = None) -> List[Tuple[NodeId, Edge]]:
        """
        Get incoming neighbors - O(degree) using adjacency list.
        
        Args:
            node_id: Node ID
            rel: Optional relation filter
            
        Returns:
            List of (neighbor_id, edge) tuples
        """
        return self.traversal_ops.neighbors_in(node_id, rel)
    
    def neighbors(self, node_id: NodeId, rel: Optional[str] = None) -> List[Tuple[NodeId, Edge]]:
        """
        Get all neighbors (both directions).
        
        Args:
            node_id: Node ID
            rel: Optional relation filter
            
        Returns:
            List of (neighbor_id, edge) tuples
        """
        return self.traversal_ops.neighbors(node_id, rel)
    
    def degree(self, node_id: NodeId) -> Tuple[int, int, int]:
        """
        Returns (out_degree, in_degree, total_degree).
        
        Args:
            node_id: Node ID
            
        Returns:
            Tuple of degree counts
        """
        return self.traversal_ops.degree(node_id)
    
    # ==================== SEARCH ====================
    
    def _find_nodes_impl(self, **filters: Any) -> Tuple[Tuple[NodeId, NodeAttrs], ...]:
        """
        Cacheable implementation.
        
        Args:
            **filters: Node attribute filters
            
        Returns:
            Tuple of (node_id, attributes) pairs
        """
        # Convert dict filters to tuple for caching
        filter_items = tuple(sorted(filters.items()))
        return tuple(self._find_nodes_no_cache(dict(filter_items)))
    
    def _find_nodes_no_cache(self, filters: Dict[str, Any]) -> List[Tuple[NodeId, NodeAttrs]]:
        """
        Actual search implementation.
        
        Args:
            filters: Node attribute filters
            
        Returns:
            List of (node_id, attributes) pairs
        """
        if not filters:
            return list(self.graph["nodes"].items())
        
        # Use indexes if available
        indexed_keys = [k for k in filters.keys() if self.index_manager.has_index(k)]
        if indexed_keys:
            # Use best index (most selective)
            best_key = min(indexed_keys, 
                          key=lambda k: len(self.index_manager.query_by_index(k, filters[k])))
            candidates = self.index_manager.query_by_index(best_key, filters[best_key])
            
            results = []
            for nid in candidates:
                attrs = self.graph["nodes"].get(nid)
                if attrs and all(attrs.get(k) == v for k, v in filters.items()):
                    results.append((nid, attrs))
            return results
        
        # Full scan
        return [(nid, attrs) for nid, attrs in self.graph["nodes"].items()
                if all(attrs.get(k) == v for k, v in filters.items())]
    
    def find_nodes(self, **filters: Any) -> NodeResult:
        """
        Find nodes matching attribute filters.
        
        Args:
            **filters: Attribute filters
            
        Returns:
            List of (node_id, attributes) pairs
            
        Example:
            graph.find_nodes(type="Person", age=25)
        """
        self._metrics["queries_executed"] += 1
        
        if self._cache_enabled and hasattr(self.find_nodes, 'cache_info'):
            cache_info = self.find_nodes.cache_info()
            if cache_info.hits > 0:
                self._metrics["cache_hits"] += 1
            else:
                self._metrics["cache_misses"] += 1
        
        return list(self.find_nodes(**filters))
    
    def find_edges(self, src: Optional[NodeId] = None, dst: Optional[NodeId] = None,
                  rel: Optional[str] = None, **attr_filters) -> EdgeResult:
        """
        Optimized edge search using indexes.
        
        Args:
            src: Optional source node filter
            dst: Optional destination node filter
            rel: Optional relation filter
            **attr_filters: Edge attribute filters
            
        Returns:
            List of matching edges
        """
        # Use adjacency lists and rel index for fast filtering
        candidates = None
        
        if rel:
            candidates = self._rel_index.get(rel, [])
        elif src:
            candidates = self._out_edges.get(src, [])
        elif dst:
            candidates = self._in_edges.get(dst, [])
        else:
            candidates = self._edges.values()
        
        # Apply additional filters
        results = list(candidates)
        if src and rel is None:
            results = [e for e in results if e.src == src]
        if dst and rel is None:
            results = [e for e in results if e.dst == dst]
        
        # Apply attribute filters
        for k, v in attr_filters.items():
            results = [e for e in results if e.get_attribute(k) == v]
        
        return results
    
    # ==================== INDEXING ====================
    
    def build_node_index(self, attr_name: str) -> None:
        """
        Build index on attribute.
        
        Args:
            attr_name: Attribute name to index
        """
        with self._lock:
            self.index_manager.create_node_index(attr_name, self.graph["nodes"])
    
    def drop_node_index(self, attr_name: str) -> None:
        """
        Drop an index.
        
        Args:
            attr_name: Index name to drop
        """
        with self._lock:
            self.index_manager.drop_node_index(attr_name)
    
    def get_index_stats(self) -> Dict[str, Any]:
        """
        Get index statistics.
        
        Returns:
            Dictionary of index statistics
        """
        return self.index_manager.get_index_statistics()
    
    # ==================== SUBGRAPHS ====================
    
    def create_subgraph_view(self, name: str,
                            node_filter: Optional[NodeFilter] = None) -> SubgraphView:
        """
        Create memory-efficient subgraph view (no data duplication).
        
        Args:
            name: View name
            node_filter: Optional function to filter nodes
            
        Returns:
            SubgraphView instance
        """
        node_filter = node_filter or (lambda nid, attrs: True)
        node_ids = {nid for nid, attrs in self.graph["nodes"].items() 
                   if node_filter(nid, attrs)}
        view = SubgraphView(self, node_ids)
        self._subgraph_views[name] = view
        return view
    
    def get_subgraph_view(self, name: str) -> Optional[SubgraphView]:
        """
        Get subgraph view.
        
        Args:
            name: View name
            
        Returns:
            SubgraphView instance or None
        """
        return self._subgraph_views.get(name)
    
    # ==================== PERSISTENCE ====================
    
    def save(self, path: Union[str, Path], format: str = "msgpack") -> None:
        """
        Save graph with compression.
        
        Args:
            path: File path to save to
            format: File format ("msgpack", "pickle", "json")
        """
        data = {
            "nodes": self.graph["nodes"],
            "_edges": self._edges,
            "metadata": self.graph["metadata"],
            "node_indexes": self.index_manager.node_indexes
        }
        
        self.persistence_manager.save(data, path, format)
    
    def load(self, path: Union[str, Path], format: str = "msgpack") -> None:
        """
        Load graph from file.
        
        Args:
            path: File path to load from
            format: File format
        """
        data = self.persistence_manager.load(path, format)
        
        # Clear current state
        self.clear()
        
        # Reconstruct graph
        self.graph["nodes"] = data["nodes"]
        self.graph["metadata"] = data.get("metadata", self.graph["metadata"])
        
        # Rebuild edges
        for edge in data["edges"].values():
            self._add_edge_internal(edge.src, edge.dst, edge.rel, edge.attrs)
        
        # Rebuild indexes
        self.index_manager.node_indexes = data.get("indexes", {})
    
    # ==================== UTILITIES ====================
    
    def stats(self) -> Stats:
        """
        Graph statistics.
        
        Returns:
            Dictionary of graph statistics
        """
        stats = {
            "nodes": len(self.graph["nodes"]),
            "edges": len(self._edges),
            "subgraphs": len(self._subgraph_views),
            "indexes": len(self.index_manager.node_indexes),
            "components": len(self.traversal_ops.connected_components()),
            "cache_size": getattr(self.find_nodes, 'cache_info', lambda: None)().currsize if self._cache_enabled else 0
        }
        
        # Add metrics
        stats.update(self._metrics)
        
        # Add index stats
        index_stats = self.index_manager.get_index_statistics()
        if "global" in index_stats:
            stats["index_hits"] = index_stats["global"]["index_hits"]
            stats["index_misses"] = index_stats["global"]["index_misses"]
        
        return stats
    
    def clear(self) -> None:
        """
        Clear all data.
        """
        with self._lock:
            self.graph = {
                "nodes": {},
                "metadata": {
                    "name": self.name,
                    "created_at": time.time(),
                    "version": self.config.get("engine.version", "2.0.0")
                }
            }
            self._edges.clear()
            self._out_edges.clear()
            self._in_edges.clear()
            self._rel_index.clear()
            self.index_manager.node_indexes.clear()
            self._subgraph_views.clear()
            self.clear_cache()
            
            # Reset metrics
            self._metrics = {key: 0 for key in self._metrics}
    
    def memory_usage_estimate(self) -> Dict[str, int]:
        """
        Estimate memory usage in bytes.
        
        Returns:
            Dictionary of memory usage by component
        """
        import sys
        
        return {
            "nodes_bytes": sum(sys.getsizeof(str(k)) + sys.getsizeof(v) 
                             for k, v in self.graph["nodes"].items()),
            "edges_bytes": sum(sys.getsizeof(e) for e in self._edges.values()),
            "indexes_bytes": sum(sys.getsizeof(idx) for idx in self.index_manager.node_indexes.values()),
            "adjacency_bytes": sys.getsizeof(self._out_edges) + sys.getsizeof(self._in_edges),
            "total_bytes": 0  # Would sum all above
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return f"FastGraph(name='{self.name}', nodes={len(self.graph['nodes'])}, edges={len(self._edges)})"
    
    def __str__(self) -> str:
        """String representation."""
        return f"FastGraph '{self.name}' with {len(self.graph['nodes'])} nodes and {len(self._edges)} edges"
    
    def __len__(self) -> int:
        """Return number of nodes."""
        return len(self.graph["nodes"])
    
    def __contains__(self, node_id: NodeId) -> bool:
        """Check if node exists using 'in' operator."""
        return node_id in self.graph["nodes"]
    
    def __iter__(self) -> Iterator[NodeId]:
        """Iterate over node IDs."""
        return iter(self.graph["nodes"].keys())
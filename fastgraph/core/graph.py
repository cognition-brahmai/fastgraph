"""
Main FastGraph class implementation

This module contains the core FastGraph class that integrates all
components into a high-performance in-memory graph database.
"""

from __future__ import annotations
import time
import threading
import logging
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
from ..utils.path_resolver import PathResolver
from ..utils.resource_manager import ResourceManager


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
        Initialize FastGraph instance with enhanced features.
        
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
            
            # Enhanced features
            graph = FastGraph(name="my_graph", enhanced_api=True)
        """
        # Load configuration
        self.config = self._load_config(config, kwargs)
        
        # Initialize core attributes
        self.name = name or self.config.get("engine.name", "fastgraph")
        
        # Enhanced features flag
        self._enhanced_enabled = self.config.get("enhanced_api.enabled", False)
        
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
        
        # Thread safety - must be initialized before managers that use it
        self._lock = threading.RLock()
        
        # Component managers
        self.index_manager = IndexManager(
            auto_index=self.config.get("indexing.auto_index", True)
        )
        self.traversal_ops = TraversalOperations(self)
        self.persistence_manager = PersistenceManager(self._lock, self.config)
        
        # Enhanced components
        if self._enhanced_enabled:
            self._path_resolver = PathResolver(self.config)
            self._resource_manager = ResourceManager(self.config)
            # Register this graph with resource manager
            self._graph_id = self._resource_manager.register_graph(self, self.name)
        else:
            self._path_resolver = None
            self._resource_manager = None
            self._graph_id = None
        
        # Subgraph views (no data duplication)
        self._subgraph_views: Dict[str, SubgraphView] = {}
        
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
                # Handle boolean overrides specially
                if key == "enhanced_api" and isinstance(value, bool):
                    # Convert to dict format for internal consistency
                    cfg_manager.set("enhanced_api.enabled", value)
                else:
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
    
    def save(self, path: Optional[Union[str, Path]] = None, format: Optional[str] = None, **kwargs) -> Union[Path, None]:
        """
        Save graph with enhanced features and smart defaults.
        
        Args:
            path: File path to save to (auto-resolved if None and enhanced API enabled)
            format: File format ("msgpack", "pickle", "json") - auto-detected if None
            **kwargs: Additional save options
            
        Returns:
            Path where graph was saved (if enhanced API enabled)
            
        Example:
            # Basic usage
            graph.save("my_graph.msgpack")
            
            # Enhanced - auto-resolve path and format
            graph.save()  # Saves to default location with default format
            
            # With path hint
            graph.save("data/my_graph")  # Auto-resolves format and path
        """
        # Prepare data
        data = {
            "nodes": self.graph["nodes"],
            "_edges": self._edges,
            "metadata": self.graph["metadata"],
            "node_indexes": self.index_manager.node_indexes
        }
        
        # Enhanced save with auto-resolution
        if self._enhanced_enabled and self._path_resolver:
            if path is None:
                # Use auto-resolution
                saved_path = self.persistence_manager.save_auto(
                    data, None, self.name, format, **kwargs
                )
                return saved_path
            else:
                # Path provided - try enhanced resolution
                try:
                    resolved_path = self._path_resolver.resolve_path(path, self.name, format)
                    if not format:
                        format = self._path_resolver.detect_format(resolved_path) or "msgpack"
                    
                    self.persistence_manager.save(data, resolved_path, format, **kwargs)
                    return resolved_path
                except Exception:
                    # Fallback to basic save
                    if not format:
                        format = self.config.get("storage.default_format", "msgpack")
                    self.persistence_manager.save(data, path, format, **kwargs)
                    return Path(path)
        else:
            # Basic save
            if not format:
                format = self.config.get("storage.default_format", "msgpack")
            if path is None:
                raise PersistenceError("Path required when enhanced API is disabled",
                                    operation="save")
            self.persistence_manager.save(data, path, format, **kwargs)
            return None
    
    def load(self, path: Optional[Union[str, Path]] = None, format: Optional[str] = None, **kwargs) -> Union[Path, None]:
        """
        Load graph with automatic format detection and path resolution.
        
        Args:
            path: File path to load from (auto-resolved if None and enhanced API enabled)
            format: File format (auto-detected if None)
            **kwargs: Additional load options
            
        Returns:
            Path where graph was loaded from (if enhanced API enabled)
            
        Example:
            # Basic usage
            graph.load("my_graph.msgpack")
            
            # Enhanced - auto-discover and load
            graph.load()  # Auto-discovers graph file
            
            # Load by name
            graph.load(graph_name="my_graph")  # Searches for graph file
        """
        # Enhanced load with auto-resolution
        if self._enhanced_enabled and self._path_resolver:
            try:
                if path is None:
                    # Auto-discover graph file
                    graph_data, loaded_path = self.persistence_manager.load_auto(
                        None, self.name, format, **kwargs
                    )
                else:
                    # Path provided - try enhanced resolution
                    if isinstance(path, str) and not Path(path).exists():
                        # Might be a graph name
                        graph_data, loaded_path = self.persistence_manager.load_auto(
                            path, None, format, **kwargs
                        )
                    else:
                        # Direct path
                        if not format:
                            format = self._path_resolver.detect_format(path) or "msgpack"
                        graph_data = self.persistence_manager.load(path, format, **kwargs)
                        loaded_path = Path(path)
                
                # Load the data into current graph
                self._load_data_into_graph(graph_data)
                
                # Update resource manager
                if self._resource_manager and self._graph_id:
                    self._resource_manager.update_access_time(self._graph_id)
                
                return loaded_path
                
            except Exception as e:
                # Fallback to basic load
                if path and format:
                    try:
                        graph_data = self.persistence_manager.load(path, format, **kwargs)
                        self._load_data_into_graph(graph_data)
                        return Path(path)
                    except Exception:
                        raise PersistenceError(f"Failed to load graph: {e}", operation="load")
                else:
                    raise PersistenceError(f"Failed to load graph: {e}", operation="load")
        else:
            # Basic load
            if path is None:
                raise PersistenceError("Path required when enhanced API is disabled",
                                    operation="load")
            if not format:
                format = self.config.get("storage.default_format", "msgpack")
            graph_data = self.persistence_manager.load(path, format, **kwargs)
            self._load_data_into_graph(graph_data)
            return Path(path)
    
    def _load_data_into_graph(self, data: Dict[str, Any]) -> None:
        """Helper method to load data into current graph instance."""
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
    
    def exists(self, path_hint: Optional[Union[str, Path]] = None) -> bool:
        """
        Check if a graph file exists.
        
        Args:
            path_hint: Optional path hint or graph name to check
            
        Returns:
            True if graph file exists, False otherwise
            
        Example:
            if graph.exists():
                print("Graph file exists")
                
            if graph.exists("my_graph"):
                print("Graph 'my_graph' exists")
        """
        if not self._enhanced_enabled or not self._path_resolver:
            # Basic check
            if path_hint:
                return Path(path_hint).exists()
            return False
        
        # Enhanced existence check
        if path_hint:
            if isinstance(path_hint, str) and not Path(path_hint).exists():
                # Try to find by name
                found_path = self._path_resolver.find_graph_file(path_hint)
                return found_path is not None and found_path.exists()
            else:
                return Path(path_hint).exists()
        else:
            # Check default location for this graph
            default_path = self._path_resolver.get_default_path(self.name)
            return default_path.exists()
    
    def translate(self, source_path: Union[str, Path], target_path: Union[str, Path],
                  source_format: Optional[str] = None, target_format: str = "msgpack",
                  **kwargs) -> Path:
        """
        Convert graph file from one format to another.
        
        Args:
            source_path: Source file path
            target_path: Target file path
            source_format: Source format (auto-detected if None)
            target_format: Target format
            **kwargs: Additional options
            
        Returns:
            Path to the converted file
            
        Example:
            # Convert JSON to msgpack
            graph.translate("data.json", "data.msgpack", "json", "msgpack")
            
            # Auto-detect source and convert to msgpack
            graph.translate("data.json", "data.msgpack", target_format="msgpack")
        """
        if not self._enhanced_enabled or not self._path_resolver:
            raise PersistenceError("Format translation requires enhanced API to be enabled",
                                operation="translate")
        
        source_path = Path(source_path)
        target_path = Path(target_path)
        
        # Detect source format if not specified
        if not source_format:
            source_format = self._path_resolver.detect_format(source_path)
            if not source_format:
                raise PersistenceError(f"Cannot detect source format for {source_path}",
                                    operation="translate")
        
        # Load source data
        source_data = self.persistence_manager.load(source_path, source_format, **kwargs)
        
        # Save in target format
        self.persistence_manager.save(source_data, target_path, target_format, **kwargs)
        
        return target_path
    
    def get_translation(self, source_path: Union[str, Path], target_format: str,
                       output_dir: Optional[Union[str, Path]] = None) -> Path:
        """
        Extract graph data from a file and convert it to a different format.
        
        Args:
            source_path: Source file path
            target_format: Target format for extraction
            output_dir: Optional output directory (auto-resolved if None)
            
        Returns:
            Path to the extracted file
            
        Example:
            # Extract data from JSON to msgpack
            extracted_path = graph.get_translation("data.json", "msgpack")
        """
        if not self._enhanced_enabled or not self._path_resolver:
            raise PersistenceError("Format extraction requires enhanced API to be enabled",
                                operation="get_translation")
        
        source_path = Path(source_path)
        
        # Determine output path
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            target_path = output_dir / f"{source_path.stem}.{target_format}"
        else:
            target_path = source_path.parent / f"{source_path.stem}.{target_format}"
        
        # Perform translation
        return self.translate(source_path, target_path, None, target_format)
    
    # ==================== FACTORY METHODS ====================
    
    @classmethod
    def from_file(cls, path: Union[str, Path], format: Optional[str] = None,
                  config: Optional[Union[str, Path, Dict, ConfigManager]] = None,
                  **kwargs) -> 'FastGraph':
        """
        Create FastGraph instance from existing file.
        
        Args:
            path: Path to graph file
            format: File format (auto-detected if None)
            config: Optional configuration
            **kwargs: Additional parameters
            
        Returns:
            FastGraph instance loaded with data from file
            
        Example:
            graph = FastGraph.from_file("my_graph.msgpack")
            graph = FastGraph.from_file("data.json", config={"enhanced_api": {"enabled": True}})
        """
        # Create instance
        instance = cls(config=config, **kwargs)
        
        # Load data
        instance.load(path, format)
        
        return instance
    
    @classmethod
    def load_graph(cls, path_hint: Optional[Union[str, Path]] = None,
                   graph_name: Optional[str] = None,
                   config: Optional[Union[str, Path, Dict, ConfigManager]] = None,
                   **kwargs) -> 'FastGraph':
        """
        Factory method to load existing graph with enhanced discovery.
        
        Args:
            path_hint: Optional path hint for graph file
            graph_name: Name of graph to search for
            config: Optional configuration
            **kwargs: Additional parameters
            
        Returns:
            FastGraph instance loaded with data
            
        Example:
            # Load from specific file
            graph = FastGraph.load_graph("my_graph.msgpack")
            
            # Auto-discover by name
            graph = FastGraph.load_graph(graph_name="my_graph")
            
            # Auto-discover any graph
            graph = FastGraph.load_graph()
        """
        # Create instance with enhanced features enabled
        if config is None:
            config = {"enhanced_api": {"enabled": True}}
        elif isinstance(config, dict):
            config = {"enhanced_api": {"enabled": True}, **config}
        
        instance = cls(config=config, **kwargs)
        
        # Load data
        if path_hint or graph_name:
            # Call instance load method directly
            instance.load(path_hint, **kwargs)
        else:
            # Try to auto-discover
            if instance._enhanced_enabled and instance._path_resolver:
                # Try to find any graph file in default locations
                if instance.name:
                    instance.load(graph_name=instance.name, **kwargs)
                else:
                    raise PersistenceError("Cannot auto-discover graph without name or path",
                                        operation="load")
            else:
                raise PersistenceError("Path or graph name required when enhanced API is disabled",
                                    operation="load")
        
        return instance
    
    @classmethod
    def with_config(cls, config: Union[str, Path, Dict, ConfigManager],
                   name: Optional[str] = None, **kwargs) -> 'FastGraph':
        """
        Create FastGraph instance with specific configuration.
        
        Args:
            config: Configuration source
            name: Optional graph name
            **kwargs: Additional configuration overrides
            
        Returns:
            FastGraph instance with specified configuration
            
        Example:
            config = {"enhanced_api": {"enabled": True}, "memory": {"query_cache_size": 256}}
            graph = FastGraph.with_config(config, name="my_graph")
        """
        return cls(name=name, config=config, **kwargs)
    
    # ==================== CONTEXT MANAGER ====================
    
    def __enter__(self):
        """
        Context manager entry.
        
        Returns:
            Self for context usage
            
        Example:
            with FastGraph(name="temp_graph") as graph:
                graph.add_node("A", name="Alice")
                graph.add_node("B", name="Bob")
                graph.add_edge("A", "B", "knows")
                # Auto-save and cleanup on exit
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Update resource manager access time
        if self._resource_manager and self._graph_id:
            self._resource_manager.update_access_time(self._graph_id)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit with automatic cleanup.
        
        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Auto-save if enabled and no exception occurred
            if exc_type is None and self._enhanced_enabled:
                auto_save = self.config.get("persistence", {}).get("auto_save_on_exit", False)
                if auto_save:
                    try:
                        self.save()
                    except Exception as e:
                        logger.warning(f"Auto-save failed on context exit: {e}")
            
            # Cleanup resources
            if self._resource_manager and self._graph_id:
                self._resource_manager.unregister_graph(self._graph_id)
                
        except Exception as e:
            logger.error(f"Error during context manager cleanup: {e}")
        
        # Don't suppress exceptions
        return False
    
    def cleanup(self) -> None:
        """
        Explicit cleanup method for resource management.
        
        This method should be called when the graph instance is no longer needed
        to ensure proper resource cleanup, especially when not using context manager.
        
        Example:
            graph = FastGraph()
            # ... use graph ...
            graph.cleanup()  # Explicit cleanup
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Save if auto-save is enabled
            if self._enhanced_enabled:
                auto_save = self.config.get("persistence", {}).get("auto_save_on_cleanup", False)
                if auto_save:
                    try:
                        self.save()
                    except Exception as e:
                        logger.warning(f"Auto-save failed during cleanup: {e}")
            
            # Unregister from resource manager
            if self._resource_manager and self._graph_id:
                self._resource_manager.unregister_graph(self._graph_id)
                self._graph_id = None
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def backup(self, backup_dir: Optional[Path] = None) -> List[Path]:
        """
        Create backup(s) of the current graph.
        
        Args:
            backup_dir: Optional backup directory override
            
        Returns:
            List of paths to created backup files
            
        Example:
            backup_paths = graph.backup()
            print(f"Created backups: {backup_paths}")
        """
        if not self._enhanced_enabled:
            raise PersistenceError("Backup requires enhanced API to be enabled",
                                operation="backup")
        
        # Prepare data
        data = {
            "nodes": self.graph["nodes"],
            "_edges": self._edges,
            "metadata": self.graph["metadata"],
            "node_indexes": self.index_manager.node_indexes
        }
        
        return self.persistence_manager.backup(data, self.name, backup_dir)
    
    def restore_from_backup(self, backup_dir: Optional[Path] = None,
                           format: Optional[str] = None) -> Path:
        """
        Restore graph from the most recent backup.
        
        Args:
            backup_dir: Optional backup directory override
            format: Optional format preference
            
        Returns:
            Path to the backup file that was restored
            
        Example:
            backup_path = graph.restore_from_backup()
            print(f"Restored from: {backup_path}")
        """
        if not self._enhanced_enabled:
            raise PersistenceError("Restore requires enhanced API to be enabled",
                                operation="restore")
        
        # Restore data
        graph_data, backup_path = self.persistence_manager.restore_from_backup(
            self.name, backup_dir, format
        )
        
        # Load into current graph
        self._load_data_into_graph(graph_data)
        
        return backup_path
    
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
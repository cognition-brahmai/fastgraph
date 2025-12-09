"""
Indexing functionality for FastGraph

This module contains the IndexManager class which handles node and edge indexing
for fast queries and lookups.
"""

from typing import Any, Dict, Set, List, Optional, Callable
from collections import defaultdict

from ..types import NodeId, NodeAttrs, IndexValue, IndexMap, NodeFilter
from ..exceptions import IndexingError, ValidationError


class IndexManager:
    """
    Manages node and edge indexes for fast query performance.
    
    Provides automatic index creation, maintenance, and query optimization
    based on node attributes and edge properties.
    """
    
    def __init__(self, auto_index: bool = True):
        """
        Initialize index manager.
        
        Args:
            auto_index: Whether to automatically create indexes for common attributes
        """
        self.auto_index = auto_index
        self.node_indexes: Dict[str, IndexMap] = {}
        self.edge_indexes: Dict[str, Dict[IndexValue, Set[str]]] = {}
        self.index_stats: Dict[str, Dict[str, int]] = {}
        
        # Track which attributes are indexed
        self.indexed_attributes: Set[str] = set()
        
        # Performance metrics
        self.index_hits = 0
        self.index_misses = 0
    
    def create_node_index(self, attr_name: str, nodes: Dict[NodeId, NodeAttrs] = None) -> None:
        """
        Create or rebuild an index on a node attribute.
        
        Args:
            attr_name: Name of the attribute to index
            nodes: Optional dictionary of nodes to index (if None, uses empty dict)
            
        Raises:
            IndexingError: If index creation fails
            ValidationError: If attribute name is invalid
        """
        if not attr_name or not isinstance(attr_name, str):
            raise ValidationError("Attribute name must be a non-empty string", 
                                field="attr_name", value=attr_name)
        
        try:
            # Create new index
            index: IndexMap = defaultdict(set)
            nodes = nodes or {}
            
            # Build index from existing nodes
            for node_id, attrs in nodes.items():
                if attr_name in attrs:
                    value = attrs[attr_name]
                    index[value].add(node_id)
            
            # Store the index
            self.node_indexes[attr_name] = dict(index)  # Convert defaultdict to dict
            self.indexed_attributes.add(attr_name)
            
            # Record index statistics
            self.index_stats[attr_name] = {
                "total_values": len(index),
                "total_entries": sum(len(node_set) for node_set in index.values()),
                "unique_values": len(index.keys()),
                "created_at": 0  # Would use time.time() in real implementation
            }
            
        except Exception as e:
            raise IndexingError(f"Failed to create index on attribute '{attr_name}': {e}",
                              index_name=attr_name, operation="create_index")
    
    def drop_node_index(self, attr_name: str) -> None:
        """
        Drop a node index.
        
        Args:
            attr_name: Name of the attribute index to drop
            
        Raises:
            IndexNotFoundError: If index doesn't exist
        """
        if attr_name not in self.node_indexes:
            raise IndexingError(f"No index found on attribute '{attr_name}'",
                              index_name=attr_name, operation="drop_index")
        
        del self.node_indexes[attr_name]
        self.indexed_attributes.discard(attr_name)
        if attr_name in self.index_stats:
            del self.index_stats[attr_name]
    
    def has_index(self, attr_name: str) -> bool:
        """
        Check if an index exists for the given attribute.
        
        Args:
            attr_name: Attribute name to check
            
        Returns:
            True if index exists, False otherwise
        """
        return attr_name in self.node_indexes
    
    def update_node_index(self, node_id: NodeId, old_attrs: NodeAttrs, new_attrs: NodeAttrs) -> None:
        """
        Update indexes when a node is modified.
        
        Args:
            node_id: ID of the modified node
            old_attrs: Previous node attributes
            new_attrs: New node attributes
        """
        # Update each index
        for attr_name in self.indexed_attributes:
            # Remove old value if it existed
            if attr_name in old_attrs:
                old_value = old_attrs[attr_name]
                self._remove_from_index(attr_name, old_value, node_id)
            
            # Add new value if it exists
            if attr_name in new_attrs:
                new_value = new_attrs[attr_name]
                self._add_to_index(attr_name, new_value, node_id)
    
    def remove_from_indexes(self, node_id: NodeId, attrs: NodeAttrs) -> None:
        """
        Remove a node from all indexes.
        
        Args:
            node_id: ID of the node to remove
            attrs: Attributes of the node being removed
        """
        for attr_name, value in attrs.items():
            if attr_name in self.indexed_attributes:
                self._remove_from_index(attr_name, value, node_id)
    
    def query_by_index(self, attr_name: str, value: IndexValue) -> Set[NodeId]:
        """
        Query nodes using an index.
        
        Args:
            attr_name: Indexed attribute name
            value: Value to look up
            
        Returns:
            Set of node IDs with the given attribute value
            
        Raises:
            IndexNotFoundError: If index doesn't exist
        """
        if attr_name not in self.node_indexes:
            raise IndexingError(f"No index found on attribute '{attr_name}'",
                              index_name=attr_name, operation="query")
        
        if attr_name in self.node_indexes and value in self.node_indexes[attr_name]:
            self.index_hits += 1
            return self.node_indexes[attr_name][value].copy()
        else:
            self.index_misses += 1
            return set()
    
    def query_by_index_range(self, attr_name: str, min_val: IndexValue, 
                           max_val: IndexValue) -> Set[NodeId]:
        """
        Query nodes using a range on an indexed attribute.
        
        Args:
            attr_name: Indexed attribute name (must be comparable)
            min_val: Minimum value (inclusive)
            max_val: Maximum value (inclusive)
            
        Returns:
            Set of node IDs with values in the range
            
        Raises:
            IndexNotFoundError: If index doesn't exist
            ValidationError: If values are not comparable
        """
        if attr_name not in self.node_indexes:
            raise IndexingError(f"No index found on attribute '{attr_name}'",
                              index_name=attr_name, operation="query_range")
        
        try:
            result = set()
            for index_value, node_set in self.node_indexes[attr_name].items():
                if min_val <= index_value <= max_val:
                    result.update(node_set)
            
            if result:
                self.index_hits += 1
            else:
                self.index_misses += 1
            
            return result
            
        except TypeError as e:
            raise ValidationError(f"Values are not comparable for range query: {e}",
                               field=attr_name, value=(min_val, max_val))
    
    def suggest_indexes(self, nodes: Dict[NodeId, NodeAttrs], 
                       query_patterns: List[Dict[str, Any]] = None) -> List[str]:
        """
        Suggest attributes that would benefit from indexing.
        
        Args:
            nodes: Dictionary of nodes to analyze
            query_patterns: Optional list of common query patterns
            
        Returns:
            List of attribute names recommended for indexing
        """
        if not nodes:
            return []
        
        # Analyze attribute frequency and selectivity
        attr_stats = defaultdict(lambda: {"count": 0, "unique": 0, "values": set()})
        
        for attrs in nodes.values():
            for attr_name, value in attrs.items():
                attr_stats[attr_name]["count"] += 1
                attr_stats[attr_name]["values"].add(value)
        
        # Calculate metrics
        suggestions = []
        total_nodes = len(nodes)
        
        for attr_name, stats in attr_stats.items():
            unique_count = len(stats["values"])
            frequency = stats["count"] / total_nodes
            selectivity = unique_count / total_nodes if total_nodes > 0 else 0
            
            # Suggest if:
            # 1. High selectivity (many unique values)
            # 2. High frequency (present in many nodes)
            # 3. Not already indexed
            if (selectivity > 0.1 and frequency > 0.1 and 
                attr_name not in self.indexed_attributes):
                suggestions.append(attr_name)
        
        # Sort by selectivity (most selective first)
        suggestions.sort(key=lambda x: len(attr_stats[x]["values"]) / total_nodes, 
                       reverse=True)
        
        return suggestions
    
    def get_index_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all indexes.
        
        Returns:
            Dictionary of index statistics
        """
        stats = {}
        
        for attr_name, index in self.node_indexes.items():
            total_entries = sum(len(node_set) for node_set in index.values())
            avg_entries_per_value = total_entries / len(index) if index else 0
            
            stats[attr_name] = {
                "total_values": len(index),
                "total_entries": total_entries,
                "avg_entries_per_value": avg_entries_per_value,
                "unique_values": len(set().union(*index.values())) if index else 0,
                "memory_estimate": self._estimate_index_memory(index)
            }
        
        # Add global statistics
        stats["global"] = {
            "total_indexes": len(self.node_indexes),
            "total_indexed_attributes": len(self.indexed_attributes),
            "index_hits": self.index_hits,
            "index_misses": self.index_misses,
            "hit_rate": self.index_hits / (self.index_hits + self.index_misses) if (self.index_hits + self.index_misses) > 0 else 0
        }
        
        return stats
    
    def optimize_indexes(self, nodes: Dict[NodeId, NodeAttrs]) -> None:
        """
        Optimize indexes based on current data and query patterns.
        
        Args:
            nodes: Current node data
        """
        # Get suggestions for new indexes
        suggestions = self.suggest_indexes(nodes)
        
        # Auto-create suggested indexes if auto_index is enabled
        if self.auto_index:
            for attr_name in suggestions[:5]:  # Limit to top 5 suggestions
                if attr_name not in self.node_indexes:
                    self.create_node_index(attr_name, nodes)
    
    def rebuild_all_indexes(self, nodes: Dict[NodeId, NodeAttrs]) -> None:
        """
        Rebuild all indexes from scratch.
        
        Args:
            nodes: Current node data
        """
        indexed_attrs = list(self.indexed_attributes.copy())
        
        # Clear all indexes
        self.node_indexes.clear()
        self.indexed_attributes.clear()
        
        # Rebuild indexes
        for attr_name in indexed_attrs:
            self.create_node_index(attr_name, nodes)
    
    def _add_to_index(self, attr_name: str, value: IndexValue, node_id: NodeId) -> None:
        """
        Add a node to an index.
        
        Args:
            attr_name: Attribute name
            value: Attribute value
            node_id: Node ID to add
        """
        if attr_name not in self.node_indexes:
            return
        
        if value not in self.node_indexes[attr_name]:
            self.node_indexes[attr_name][value] = set()
        
        self.node_indexes[attr_name][value].add(node_id)
    
    def _remove_from_index(self, attr_name: str, value: IndexValue, node_id: NodeId) -> None:
        """
        Remove a node from an index.
        
        Args:
            attr_name: Attribute name
            value: Attribute value
            node_id: Node ID to remove
        """
        if (attr_name in self.node_indexes and 
            value in self.node_indexes[attr_name]):
            self.node_indexes[attr_name][value].discard(node_id)
            
            # Clean up empty value entries
            if not self.node_indexes[attr_name][value]:
                del self.node_indexes[attr_name][value]
    
    def _estimate_index_memory(self, index: IndexMap) -> int:
        """
        Estimate memory usage of an index in bytes.
        
        Args:
            index: Index to estimate
            
        Returns:
            Estimated memory usage in bytes
        """
        import sys
        
        # Rough estimate: overhead per key + per value + per node in sets
        size = sys.getsizeof(index)
        for value, node_set in index.items():
            size += sys.getsizeof(value)
            size += sys.getsizeof(node_set)
            size += sum(sys.getsizeof(node_id) for node_id in node_set)
        
        return size
    
    def __repr__(self) -> str:
        """String representation."""
        return f"IndexManager(indexes={len(self.node_indexes)}, auto_index={self.auto_index})"
    
    def __str__(self) -> str:
        """String representation."""
        return f"IndexManager with {len(self.node_indexes)} indexes on attributes: {list(self.indexed_attributes)}"
"""
Subgraph view implementation for FastGraph

This module contains the SubgraphView class which provides memory-efficient
views into parent graphs without data duplication.
"""

import weakref
from typing import Any, Dict, List, Set

from ..types import NodeId, NodeAttrs
from ..exceptions import TraversalError
from .edge import Edge


class SubgraphView:
    """
    Memory-efficient view into a parent graph (no data duplication).
    
    A subgraph view provides a filtered view of a parent graph, containing
    only a subset of nodes and their connected edges. This is implemented
    using weak references to avoid data duplication and memory overhead.
    """
    
    def __init__(self, parent: 'FastGraph', node_ids: Set[NodeId]):
        """
        Initialize subgraph view.
        
        Args:
            parent: Parent FastGraph instance
            node_ids: Set of node IDs to include in this view
            
        Raises:
            TraversalError: If parent graph is invalid
        """
        # Store weak reference to parent to avoid circular references
        self._parent_ref = weakref.ref(parent)
        self._node_ids = set(node_ids)  # Make a copy
        
        # Validate that parent has reference to this view for cleanup
        if not hasattr(parent, '_subgraph_views'):
            raise TraversalError("Parent graph must support subgraph views")
    
    @property
    def parent(self) -> 'FastGraph':
        """
        Get the parent graph instance.
        
        Returns:
            Parent FastGraph instance
            
        Raises:
            TraversalError: If parent graph has been garbage collected
        """
        parent = self._parent_ref()
        if parent is None:
            raise TraversalError("Parent graph was garbage collected")
        return parent
    
    @property
    def nodes(self) -> Dict[NodeId, NodeAttrs]:
        """
        Get nodes in this subgraph view.
        
        Returns:
            Dictionary of node_id -> attributes for nodes in this view
            (returns a view, not a copy)
        """
        parent = self.parent
        return {
            nid: parent.graph["nodes"][nid] 
            for nid in self._node_ids 
            if nid in parent.graph["nodes"]
        }
    
    @property
    def edges(self) -> List[Edge]:
        """
        Get edges in this subgraph view.
        
        Returns:
            List of edges where both endpoints are in this subgraph
        """
        parent = self.parent
        return [
            edge for edge in parent._edges.values() 
            if edge.src in self._node_ids and edge.dst in self._node_ids
        ]
    
    @property
    def node_count(self) -> int:
        """
        Get the number of nodes in this subgraph.
        
        Returns:
            Number of nodes
        """
        return len(self._node_ids)
    
    @property
    def edge_count(self) -> int:
        """
        Get the number of edges in this subgraph.
        
        Returns:
            Number of edges
        """
        return len(self.edges)
    
    def contains_node(self, node_id: NodeId) -> bool:
        """
        Check if a node is in this subgraph view.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            True if node is in view, False otherwise
        """
        return node_id in self._node_ids
    
    def get_node(self, node_id: NodeId) -> NodeAttrs:
        """
        Get a node from this subgraph view.
        
        Args:
            node_id: Node ID to retrieve
            
        Returns:
            Node attributes
            
        Raises:
            TraversalError: If node is not in this view
        """
        if node_id not in self._node_ids:
            raise TraversalError(f"Node '{node_id}' not in subgraph view", 
                              node_id=node_id, operation="get_node")
        
        parent = self.parent
        if node_id not in parent.graph["nodes"]:
            raise TraversalError(f"Node '{node_id}' not found in parent graph", 
                              node_id=node_id, operation="get_node")
        
        return parent.graph["nodes"][node_id]
    
    def get_edges_between(self, src: NodeId, dst: NodeId, rel: str = None) -> List[Edge]:
        """
        Get edges between two nodes in this subgraph.
        
        Args:
            src: Source node ID
            dst: Destination node ID
            rel: Optional relation filter
            
        Returns:
            List of edges between the nodes
        """
        parent = self.parent
        edges = []
        
        for (edge_src, edge_dst, edge_rel), edge in parent._edges.items():
            if (edge_src == src and edge_dst == dst and 
                edge_src in self._node_ids and edge_dst in self._node_ids):
                if rel is None or edge_rel == rel:
                    edges.append(edge)
        
        return edges
    
    def get_node_edges(self, node_id: NodeId) -> List[Edge]:
        """
        Get all edges connected to a node in this subgraph.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of edges connected to the node
        """
        if node_id not in self._node_ids:
            return []
        
        parent = self.parent
        edges = []
        
        # Outgoing edges
        for edge in parent._out_edges.get(node_id, []):
            if edge.dst in self._node_ids:
                edges.append(edge)
        
        # Incoming edges
        for edge in parent._in_edges.get(node_id, []):
            if edge.src in self._node_ids:
                edges.append(edge)
        
        return edges
    
    def get_neighbors(self, node_id: NodeId) -> List[NodeId]:
        """
        Get neighbors of a node within this subgraph.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of neighbor node IDs
        """
        if node_id not in self._node_ids:
            return []
        
        parent = self.parent
        neighbors = set()
        
        # Outgoing neighbors
        for edge in parent._out_edges.get(node_id, []):
            if edge.dst in self._node_ids:
                neighbors.add(edge.dst)
        
        # Incoming neighbors
        for edge in parent._in_edges.get(node_id, []):
            if edge.src in self._node_ids:
                neighbors.add(edge.src)
        
        return list(neighbors)
    
    def stats(self) -> Dict[str, Any]:
        """
        Get statistics for this subgraph view.
        
        Returns:
            Dictionary containing subgraph statistics
        """
        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "avg_degree": (2 * self.edge_count / self.node_count) if self.node_count > 0 else 0,
            "density": self._calculate_density(),
        }
    
    def _calculate_density(self) -> float:
        """
        Calculate graph density.
        
        Returns:
            Graph density (0.0 to 1.0)
        """
        if self.node_count <= 1:
            return 0.0
        
        # For directed graph: edges / (n * (n-1))
        max_possible_edges = self.node_count * (self.node_count - 1)
        return self.edge_count / max_possible_edges
    
    def is_connected(self) -> bool:
        """
        Check if this subgraph is connected.
        
        Returns:
            True if subgraph is connected, False otherwise
        """
        if self.node_count == 0:
            return True
        
        if self.node_count == 1:
            return True
        
        # Use BFS to check connectivity
        visited = set()
        to_visit = [next(iter(self._node_ids))]  # Start with any node
        
        while to_visit:
            current = to_visit.pop(0)
            if current in visited:
                continue
            
            visited.add(current)
            
            # Add unvisited neighbors
            neighbors = self.get_neighbors(current)
            for neighbor in neighbors:
                if neighbor not in visited and neighbor not in to_visit:
                    to_visit.append(neighbor)
        
        return len(visited) == self.node_count
    
    def find_components(self) -> List[Set[NodeId]]:
        """
        Find connected components in this subgraph.
        
        Returns:
            List of sets, each containing node IDs for a component
        """
        if self.node_count == 0:
            return []
        
        unvisited = set(self._node_ids)
        components = []
        
        while unvisited:
            # Start BFS from an unvisited node
            start = next(iter(unvisited))
            component = set()
            to_visit = [start]
            
            while to_visit:
                current = to_visit.pop(0)
                if current in component:
                    continue
                
                component.add(current)
                
                # Add unvisited neighbors within this subgraph
                neighbors = self.get_neighbors(current)
                for neighbor in neighbors:
                    if neighbor not in component and neighbor in unvisited:
                        to_visit.append(neighbor)
            
            components.append(component)
            unvisited -= component
        
        return components
    
    def __contains__(self, node_id: NodeId) -> bool:
        """Check if node is in subgraph using 'in' operator."""
        return self.contains_node(node_id)
    
    def __len__(self) -> int:
        """Get number of nodes in subgraph."""
        return self.node_count
    
    def __iter__(self):
        """Iterate over node IDs in subgraph."""
        return iter(self._node_ids)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"SubgraphView(nodes={self.node_count}, edges={self.edge_count})"
    
    def __str__(self) -> str:
        """String representation."""
        return f"Subgraph with {self.node_count} nodes and {self.edge_count} edges"
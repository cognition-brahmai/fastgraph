"""
Graph traversal operations for FastGraph

This module contains traversal algorithms and neighbor operations for
navigating and analyzing graph structures.
"""

from typing import Any, Dict, List, Set, Optional, Iterator, Callable, Generator, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass

from ..types import NodeId, NodeAttrs, EdgeFilter, NodeFilter, EdgeKey, EdgeAttrs
from ..exceptions import TraversalError, NodeNotFoundError
from .edge import Edge


@dataclass
class TraversalResult:
    """
    Result of a graph traversal operation.
    """
    nodes: Set[NodeId]
    edges: List[Edge]
    depth: int
    paths: List[List[NodeId]]
    
    @property
    def node_count(self) -> int:
        """Get number of nodes in result."""
        return len(self.nodes)
    
    @property
    def edge_count(self) -> int:
        """Get number of edges in result."""
        return len(self.edges)
    
    @property
    def path_count(self) -> int:
        """Get number of paths found."""
        return len(self.paths)


class TraversalOperations:
    """
    Provides graph traversal algorithms and neighbor operations.
    
    Includes BFS, DFS, shortest path, connected components, and various
    graph exploration algorithms optimized for the FastGraph data structure.
    """
    
    def __init__(self, graph):
        """
        Initialize traversal operations.
        
        Args:
            graph: FastGraph instance to operate on
        """
        self.graph = graph
    
    def neighbors_out(self, node_id: NodeId, rel: Optional[str] = None, 
                     edge_filter: Optional[EdgeFilter] = None) -> List[Tuple[NodeId, Edge]]:
        """
        Get outgoing neighbors of a node.
        
        Args:
            node_id: Starting node ID
            rel: Optional relation filter
            edge_filter: Optional edge filter function
            
        Returns:
            List of (neighbor_id, edge) tuples
            
        Raises:
            NodeNotFoundError: If node doesn't exist
            TraversalError: If traversal fails
        """
        if node_id not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(node_id)
        
        try:
            edges = self.graph._out_edges.get(node_id, [])
            
            # Apply relation filter
            if rel:
                edges = [e for e in edges if e.rel == rel]
            
            # Apply edge filter
            if edge_filter:
                edges = [e for e in edges if edge_filter(e)]
            
            return [(e.dst, e) for e in edges]
            
        except Exception as e:
            raise TraversalError(f"Failed to get outgoing neighbors for node '{node_id}': {e}",
                              node_id=node_id, operation="neighbors_out")
    
    def neighbors_in(self, node_id: NodeId, rel: Optional[str] = None,
                    edge_filter: Optional[EdgeFilter] = None) -> List[Tuple[NodeId, Edge]]:
        """
        Get incoming neighbors of a node.
        
        Args:
            node_id: Target node ID
            rel: Optional relation filter
            edge_filter: Optional edge filter function
            
        Returns:
            List of (neighbor_id, edge) tuples
            
        Raises:
            NodeNotFoundError: If node doesn't exist
            TraversalError: If traversal fails
        """
        if node_id not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(node_id)
        
        try:
            edges = self.graph._in_edges.get(node_id, [])
            
            # Apply relation filter
            if rel:
                edges = [e for e in edges if e.rel == rel]
            
            # Apply edge filter
            if edge_filter:
                edges = [e for e in edges if edge_filter(e)]
            
            return [(e.src, e) for e in edges]
            
        except Exception as e:
            raise TraversalError(f"Failed to get incoming neighbors for node '{node_id}': {e}",
                              node_id=node_id, operation="neighbors_in")
    
    def neighbors(self, node_id: NodeId, rel: Optional[str] = None,
                 edge_filter: Optional[EdgeFilter] = None) -> List[Tuple[NodeId, Edge]]:
        """
        Get all neighbors (both incoming and outgoing) of a node.
        
        Args:
            node_id: Node ID
            rel: Optional relation filter
            edge_filter: Optional edge filter function
            
        Returns:
            List of (neighbor_id, edge) tuples
        """
        outgoing = self.neighbors_out(node_id, rel, edge_filter)
        incoming = self.neighbors_in(node_id, rel, edge_filter)
        return outgoing + incoming
    
    def degree(self, node_id: NodeId, rel: Optional[str] = None) -> tuple[int, int, int]:
        """
        Calculate degree of a node.
        
        Args:
            node_id: Node ID
            rel: Optional relation filter
            
        Returns:
            Tuple of (out_degree, in_degree, total_degree)
        """
        out_degree = len(self.neighbors_out(node_id, rel))
        in_degree = len(self.neighbors_in(node_id, rel))
        total_degree = out_degree + in_degree
        return (out_degree, in_degree, total_degree)
    
    def bfs(self, start_node: NodeId, max_depth: Optional[int] = None,
           node_filter: Optional[NodeFilter] = None,
           edge_filter: Optional[EdgeFilter] = None) -> TraversalResult:
        """
        Breadth-First Search traversal.
        
        Args:
            start_node: Starting node ID
            max_depth: Maximum depth to traverse
            node_filter: Optional node filter function
            edge_filter: Optional edge filter function
            
        Returns:
            TraversalResult containing visited nodes, edges, depth, and paths
            
        Raises:
            NodeNotFoundError: If start node doesn't exist
        """
        if start_node not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(start_node)
        
        visited = set()
        queue = deque([(start_node, 0)])  # (node, depth)
        visited_nodes = set()
        visited_edges = []
        paths = {start_node: [start_node]}
        current_depth = 0
        
        while queue:
            node, depth = queue.popleft()
            
            if node in visited:
                continue
            
            visited.add(node)
            visited_nodes.add(node)
            current_depth = max(current_depth, depth)
            
            # Check max depth
            if max_depth is not None and depth >= max_depth:
                continue
            
            # Get neighbors
            for neighbor, edge in self.neighbors_out(node, edge_filter=edge_filter):
                if neighbor not in visited:
                    # Apply node filter
                    if node_filter:
                        neighbor_attrs = self.graph.graph["nodes"].get(neighbor, {})
                        if not node_filter(neighbor, neighbor_attrs):
                            continue
                    
                    queue.append((neighbor, depth + 1))
                    visited_edges.append(edge)
                    
                    # Track path
                    if neighbor not in paths:
                        paths[neighbor] = paths[node] + [neighbor]
        
        return TraversalResult(
            nodes=visited_nodes,
            edges=visited_edges,
            depth=current_depth,
            paths=list(paths.values())
        )
    
    def dfs(self, start_node: NodeId, max_depth: Optional[int] = None,
           node_filter: Optional[NodeFilter] = None,
           edge_filter: Optional[EdgeFilter] = None) -> TraversalResult:
        """
        Depth-First Search traversal.
        
        Args:
            start_node: Starting node ID
            max_depth: Maximum depth to traverse
            node_filter: Optional node filter function
            edge_filter: Optional edge filter function
            
        Returns:
            TraversalResult containing visited nodes, edges, depth, and paths
        """
        if start_node not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(start_node)
        
        visited = set()
        stack = [(start_node, 0)]  # (node, depth)
        visited_nodes = set()
        visited_edges = []
        paths = {start_node: [start_node]}
        current_depth = 0
        
        while stack:
            node, depth = stack.pop()
            
            if node in visited:
                continue
            
            visited.add(node)
            visited_nodes.add(node)
            current_depth = max(current_depth, depth)
            
            # Check max depth
            if max_depth is not None and depth >= max_depth:
                continue
            
            # Get neighbors (LIFO order for DFS)
            for neighbor, edge in reversed(list(self.neighbors_out(node, edge_filter=edge_filter))):
                if neighbor not in visited:
                    # Apply node filter
                    if node_filter:
                        neighbor_attrs = self.graph.graph["nodes"].get(neighbor, {})
                        if not node_filter(neighbor, neighbor_attrs):
                            continue
                    
                    stack.append((neighbor, depth + 1))
                    visited_edges.append(edge)
                    
                    # Track path
                    if neighbor not in paths:
                        paths[neighbor] = paths[node] + [neighbor]
        
        return TraversalResult(
            nodes=visited_nodes,
            edges=visited_edges,
            depth=current_depth,
            paths=list(paths.values())
        )
    
    def shortest_path(self, start: NodeId, end: NodeId,
                     edge_filter: Optional[EdgeFilter] = None) -> Optional[List[NodeId]]:
        """
        Find shortest path between two nodes using BFS.
        
        Args:
            start: Starting node ID
            end: Ending node ID
            edge_filter: Optional edge filter function
            
        Returns:
            List of node IDs representing the path, or None if no path exists
            
        Raises:
            NodeNotFoundError: If either node doesn't exist
        """
        if start not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(start)
        if end not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(end)
        
        if start == end:
            return [start]
        
        visited = set()
        queue = deque([(start, [start])])
        
        while queue:
            node, path = queue.popleft()
            
            if node in visited:
                continue
            
            visited.add(node)
            
            for neighbor, edge in self.neighbors_out(node, edge_filter=edge_filter):
                if neighbor == end:
                    return path + [neighbor]
                
                if neighbor not in visited:
                    queue.append((neighbor, path + [neighbor]))
        
        return None
    
    def all_shortest_paths(self, start: NodeId, end: NodeId,
                          edge_filter: Optional[EdgeFilter] = None) -> List[List[NodeId]]:
        """
        Find all shortest paths between two nodes.
        
        Args:
            start: Starting node ID
            end: Ending node ID
            edge_filter: Optional edge filter function
            
        Returns:
            List of paths, each path is a list of node IDs
        """
        if start not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(start)
        if end not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(end)
        
        if start == end:
            return [[start]]
        
        # BFS to find shortest distance
        visited = set()
        queue = deque([(start, [start])])
        found_paths = []
        shortest_length = None
        
        while queue and (shortest_length is None):
            node, path = queue.popleft()
            
            if node in visited:
                continue
            
            visited.add(node)
            
            for neighbor, edge in self.neighbors_out(node, edge_filter=edge_filter):
                if neighbor == end:
                    found_path = path + [neighbor]
                    found_paths.append(found_path)
                    shortest_length = len(found_path)
                    break
                
                if neighbor not in visited:
                    if shortest_length is None or len(path) + 1 < shortest_length:
                        queue.append((neighbor, path + [neighbor]))
        
        return found_paths
    
    def connected_components(self, edge_filter: Optional[EdgeFilter] = None) -> List[Set[NodeId]]:
        """
        Find all connected components in the graph.
        
        Args:
            edge_filter: Optional edge filter function
            
        Returns:
            List of sets, each containing node IDs for a component
        """
        visited = set()
        components = []
        
        for node_id in self.graph.graph["nodes"]:
            if node_id not in visited:
                # BFS to find component
                component = set()
                queue = deque([node_id])
                
                while queue:
                    current = queue.popleft()
                    if current in visited:
                        continue
                    
                    visited.add(current)
                    component.add(current)
                    
                    # Add all neighbors
                    for neighbor, _ in self.neighbors(current, edge_filter=edge_filter):
                        if neighbor not in visited:
                            queue.append(neighbor)
                
                components.append(component)
        
        return components
    
    def weakly_connected_components(self) -> List[Set[NodeId]]:
        """
        Find weakly connected components (treating edges as undirected).
        
        Returns:
            List of sets, each containing node IDs for a component
        """
        visited = set()
        components = []
        
        for node_id in self.graph.graph["nodes"]:
            if node_id not in visited:
                # BFS treating edges as undirected
                component = set()
                queue = deque([node_id])
                
                while queue:
                    current = queue.popleft()
                    if current in visited:
                        continue
                    
                    visited.add(current)
                    component.add(current)
                    
                    # Add both incoming and outgoing neighbors
                    for neighbor, _ in self.neighbors(current):
                        if neighbor not in visited:
                            queue.append(neighbor)
                
                components.append(component)
        
        return components
    
    def topological_sort(self) -> Optional[List[NodeId]]:
        """
        Perform topological sort on directed acyclic graph.
        
        Returns:
            List of node IDs in topological order, or None if graph has cycles
        """
        # Calculate in-degrees
        in_degrees = defaultdict(int)
        for node_id in self.graph.graph["nodes"]:
            in_degrees[node_id] = 0
        
        for edge in self.graph._edges.values():
            in_degrees[edge.dst] += 1
        
        # Queue of nodes with no incoming edges
        queue = deque([node for node, degree in in_degrees.items() if degree == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            # Reduce in-degree of neighbors
            for neighbor, _ in self.neighbors_out(node):
                in_degrees[neighbor] -= 1
                if in_degrees[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check if all nodes were processed (no cycles)
        if len(result) != len(self.graph.graph["nodes"]):
            return None  # Graph has cycles
        
        return result
    
    def has_cycles(self) -> bool:
        """
        Check if the graph contains cycles.
        
        Returns:
            True if graph has cycles, False otherwise
        """
        # Simple cycle detection using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle_dfs(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor, _ in self.neighbors_out(node):
                if has_cycle_dfs(neighbor):
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node_id in self.graph.graph["nodes"]:
            if node_id not in visited:
                if has_cycle_dfs(node_id):
                    return True
        
        return False
    
    def find_paths(self, start: NodeId, end: NodeId, max_length: Optional[int] = None,
                  edge_filter: Optional[EdgeFilter] = None) -> Generator[List[NodeId], None, None]:
        """
        Find all paths between two nodes up to a maximum length.
        
        Args:
            start: Starting node ID
            end: Ending node ID
            max_length: Maximum path length
            edge_filter: Optional edge filter function
            
        Yields:
            Paths as lists of node IDs
        """
        if start not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(start)
        if end not in self.graph.graph["nodes"]:
            raise NodeNotFoundError(end)
        
        def dfs_path(current, path, visited):
            if current == end:
                yield path.copy()
                return
            
            if max_length is not None and len(path) >= max_length:
                return
            
            for neighbor, edge in self.neighbors_out(current, edge_filter=edge_filter):
                if neighbor not in visited:
                    visited.add(neighbor)
                    path.append(neighbor)
                    
                    yield from dfs_path(neighbor, path, visited)
                    
                    path.pop()
                    visited.remove(neighbor)
        
        yield from dfs_path(start, [start], {start})
    
    def __repr__(self) -> str:
        """String representation."""
        return f"TraversalOperations(graph.nodes={len(self.graph.graph['nodes'])})"
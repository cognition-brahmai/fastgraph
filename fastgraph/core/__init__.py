"""
Core FastGraph functionality

This module contains the core graph database components including:
- FastGraph: Main graph database class
- Edge: Edge dataclass and operations
- SubgraphView: Memory-efficient subgraph views
- Indexing: Node and edge indexing
- Traversal: Graph traversal operations
- Persistence: Save/load operations
"""

from .graph import FastGraph
from .edge import Edge
from .subgraph import SubgraphView
from .indexing import IndexManager
from .traversal import TraversalOperations

__all__ = [
    "FastGraph",
    "Edge",
    "SubgraphView", 
    "IndexManager",
    "TraversalOperations",
]
"""
FastGraph v2: High-Performance In-Memory Graph Database

A fast, memory-efficient graph database with:
- O(1) edge lookups using adjacency lists
- Automatic indexing for fast queries
- Batch operations for bulk data
- Memory-efficient subgraph views
- Compressed persistence with msgpack
- Configuration-driven setup
- CLI tools for common operations
"""

from __future__ import annotations

__version__ = "2.0.0"
__author__ = "FastGraph Team"
__email__ = "hello@brahmai.in"
__description__ = "High-performance in-memory graph database"

# Core exports
from .core.graph import FastGraph
from .core.edge import Edge
from .core.subgraph import SubgraphView

# Configuration exports
from .config.manager import ConfigManager
from .config.defaults import get_default_config

# Exception exports
from .exceptions import (
    FastGraphError,
    ConfigurationError,
    NodeNotFoundError,
    EdgeNotFoundError,
    IndexNotFoundError,
    PersistenceError,
    CLIError,
)

# Type exports
from .types import NodeId, NodeAttrs

__all__ = [
    # Version info
    "__version__",
    "__author__", 
    "__email__",
    "__description__",
    
    # Core classes
    "FastGraph",
    "Edge", 
    "SubgraphView",
    
    # Configuration
    "ConfigManager",
    "get_default_config",
    
    # Exceptions
    "FastGraphError",
    "ConfigurationError",
    "NodeNotFoundError", 
    "EdgeNotFoundError",
    "IndexNotFoundError",
    "PersistenceError",
    "CLIError",
    
    # Types
    "NodeId",
    "NodeAttrs",
]

# Initialize logging
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
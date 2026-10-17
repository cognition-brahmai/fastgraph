"""FastGraph: embedded native property graphs and compound-node traversal."""

from __future__ import annotations

__version__ = "3.0.0"
__author__ = "BRAHMAI"
__email__ = "hello@brahmai.in"
__description__ = "Embedded native property graphs with scoped, nested traversal"

# Core exports
from .core.graph import FastGraph
from .core.edge import Edge
from .core.node import NodeRef
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
    ValidationError,
    ClosedGraphError,
    StaleReferenceError,
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
    "NodeRef",
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
    "ValidationError",
    "ClosedGraphError",
    "StaleReferenceError",
    # Types
    "NodeId",
    "NodeAttrs",
]

# Initialize logging
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

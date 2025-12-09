"""
Type definitions for FastGraph

This module contains common type definitions used throughout the FastGraph package.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Iterator, Callable
from pathlib import Path

# Import Edge for type annotations
from .core.edge import Edge

# Basic types
NodeId = str
NodeAttrs = Dict[str, Any]
EdgeAttrs = Dict[str, Any]

# Edge representation
EdgeKey = Tuple[NodeId, NodeId, str]

# Filter types
NodeFilter = Callable[[NodeId, NodeAttrs], bool]
EdgeFilter = Callable[[Edge], bool]

# Batch operation types
NodeBatch = List[Tuple[NodeId, NodeAttrs]]
EdgeBatch = List[Tuple[NodeId, NodeId, str, Optional[EdgeAttrs]]]

# Query result types
NodeResult = List[Tuple[NodeId, NodeAttrs]]
EdgeResult = List[Edge]
NodeResultTuple = Tuple[Tuple[NodeId, NodeAttrs], ...]

# Index types
IndexValue = Any
IndexMap = Dict[IndexValue, Set[NodeId]]

# Persistence types
FormatType = Union[str, Path]
PersistenceFormat = str  # "msgpack", "pickle", "json"

# Statistics types
Stats = Dict[str, int]
MemoryStats = Dict[str, int]

# Config types
ConfigValue = Union[str, int, float, bool, Dict[str, Any], List[Any]]
ConfigDict = Dict[str, ConfigValue]

# CLI types
CLICommand = Callable[..., None]
CLIOptions = Dict[str, Any]

# Threading types
LockType = Any  # Could be threading.Lock, threading.RLock, etc.

# Cache types
CacheKey = Any
CacheValue = Any

# Performance metrics
PerformanceMetrics = Dict[str, float]

# Error handling types
ErrorHandler = Callable[[Exception], None]

# Serialization types
Serializable = Union[str, int, float, bool, Dict, List, Tuple, None]

# File system types
FilePath = Union[str, Path]
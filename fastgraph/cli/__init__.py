"""
Command-line interface for FastGraph

This module provides CLI tools for common FastGraph operations including:
- Graph creation and management
- Data import and export
- Statistics and analysis
- Configuration management
"""

from .main import main
from .commands import *

__all__ = [
    "main",
]
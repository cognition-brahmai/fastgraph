"""
Path and format resolution utilities for FastGraph

This module provides intelligent path resolution and format detection
capabilities for automatic graph file discovery and management.
"""

import os
import gzip
from pathlib import Path
from typing import List, Optional, Union, Dict, Any, Tuple
import logging

from ..types import FormatType, PersistenceFormat
from ..exceptions import PersistenceError, ValidationError


logger = logging.getLogger(__name__)


class PathResolver:
    """
    Intelligent path and format resolution for FastGraph.
    
    Provides automatic path detection, format detection from file extensions
    and content inspection, and smart path resolution based on graph names
    and configuration.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize PathResolver with configuration.
        
        Args:
            config: Configuration dictionary containing path settings
        """
        self.config = config or {}
        self._supported_formats = {"msgpack", "pickle", "json"}
        
        # Default search paths for graph files
        self._default_search_paths = self._get_default_search_paths()
        
        # Format signatures for content-based detection
        self._format_signatures = {
            "json": [b'{', b'['],  # JSON starts with { or [
            "msgpack": [],  # msgpack is binary, harder to detect
            "pickle": [b'\x80', b'\x00'],  # pickle protocol markers
        }
    
    def resolve_path(self, path_hint: Optional[Union[str, Path]] = None, 
                    graph_name: Optional[str] = None, 
                    format: Optional[str] = None) -> Path:
        """
        Resolve a file path for graph storage/loading.
        
        Args:
            path_hint: User-provided path hint (can be partial)
            graph_name: Name of the graph for auto-naming
            format: Expected format for extension detection
            
        Returns:
            Resolved absolute Path object
            
        Raises:
            ValidationError: If parameters are invalid
            PersistenceError: If path resolution fails
        """
        try:
            # Handle different input scenarios
            if path_hint:
                path = Path(path_hint)
                
                # If it's already an absolute path that exists, return it
                if path.is_absolute() and (path.exists() or path.parent.exists()):
                    return self._ensure_format_extension(path, format)
                
                # If it's a relative path, try to resolve it
                if not path.is_absolute():
                    resolved_path = self._resolve_relative_path(path, graph_name, format)
                    if resolved_path:
                        return resolved_path
                
                # If path doesn't exist, treat as a filename to be created in default location
                if not path.exists():
                    return self._create_default_path(path.name, graph_name, format)
            
            # No path hint provided, create default path
            return self._create_default_path(None, graph_name, format)
            
        except Exception as e:
            raise PersistenceError(f"Failed to resolve path: {e}", 
                                operation="resolve_path", 
                                file_path=str(path_hint))
    
    def detect_format(self, path: Union[str, Path]) -> Optional[str]:
        """
        Detect file format from path extension and content.
        
        Args:
            path: File path to analyze
            
        Returns:
            Detected format string or None if unknown
            
        Raises:
            PersistenceError: If format detection fails
        """
        path = Path(path)
        
        if not path.exists():
            # Try to detect from extension only for non-existent files
            return self._detect_format_from_extension(path)
        
        try:
            # First try to detect from extension
            format_from_ext = self._detect_format_from_extension(path)
            if format_from_ext:
                # Verify with content inspection
                if self._verify_format_with_content(path, format_from_ext):
                    return format_from_ext
            
            # If extension detection fails, try content inspection
            return self._detect_format_from_content(path)
            
        except Exception as e:
            logger.warning(f"Format detection failed for {path}: {e}")
            return None
    
    def ensure_directory(self, path: Union[str, Path]) -> Path:
        """
        Ensure directory exists for the given path.
        
        Args:
            path: Path whose parent directory should exist
            
        Returns:
            Path object with ensured directory
            
        Raises:
            PersistenceError: If directory creation fails
        """
        path = Path(path)
        
        try:
            if path.is_file():
                directory = path.parent
            else:
                directory = path
            
            directory.mkdir(parents=True, exist_ok=True)
            return path
            
        except Exception as e:
            raise PersistenceError(f"Failed to create directory for {path}: {e}",
                                operation="ensure_directory",
                                file_path=str(path))
    
    def find_graph_file(self, name: str, search_paths: Optional[List[Path]] = None) -> Optional[Path]:
        """
        Find a graph file by name across multiple search paths.
        
        Args:
            name: Graph name to search for
            search_paths: List of paths to search in (uses defaults if None)
            
        Returns:
            Path to found graph file or None if not found
        """
        search_paths = search_paths or self._default_search_paths
        
        # Try different format combinations
        for format in self._supported_formats:
            for search_path in search_paths:
                # Try with format extension
                file_path = search_path / f"{name}.{format}"
                if file_path.exists():
                    return file_path
                
                # Try with common variations
                variations = [
                    f"{name}.graph.{format}",
                    f"{name}_graph.{format}",
                    f"{name}-graph.{format}",
                ]
                
                for variation in variations:
                    file_path = search_path / variation
                    if file_path.exists():
                        return file_path
        
        return None
    
    def get_default_path(self, graph_name: str, format: Optional[str] = None) -> Path:
        """
        Get default storage path for a graph.
        
        Args:
            graph_name: Name of the graph
            format: Format to use for extension
            
        Returns:
            Default Path object for graph storage
        """
        format = format or self.config.get("storage", {}).get("default_format", "msgpack")
        default_dir = Path(self.config.get("storage", {}).get("data_dir", "~/.cache/fastgraph/data"))
        default_dir = default_dir.expanduser()
        
        return default_dir / f"{graph_name}.{format}"
    
    def _get_default_search_paths(self) -> List[Path]:
        """Get default search paths for graph files."""
        paths = []
        
        # Add configured data directory
        data_dir = self.config.get("storage", {}).get("data_dir", "~/.cache/fastgraph/data")
        paths.append(Path(data_dir).expanduser())
        
        # Add current working directory
        paths.append(Path.cwd())
        
        # Add user home directory
        paths.append(Path.home() / ".fastgraph")
        
        # Add common locations
        common_locations = [
            Path.home() / ".cache" / "fastgraph",
            Path.home() / ".local" / "share" / "fastgraph",
        ]
        paths.extend(common_locations)
        
        return [p for p in paths if p.exists() or p.parent.exists()]
    
    def _resolve_relative_path(self, path: Path, graph_name: Optional[str], 
                              format: Optional[str]) -> Optional[Path]:
        """Resolve relative path against search locations."""
        # Try against each search path
        for search_path in self._default_search_paths:
            resolved = search_path / path
            if resolved.exists() or resolved.parent.exists():
                return self._ensure_format_extension(resolved, format)
        
        return None
    
    def _create_default_path(self, filename: Optional[str], graph_name: Optional[str], 
                           format: Optional[str]) -> Path:
        """Create default path for graph storage."""
        if not filename:
            filename = graph_name or "graph"
        
        # Clean filename
        filename = Path(filename).stem  # Remove any extension
        
        format = format or self.config.get("storage", {}).get("default_format", "msgpack")
        default_dir = Path(self.config.get("storage", {}).get("data_dir", "~/.cache/fastgraph/data"))
        default_dir = default_dir.expanduser()
        
        return default_dir / f"{filename}.{format}"
    
    def _ensure_format_extension(self, path: Path, format: Optional[str]) -> Path:
        """Ensure path has correct format extension."""
        if not format:
            return path
        
        # Remove existing extension if it doesn't match format
        if path.suffix and path.suffix.lower() != f".{format.lower()}":
            path = path.with_suffix("")
        
        # Add correct extension
        if path.suffix != f".{format}":
            path = path.with_suffix(f".{format}")
        
        return path
    
    def _detect_format_from_extension(self, path: Path) -> Optional[str]:
        """Detect format from file extension."""
        extension = path.suffix.lower()
        
        format_map = {
            ".json": "json",
            ".msgpack": "msgpack", 
            ".mp": "msgpack",
            ".pickle": "pickle",
            ".pkl": "pickle",
        }
        
        return format_map.get(extension)
    
    def _detect_format_from_content(self, path: Path) -> Optional[str]:
        """Detect format by inspecting file content."""
        try:
            with open(path, "rb") as f:
                # Read first few bytes for signature detection
                header = f.read(16)
                
                # Check for gzip compression
                if header.startswith(b'\x1f\x8b'):
                    # File is compressed, try to read first bytes after decompression
                    f.seek(0)
                    with gzip.open(f, 'rb') as gz_file:
                        header = gz_file.read(16)
                
                # Check against format signatures
                for format, signatures in self._format_signatures.items():
                    for signature in signatures:
                        if header.startswith(signature):
                            return format
                
                # Additional content-based checks
                if self._is_json_content(header):
                    return "json"
                elif self._is_pickle_content(header):
                    return "pickle"
                elif self._is_msgpack_content(header):
                    return "msgpack"
        
        except Exception as e:
            logger.warning(f"Content inspection failed for {path}: {e}")
        
        return None
    
    def _verify_format_with_content(self, path: Path, expected_format: str) -> bool:
        """Verify detected format matches content."""
        try:
            actual_format = self._detect_format_from_content(path)
            return actual_format == expected_format
        except Exception:
            return False
    
    def _is_json_content(self, header: bytes) -> bool:
        """Check if content appears to be JSON."""
        try:
            # JSON should start with { or [
            return header.startswith(b'{') or header.startswith(b'[')
        except Exception:
            return False
    
    def _is_pickle_content(self, header: bytes) -> bool:
        """Check if content appears to be pickle."""
        try:
            # Pickle protocol markers
            return header.startswith(b'\x80') or header.startswith(b'\x00')
        except Exception:
            return False
    
    def _is_msgpack_content(self, bytes_data: bytes) -> bool:
        """Check if content appears to be msgpack."""
        try:
            import msgpack
            # Try to unpack first few bytes as msgpack
            msgpack.unpackb(bytes_data[:min(16, len(bytes_data))], raw=False)
            return True
        except Exception:
            return False
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported formats."""
        return list(self._supported_formats)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"PathResolver(formats={self._supported_formats}, search_paths={len(self._default_search_paths)})"
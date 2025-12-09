"""
Persistence operations for FastGraph

This module handles saving and loading graph data in various formats
with support for compression and streaming operations.
"""

import pickle
import json
import msgpack
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import time
import threading
from contextlib import contextmanager

from ..types import FormatType, PersistenceFormat, IndexValue
from ..exceptions import PersistenceError
from .edge import Edge


class PersistenceManager:
    """
    Handles graph persistence operations with multiple format support.
    
    Supports saving and loading graphs in various formats with compression,
    streaming for large graphs, and thread safety.
    """
    
    def __init__(self, lock):
        """
        Initialize persistence manager.
        
        Args:
            lock: Threading lock for thread-safe operations
        """
        self.lock = lock
        self._supported_formats = {"msgpack", "pickle", "json"}
    
    def save(self, graph_data: Dict[str, Any], path: FormatType, 
             format: str = "msgpack", compress: bool = True) -> None:
        """
        Save graph data to file.
        
        Args:
            graph_data: Graph data dictionary
            path: File path to save to
            format: File format ("msgpack", "pickle", "json")
            compress: Whether to use compression
            
        Raises:
            PersistenceError: If save fails
            ValidationError: If parameters are invalid
        """
        path = Path(path)
        format = format.lower()
        
        if format not in self._supported_formats:
            raise PersistenceError(f"Unsupported format: {format}. Supported formats: {self._supported_formats}",
                                operation="save", format=format)
        
        try:
            # Prepare data for saving
            save_data = self._prepare_save_data(graph_data)
            
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with self.lock:
                start_time = time.time()
                
                if format == "msgpack":
                    self._save_msgpack(save_data, path, compress)
                elif format == "pickle":
                    self._save_pickle(save_data, path, compress)
                elif format == "json":
                    self._save_json(save_data, path, compress)
                else:
                    raise PersistenceError(f"Unsupported format: {format}",
                                        operation="save", format=format)
                
                save_time = time.time() - start_time
                file_size = path.stat().st_size
                
                # Log statistics (in real implementation, would use proper logging)
                print(f"Saved graph in {save_time:.3f}s, size: {file_size:,} bytes")
                
        except Exception as e:
            raise PersistenceError(f"Failed to save graph to {path}: {e}",
                                operation="save", file_path=str(path), format=format)
    
    def load(self, path: FormatType, format: str = "msgpack") -> Dict[str, Any]:
        """
        Load graph data from file.
        
        Args:
            path: File path to load from
            format: File format ("msgpack", "pickle", "json")
            
        Returns:
            Loaded graph data dictionary
            
        Raises:
            PersistenceError: If load fails
            ValidationError: If parameters are invalid
        """
        path = Path(path)
        format = format.lower()
        
        if not path.exists():
            raise PersistenceError(f"File not found: {path}",
                                operation="load", file_path=str(path), format=format)
        
        if format not in self._supported_formats:
            raise PersistenceError(f"Unsupported format: {format}. Supported formats: {self._supported_formats}",
                                operation="load", format=format)
        
        try:
            with self.lock:
                start_time = time.time()
                
                if format == "msgpack":
                    data = self._load_msgpack(path)
                elif format == "pickle":
                    data = self._load_pickle(path)
                elif format == "json":
                    data = self._load_json(path)
                else:
                    raise PersistenceError(f"Unsupported format: {format}",
                                        operation="load", file_path=str(path), format=format)
                
                load_time = time.time() - start_time
                
                # Validate and process loaded data
                processed_data = self._process_loaded_data(data)
                
                # Log statistics
                print(f"Loaded graph in {load_time:.3f}s, nodes: {len(processed_data.get('nodes', {}))}, edges: {len(data.get('edges', []))}")
                
                return processed_data
                
        except Exception as e:
            raise PersistenceError(f"Failed to load graph from {path}: {e}",
                                operation="load", file_path=str(path), format=format)
    
    def save_stream(self, graph_data: Dict[str, Any], path: FormatType,
                   format: str = "msgpack", chunk_size: int = 10000) -> None:
        """
        Save large graphs in streaming mode.
        
        Args:
            graph_data: Graph data dictionary
            path: File path to save to
            format: File format
            chunk_size: Number of items to process at once
        """
        path = Path(path)
        format = format.lower()
        
        if format not in {"msgpack", "json"}:
            raise PersistenceError(f"Streaming not supported for format: {format}",
                                operation="save_stream", format=format)
        
        try:
            with self.lock:
                if format == "msgpack":
                    self._save_stream_msgpack(graph_data, path, chunk_size)
                elif format == "json":
                    self._save_stream_json(graph_data, path, chunk_size)
                    
        except Exception as e:
            raise PersistenceError(f"Failed to save graph stream to {path}: {e}",
                                operation="save_stream", file_path=str(path), format=format)
    
    def load_stream(self, path: FormatType, format: str = "msgpack",
                   chunk_callback=None) -> Dict[str, Any]:
        """
        Load large graphs in streaming mode.
        
        Args:
            path: File path to load from
            format: File format
            chunk_callback: Optional callback for each chunk
            
        Returns:
            Loaded graph data
        """
        path = Path(path)
        format = format.lower()
        
        try:
            with self.lock:
                if format == "msgpack":
                    return self._load_stream_msgpack(path, chunk_callback)
                elif format == "json":
                    return self._load_stream_json(path, chunk_callback)
                else:
                    raise PersistenceError(f"Streaming not supported for format: {format}",
                                        operation="load_stream", format=format)
                    
        except Exception as e:
            raise PersistenceError(f"Failed to load graph stream from {path}: {e}",
                                operation="load_stream", file_path=str(path), format=format)
    
    @contextmanager
    def atomic_write(self, path: FormatType):
        """
        Context manager for atomic file writes.
        
        Args:
            path: File path to write to
        """
        path = Path(path)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        
        try:
            yield temp_path
            temp_path.rename(path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def _prepare_save_data(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare graph data for saving.
        
        Args:
            graph_data: Raw graph data
            
        Returns:
            Formatted data ready for saving
        """
        data = {
            "version": "2.0.0",
            "created_at": time.time(),
            "nodes": graph_data.get("nodes", {}),
            "edges": [edge.to_dict() for edge in graph_data.get("_edges", {}).values()],
            "metadata": graph_data.get("metadata", {}),
            "indexes": self._serialize_indexes(graph_data.get("node_indexes", {}))
        }
        
        return data
    
    def _process_loaded_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process and validate loaded data.
        
        Args:
            data: Raw loaded data
            
        Returns:
            Processed data ready for graph reconstruction
        """
        # Validate required fields
        if "nodes" not in data:
            raise PersistenceError("Invalid graph data: missing nodes field",
                                operation="load")
        
        # Process edges
        processed_edges = {}
        for edge_dict in data.get("edges", []):
            edge = Edge.from_dict(edge_dict)
            processed_edges[edge.key()] = edge
        
        # Process indexes
        processed_indexes = self._deserialize_indexes(data.get("indexes", {}))
        
        return {
            "nodes": data["nodes"],
            "edges": processed_edges,
            "metadata": data.get("metadata", {}),
            "indexes": processed_indexes
        }
    
    def _save_msgpack(self, data: Dict[str, Any], path: Path, compress: bool) -> None:
        """Save data using msgpack format."""
        with open(path, "wb") as f:
            if compress:
                import gzip
                with gzip.GzipFile(fileobj=f, mode='wb') as gz_file:
                    msgpack.pack(data, gz_file, use_bin_type=True)
            else:
                msgpack.pack(data, f, use_bin_type=True)
    
    def _load_msgpack(self, path: Path) -> Dict[str, Any]:
        """Load data using msgpack format."""
        with open(path, "rb") as f:
            # Check if file is gzipped
            f.seek(0)
            header = f.read(2)
            f.seek(0)
            
            if header == b'\x1f\x8b':  # gzip magic number
                import gzip
                with gzip.GzipFile(fileobj=f, mode='rb') as gz_file:
                    return msgpack.unpack(gz_file, raw=False)
            else:
                return msgpack.unpack(f, raw=False)
    
    def _save_pickle(self, data: Dict[str, Any], path: Path, compress: bool) -> None:
        """Save data using pickle format."""
        with open(path, "wb") as f:
            if compress:
                import gzip
                with gzip.GzipFile(fileobj=f, mode='wb') as gz_file:
                    pickle.dump(data, gz_file, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    def _load_pickle(self, path: Path) -> Dict[str, Any]:
        """Load data using pickle format."""
        with open(path, "rb") as f:
            # Check if file is gzipped
            f.seek(0)
            header = f.read(2)
            f.seek(0)
            
            if header == b'\x1f\x8b':  # gzip magic number
                import gzip
                with gzip.GzipFile(fileobj=f, mode='rb') as gz_file:
                    return pickle.load(gz_file)
            else:
                return pickle.load(f)
    
    def _save_json(self, data: Dict[str, Any], path: Path, compress: bool) -> None:
        """Save data using JSON format."""
        with open(path, "w") as f:
            if compress:
                import gzip
                with gzip.GzipFile(fileobj=f, mode='wt', encoding='utf-8') as gz_file:
                    json.dump(data, gz_file, indent=2, default=str)
            else:
                json.dump(data, f, indent=2, default=str)
    
    def _load_json(self, path: Path) -> Dict[str, Any]:
        """Load data using JSON format."""
        with open(path, "rb") as f:
            # Check if file is gzipped
            f.seek(0)
            header = f.read(2)
            f.seek(0)
            
            if header == b'\x1f\x8b':  # gzip magic number
                import gzip
                with gzip.GzipFile(fileobj=f, mode='rt', encoding='utf-8') as gz_file:
                    return json.load(gz_file)
            else:
                # Use text mode for regular JSON
                with open(path, "r", encoding='utf-8') as text_file:
                    return json.load(text_file)
    
    def _save_stream_msgpack(self, data: Dict[str, Any], path: Path, chunk_size: int) -> None:
        """Save large graph using streaming msgpack."""
        with open(path, "wb") as f:
            # Write metadata first
            metadata = {
                "version": "2.0.0",
                "created_at": time.time(),
                "metadata": data.get("metadata", {})
            }
            msgpack.pack({"metadata": metadata}, f, use_bin_type=True)
            
            # Stream nodes in chunks
            nodes = data.get("nodes", {})
            node_items = list(nodes.items())
            
            for i in range(0, len(node_items), chunk_size):
                chunk = dict(node_items[i:i + chunk_size])
                msgpack.pack({"nodes_chunk": chunk}, f, use_bin_type=True)
            
            # Stream edges in chunks
            edges = [edge.to_dict() for edge in data.get("_edges", {}).values()]
            for i in range(0, len(edges), chunk_size):
                chunk = edges[i:i + chunk_size]
                msgpack.pack({"edges_chunk": chunk}, f, use_bin_type=True)
    
    def _load_stream_msgpack(self, path: Path, chunk_callback=None) -> Dict[str, Any]:
        """Load large graph using streaming msgpack."""
        nodes = {}
        edges = []
        metadata = {}
        
        with open(path, "rb") as f:
            unpacker = msgpack.Unpacker(raw=False)
            
            while True:
                try:
                    data = unpacker.unpack(f)
                    
                    if "metadata" in data:
                        metadata = data["metadata"]
                    elif "nodes_chunk" in data:
                        nodes.update(data["nodes_chunk"])
                        if chunk_callback:
                            chunk_callback("nodes", data["nodes_chunk"])
                    elif "edges_chunk" in data:
                        edge_objects = [Edge.from_dict(edge_dict) for edge_dict in data["edges_chunk"]]
                        edges.extend(edge_objects)
                        if chunk_callback:
                            chunk_callback("edges", edge_objects)
                
                except EOFError:
                    break
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": metadata
        }
    
    def _save_stream_json(self, data: Dict[str, Any], path: Path, chunk_size: int) -> None:
        """Save large graph using streaming JSON."""
        with open(path, "w") as f:
            # Write metadata
            metadata = data.get("metadata", {})
            f.write('{"metadata":')
            json.dump(metadata, f, default=str)
            f.write('}\n')
            
            # Stream nodes
            nodes = data.get("nodes", {})
            node_items = list(nodes.items())
            
            for i in range(0, len(node_items), chunk_size):
                chunk = dict(node_items[i:i + chunk_size])
                f.write('{"nodes_chunk":')
                json.dump(chunk, f, default=str)
                f.write('}\n')
            
            # Stream edges
            edges = [edge.to_dict() for edge in data.get("_edges", {}).values()]
            for i in range(0, len(edges), chunk_size):
                chunk = edges[i:i + chunk_size]
                f.write('{"edges_chunk":')
                json.dump(chunk, f, default=str)
                f.write('}\n')
    
    def _load_stream_json(self, path: Path, chunk_callback=None) -> Dict[str, Any]:
        """Load large graph using streaming JSON."""
        nodes = {}
        edges = []
        metadata = {}
        
        with open(path, "r") as f:
            for line in f:
                data = json.loads(line.strip())
                
                if "metadata" in data:
                    metadata = data["metadata"]
                elif "nodes_chunk" in data:
                    nodes.update(data["nodes_chunk"])
                    if chunk_callback:
                        chunk_callback("nodes", data["nodes_chunk"])
                elif "edges_chunk" in data:
                    edge_objects = [Edge.from_dict(edge_dict) for edge_dict in data["edges_chunk"]]
                    edges.extend(edge_objects)
                    if chunk_callback:
                        chunk_callback("edges", edge_objects)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": metadata
        }
    
    def _serialize_indexes(self, indexes: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize indexes for storage."""
        serialized = {}
        for attr_name, index in indexes.items():
            serialized[attr_name] = {
                str(value): list(node_set) for value, node_set in index.items()
            }
        return serialized
    
    def _deserialize_indexes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Deserialize indexes from storage."""
        deserialized = {}
        for attr_name, index_data in data.items():
            # Convert string keys back to appropriate types
            deserialized[attr_name] = {
                self._convert_key(key): set(node_set) 
                for key, node_set in index_data.items()
            }
        return deserialized
    
    def _convert_key(self, key: str) -> IndexValue:
        """Convert string key back to appropriate type."""
        # Try to parse as int, then float, then keep as string
        try:
            return int(key)
        except ValueError:
            try:
                return float(key)
            except ValueError:
                if key.lower() in ('true', 'false'):
                    return key.lower() == 'true'
                return key
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported formats."""
        return list(self._supported_formats)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"PersistenceManager(formats={self._supported_formats})"
"""
Custom exceptions for FastGraph

This module defines all custom exception classes used throughout the FastGraph package.
"""


class FastGraphError(Exception):
    """Base exception class for all FastGraph errors."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


class ConfigurationError(FastGraphError):
    """Raised when there's an error in configuration."""
    
    def __init__(self, message: str, config_path: str = None, config_key: str = None):
        super().__init__(message)
        self.config_path = config_path
        self.config_key = config_key
        self.details = {
            "config_path": config_path,
            "config_key": config_key,
        }


class NodeNotFoundError(FastGraphError):
    """Raised when a requested node is not found."""
    
    def __init__(self, node_id: str):
        message = f"Node '{node_id}' not found"
        super().__init__(message)
        self.node_id = node_id
        self.details = {"node_id": node_id}


class EdgeNotFoundError(FastGraphError):
    """Raised when a requested edge is not found."""
    
    def __init__(self, src: str = None, dst: str = None, rel: str = None):
        details = {}
        if src:
            details["src"] = src
        if dst:
            details["dst"] = dst
        if rel:
            details["rel"] = rel
            
        message_parts = []
        if src:
            message_parts.append(f"src='{src}'")
        if dst:
            message_parts.append(f"dst='{dst}'")
        if rel:
            message_parts.append(f"rel='{rel}'")
            
        message = f"Edge not found with {', '.join(message_parts)}"
        super().__init__(message, details)
        self.src = src
        self.dst = dst
        self.rel = rel


class IndexNotFoundError(FastGraphError):
    """Raised when a requested index is not found."""
    
    def __init__(self, index_name: str):
        message = f"Index '{index_name}' not found"
        super().__init__(message)
        self.index_name = index_name
        self.details = {"index_name": index_name}


class PersistenceError(FastGraphError):
    """Raised when there's an error in save/load operations."""
    
    def __init__(self, message: str, file_path: str = None, operation: str = None, format: str = None):
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation  # "save" or "load"
        self.format = format
        self.details = {
            "file_path": file_path,
            "operation": operation,
            "format": format,
        }


class IndexingError(FastGraphError):
    """Raised when there's an error in index operations."""
    
    def __init__(self, message: str, index_name: str = None, operation: str = None):
        super().__init__(message)
        self.index_name = index_name
        self.operation = operation
        self.details = {
            "index_name": index_name,
            "operation": operation,
        }


class TraversalError(FastGraphError):
    """Raised when there's an error in graph traversal operations."""
    
    def __init__(self, message: str, node_id: str = None, operation: str = None):
        super().__init__(message)
        self.node_id = node_id
        self.operation = operation
        self.details = {
            "node_id": node_id,
            "operation": operation,
        }


class MemoryError(FastGraphError):
    """Raised when there's insufficient memory for operations."""
    
    def __init__(self, message: str, operation: str = None, memory_required: int = None):
        super().__init__(message)
        self.operation = operation
        self.memory_required = memory_required
        self.details = {
            "operation": operation,
            "memory_required": memory_required,
        }


class ValidationError(FastGraphError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, field: str = None, value: any = None):
        super().__init__(message)
        self.field = field
        self.value = value
        self.details = {
            "field": field,
            "value": value,
        }


class CLIError(FastGraphError):
    """Raised when there's an error in CLI operations."""
    
    def __init__(self, message: str, command: str = None, args: dict = None):
        super().__init__(message)
        self.command = command
        self.args = args or {}
        self.details = {
            "command": command,
            "args": self.args,
        }


class ConcurrencyError(FastGraphError):
    """Raised when there's a concurrency-related error."""
    
    def __init__(self, message: str, operation: str = None, thread_id: int = None):
        super().__init__(message)
        self.operation = operation
        self.thread_id = thread_id
        self.details = {
            "operation": operation,
            "thread_id": thread_id,
        }


class CacheError(FastGraphError):
    """Raised when there's an error in cache operations."""
    
    def __init__(self, message: str, cache_key: str = None, operation: str = None):
        super().__init__(message)
        self.cache_key = cache_key
        self.operation = operation
        self.details = {
            "cache_key": cache_key,
            "operation": operation,
        }


class BatchOperationError(FastGraphError):
    """Raised when batch operations fail."""
    
    def __init__(self, message: str, batch_type: str = None, batch_size: int = None, 
                 failed_index: int = None, error_count: int = None):
        super().__init__(message)
        self.batch_type = batch_type
        self.batch_size = batch_size
        self.failed_index = failed_index
        self.error_count = error_count
        self.details = {
            "batch_type": batch_type,
            "batch_size": batch_size,
            "failed_index": failed_index,
            "error_count": error_count,
        }


# Error handling utilities
def handle_fastgraph_error(func):
    """Decorator to handle FastGraph errors consistently."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FastGraphError:
            # Re-raise FastGraph errors as-is
            raise
        except Exception as e:
            # Wrap other exceptions as FastGraphError
            raise FastGraphError(f"Unexpected error in {func.__name__}: {str(e)}")
    return wrapper


def format_error(error: Exception) -> str:
    """Format an error for user display."""
    if isinstance(error, FastGraphError):
        return str(error)
    return f"Error: {str(error)}"


def get_error_details(error: Exception) -> dict:
    """Get detailed error information."""
    if isinstance(error, FastGraphError):
        return error.details.copy()
    return {"type": type(error).__name__, "message": str(error)}
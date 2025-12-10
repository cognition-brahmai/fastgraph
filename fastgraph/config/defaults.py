"""
Default configuration values for FastGraph

This module contains the default configuration settings based on the example_config.json file.
"""

import os
from typing import Dict, Any
from pathlib import Path


def get_default_config() -> Dict[str, Any]:
    """
    Get the default configuration for FastGraph.
    
    Returns:
        Dictionary containing default configuration values
        
    The defaults are based on the example_config.json structure:
    - Engine settings
    - Storage configuration  
    - Memory and cache settings
    - Indexing options
    - Performance parameters
    """
    return {
        "engine": {
            "name": "FastGraph",
            "version": "2.0.0"
        },
        
        "storage": {
            "data_dir": _expand_path("~/.cache/fastgraph/data"),
            "default_format": "msgpack",
            "backup_enabled": True,
            "backup_interval": 3600,  # seconds
            "max_backup_files": 5,
            "auto_create_directories": True,
            "backup_directory": _expand_path("~/.fastgraph/backups/"),
            "max_backups": 5,
            "compression_default": True,
            "atomic_writes": True,
            "default_directory": _expand_path("~/.fastgraph/graphs/")
        },
        
        "memory": {
            "query_cache_size": 128,
            "cache_ttl": 3600,  # seconds
            "memory_limit_mb": 1024,  # MB
            "gc_threshold": 0.8  # 80% of memory limit
        },
        
        "indexing": {
            "auto_index": True,
            "default_indexes": ["id", "type", "name"],
            "index_memory_limit_mb": 256,
            "batch_index_threshold": 1000
        },
        
        "performance": {
            "thread_pool_size": 4,
            "batch_threshold": 100,
            "optimize_for_memory": False,
            "compression_level": 6,
            "enable_profiling": False
        },
        
        "cli": {
            "default_output_format": "table",
            "verbose": False,
            "color_output": True,
            "progress_bar": True,
            "confirm_destructive": True
        },
        
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file_logging": False,
            "log_file": _expand_path("~/.cache/fastgraph/logs/fastgraph.log"),
            "max_log_size_mb": 10,
            "backup_log_count": 3
        },
        
        "security": {
            "validate_inputs": True,
            "max_node_id_length": 255,
            "max_attr_value_size": 1048576,  # 1MB
            "allowed_serialization_formats": ["msgpack", "pickle", "json"]
        },
        
        "network": {
            "enable_network": False,
            "host": "localhost",
            "port": 8080,
            "max_connections": 10,
            "timeout": 30
        },
        
        "enhanced_api": {
            "auto_save": False,
            "auto_cleanup": True,
            "format_detection": True,
            "path_resolution": True,
            "atomic_operations": True,
            "smart_defaults": True,
            "auto_discovery": True,
            "fallback_mechanisms": True
        },
        
        "resource_management": {
            "max_open_graphs": 10,
            "memory_limit_per_graph": "100MB",
            "cleanup_interval": 300,  # seconds
            "backup_on_close": False,
            "auto_cleanup": True,
            "memory_monitoring": True,
            "resource_tracking": True
        },
        
        "persistence": {
            "default_directory": _expand_path("~/.fastgraph/graphs/"),
            "auto_create_directories": True,
            "backup_directory": _expand_path("~/.fastgraph/backups/"),
            "max_backups": 5,
            "compression_default": True,
            "atomic_writes": True,
            "format_detection": True,
            "path_resolution": True
        }
    }


def get_config_schema() -> Dict[str, Any]:
    """
    Get the configuration schema for validation.
    
    Returns:
        Dictionary describing the expected configuration structure and types
    """
    return {
        "engine": {
            "type": "dict",
            "required": True,
            "properties": {
                "name": {"type": "string", "required": True},
                "version": {"type": "string", "required": True}
            }
        },
        
        "storage": {
            "type": "dict", 
            "required": True,
            "properties": {
                "data_dir": {"type": "string", "required": True},
                "default_format": {"type": "string", "required": True, "enum": ["msgpack", "pickle", "json"]},
                "backup_enabled": {"type": "boolean", "default": True},
                "backup_interval": {"type": "integer", "min": 60, "default": 3600},
                "max_backup_files": {"type": "integer", "min": 1, "default": 5}
            }
        },
        
        "memory": {
            "type": "dict",
            "required": True,
            "properties": {
                "query_cache_size": {"type": "integer", "min": 0, "default": 128},
                "cache_ttl": {"type": "integer", "min": 0, "default": 3600},
                "memory_limit_mb": {"type": "integer", "min": 64, "default": 1024},
                "gc_threshold": {"type": "float", "min": 0.1, "max": 1.0, "default": 0.8}
            }
        },
        
        "indexing": {
            "type": "dict",
            "required": True,
            "properties": {
                "auto_index": {"type": "boolean", "default": True},
                "default_indexes": {"type": "array", "items": {"type": "string"}, "default": ["id", "type", "name"]},
                "index_memory_limit_mb": {"type": "integer", "min": 16, "default": 256},
                "batch_index_threshold": {"type": "integer", "min": 10, "default": 1000}
            }
        },
        
        "performance": {
            "type": "dict",
            "required": True,
            "properties": {
                "thread_pool_size": {"type": "integer", "min": 1, "max": 32, "default": 4},
                "batch_threshold": {"type": "integer", "min": 1, "default": 100},
                "optimize_for_memory": {"type": "boolean", "default": False},
                "compression_level": {"type": "integer", "min": 1, "max": 9, "default": 6},
                "enable_profiling": {"type": "boolean", "default": False}
            }
        },
        
        "cli": {
            "type": "dict",
            "required": True,
            "properties": {
                "default_output_format": {"type": "string", "enum": ["table", "json", "yaml", "plain"], "default": "table"},
                "verbose": {"type": "boolean", "default": False},
                "color_output": {"type": "boolean", "default": True},
                "progress_bar": {"type": "boolean", "default": True},
                "confirm_destructive": {"type": "boolean", "default": True}
            }
        },
        
        "logging": {
            "type": "dict",
            "required": True,
            "properties": {
                "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], "default": "INFO"},
                "format": {"type": "string", "default": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
                "file_logging": {"type": "boolean", "default": False},
                "log_file": {"type": "string", "default": "~/.cache/fastgraph/logs/fastgraph.log"},
                "max_log_size_mb": {"type": "integer", "min": 1, "default": 10},
                "backup_log_count": {"type": "integer", "min": 1, "default": 3}
            }
        },
        
        "security": {
            "type": "dict",
            "required": True,
            "properties": {
                "validate_inputs": {"type": "boolean", "default": True},
                "max_node_id_length": {"type": "integer", "min": 1, "max": 1000, "default": 255},
                "max_attr_value_size": {"type": "integer", "min": 1024, "default": 1048576},
                "allowed_serialization_formats": {"type": "array", "items": {"type": "string"}, "default": ["msgpack", "pickle", "json"]}
            }
        },
        
        "network": {
            "type": "dict",
            "required": False,
            "properties": {
                "enable_network": {"type": "boolean", "default": False},
                "host": {"type": "string", "default": "localhost"},
                "port": {"type": "integer", "min": 1024, "max": 65535, "default": 8080},
                "max_connections": {"type": "integer", "min": 1, "max": 1000, "default": 10},
                "timeout": {"type": "integer", "min": 1, "default": 30}
            }
        },
        
        "enhanced_api": {
            "type": "dict",
            "required": True,
            "properties": {
                "auto_save": {"type": "boolean", "default": False},
                "auto_cleanup": {"type": "boolean", "default": True},
                "format_detection": {"type": "boolean", "default": True},
                "path_resolution": {"type": "boolean", "default": True},
                "atomic_operations": {"type": "boolean", "default": True},
                "smart_defaults": {"type": "boolean", "default": True},
                "auto_discovery": {"type": "boolean", "default": True},
                "fallback_mechanisms": {"type": "boolean", "default": True}
            }
        },
        
        "resource_management": {
            "type": "dict",
            "required": True,
            "properties": {
                "max_open_graphs": {"type": "integer", "min": 1, "max": 100, "default": 10},
                "memory_limit_per_graph": {"type": "string", "default": "100MB"},
                "cleanup_interval": {"type": "integer", "min": 10, "default": 300},
                "backup_on_close": {"type": "boolean", "default": False},
                "auto_cleanup": {"type": "boolean", "default": True},
                "memory_monitoring": {"type": "boolean", "default": True},
                "resource_tracking": {"type": "boolean", "default": True}
            }
        },
        
        "persistence": {
            "type": "dict",
            "required": True,
            "properties": {
                "default_directory": {"type": "string", "default": "~/.fastgraph/graphs/"},
                "auto_create_directories": {"type": "boolean", "default": True},
                "backup_directory": {"type": "string", "default": "~/.fastgraph/backups/"},
                "max_backups": {"type": "integer", "min": 1, "default": 5},
                "compression_default": {"type": "boolean", "default": True},
                "atomic_writes": {"type": "boolean", "default": True},
                "format_detection": {"type": "boolean", "default": True},
                "path_resolution": {"type": "boolean", "default": True}
            }
        }
    }


def _expand_path(path: str) -> str:
    """
    Expand user home directory in path.
    
    Args:
        path: Path that may contain ~
        
    Returns:
        Expanded absolute path
    """
    return str(Path(path).expanduser())


def get_env_config_mapping() -> Dict[str, str]:
    """
    Get mapping of environment variables to config keys.
    
    Returns:
        Dictionary mapping environment variable names to config key paths
    """
    return {
        "FASTGRAPH_DATA_DIR": "storage.data_dir",
        "FASTGRAPH_DEFAULT_FORMAT": "storage.default_format",
        "FASTGRAPH_CACHE_SIZE": "memory.query_cache_size",
        "FASTGRAPH_AUTO_INDEX": "indexing.auto_index",
        "FASTGRAPH_THREAD_POOL_SIZE": "performance.thread_pool_size",
        "FASTGRAPH_BATCH_THRESHOLD": "performance.batch_threshold",
        "FASTGRAPH_LOG_LEVEL": "logging.level",
        "FASTGRAPH_LOG_FILE": "logging.log_file",
        "FASTGRAPH_MEMORY_LIMIT": "memory.memory_limit_mb",
        "FASTGRAPH_VERBOSE": "cli.verbose",
        "FASTGRAPH_HOST": "network.host",
        "FASTGRAPH_PORT": "network.port"
    }


def get_user_config_paths() -> list:
    """
    Get possible user configuration file paths.
    
    Returns:
        List of possible config file paths in order of preference
    """
    home = Path.home()
    
    return [
        home / ".fastgraph" / "config.yaml",
        home / ".fastgraph" / "config.yml", 
        home / ".fastgraph" / "config.json",
        home / ".config" / "fastgraph" / "config.yaml",
        home / ".config" / "fastgraph" / "config.yml",
        home / ".config" / "fastgraph" / "config.json",
        Path.cwd() / "fastgraph.yaml",
        Path.cwd() / "fastgraph.yml", 
        Path.cwd() / "fastgraph.json",
    ]
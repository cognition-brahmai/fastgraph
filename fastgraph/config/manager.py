"""
Configuration manager for FastGraph

This module provides the main ConfigManager class that handles loading,
merging, and managing FastGraph configurations.
"""

import os
import json
import yaml
from typing import Any, Dict, Optional, Union
from pathlib import Path

from ..exceptions import ConfigurationError
from .defaults import get_default_config, get_config_schema, get_env_config_mapping, get_user_config_paths
from .validator import ConfigValidator


class ConfigManager:
    """
    Manages FastGraph configuration with hierarchical loading and validation.
    
    Configuration priority (highest to lowest):
    1. Direct parameters passed to ConfigManager
    2. Environment variables
    3. User configuration file
    4. Package default configuration
    
    Supported configuration file formats:
    - JSON (.json)
    - YAML (.yaml, .yml)
    """
    
    def __init__(self, config_file: Optional[Union[str, Path]] = None, 
                 config_dict: Optional[Dict[str, Any]] = None,
                 validate: bool = True):
        """
        Initialize the configuration manager.
        
        Args:
            config_file: Path to configuration file
            config_dict: Direct configuration dictionary (highest priority)
            validate: Whether to validate the configuration
        """
        self.config_file = config_file
        self.config_dict = config_dict
        self.validate = validate
        
        # Initialize validator
        self.validator = ConfigValidator(get_config_schema()) if validate else None
        
        # Load and cache configuration
        self._config = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load and process configuration."""
        # Start with defaults
        config = get_default_config()
        
        # Load user config if available
        user_config = self._load_user_config()
        if user_config:
            config = self._merge_configs(config, user_config)
        
        # Load specified config file if provided
        if self.config_file:
            file_config = self._load_config_file(self.config_file)
            if file_config:
                config = self._merge_configs(config, file_config)
        
        # Apply environment variables
        env_config = self._load_env_config()
        if env_config:
            config = self._merge_configs(config, env_config)
        
        # Apply direct config dict if provided
        if self.config_dict:
            config = self._merge_configs(config, self.config_dict)
        
        # Validate if requested
        if self.validate and self.validator:
            config = self.validator.validate(config)
        
        self._config = config
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the complete configuration.
        
        Returns:
            Configuration dictionary
        """
        return self._config.copy()
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value by key path.
        
        Args:
            key_path: Dot-separated key path (e.g., "storage.data_dir")
            default: Default value if key is not found
            
        Returns:
            Configuration value or default
            
        Example:
            config.get("storage.default_format") => "msgpack"
        """
        keys = key_path.split(".")
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path: str, value: Any) -> None:
        """
        Set a configuration value by key path.
        
        Args:
            key_path: Dot-separated key path
            value: Value to set
            
        Example:
            config.set("storage.default_format", "json")
        """
        keys = key_path.split(".")
        config = self._config
        
        # Navigate to parent
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # Set the final value
        config[keys[-1]] = value
    
    def reload(self) -> None:
        """Reload configuration from sources."""
        self._load_config()
    
    def save_config(self, file_path: Union[str, Path]) -> None:
        """
        Save current configuration to file.
        
        Args:
            file_path: Path to save configuration
        """
        file_path = Path(file_path)
        
        try:
            # Determine format from file extension
            if file_path.suffix.lower() in ['.yaml', '.yml']:
                with open(file_path, 'w') as f:
                    yaml.dump(self._config, f, default_flow_style=False, indent=2)
            elif file_path.suffix.lower() == '.json':
                with open(file_path, 'w') as f:
                    json.dump(self._config, f, indent=2, default=str)
            else:
                # Default to YAML
                with open(file_path, 'w') as f:
                    yaml.dump(self._config, f, default_flow_style=False, indent=2)
                    
        except Exception as e:
            raise ConfigurationError(
                f"Failed to save configuration to {file_path}: {e}",
                config_path=str(file_path)
            )
    
    def _load_user_config(self) -> Optional[Dict[str, Any]]:
        """
        Load user configuration from standard locations.
        
        Returns:
            User configuration dict or None
        """
        for config_path in get_user_config_paths():
            if config_path.exists():
                try:
                    return self._load_config_file(config_path)
                except Exception as e:
                    # Log warning but continue trying other paths
                    print(f"Warning: Failed to load config from {config_path}: {e}")
                    continue
        return None
    
    def _load_config_file(self, file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """
        Load configuration from a file.
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Configuration dict or None
            
        Raises:
            ConfigurationError: If file cannot be loaded
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {file_path}",
                config_path=str(file_path)
            )
        
        try:
            with open(file_path, 'r') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    return yaml.safe_load(f) or {}
                elif file_path.suffix.lower() == '.json':
                    return json.load(f) or {}
                else:
                    # Try to detect format based on content
                    content = f.read()
                    f.seek(0)
                    
                    if content.strip().startswith('{'):
                        return json.load(f) or {}
                    else:
                        return yaml.safe_load(f) or {}
                        
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML in config file {file_path}: {e}",
                config_path=str(file_path)
            )
        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in config file {file_path}: {e}",
                config_path=str(file_path)
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load config file {file_path}: {e}",
                config_path=str(file_path)
            )
    
    def _load_env_config(self) -> Dict[str, Any]:
        """
        Load configuration from environment variables.
        
        Returns:
            Configuration dict from environment variables
        """
        config = {}
        env_mapping = get_env_config_mapping()
        
        for env_var, config_key in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                self._set_nested_value(config, config_key, value)
        
        return config
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge two configuration dictionaries.
        
        Args:
            base: Base configuration
            override: Override configuration
            
        Returns:
            Merged configuration
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _set_nested_value(self, config: Dict[str, Any], key_path: str, value: Any) -> None:
        """
        Set a nested value in configuration dict.
        
        Args:
            config: Configuration dict
            key_path: Dot-separated key path
            value: Value to set
        """
        keys = key_path.split(".")
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def __getitem__(self, key_path: str) -> Any:
        """Get configuration value using dict-like access."""
        return self.get(key_path)
    
    def __setitem__(self, key_path: str, value: Any) -> None:
        """Set configuration value using dict-like access."""
        self.set(key_path, value)
    
    def __contains__(self, key_path: str) -> bool:
        """Check if configuration key exists."""
        return self.get(key_path) is not None
    
    def __repr__(self) -> str:
        """String representation."""
        return f"ConfigManager(config_file={self.config_file}, validate={self.validate})"


# Global configuration instance
_global_config: Optional[ConfigManager] = None


def get_global_config() -> ConfigManager:
    """
    Get the global configuration instance.
    
    Returns:
        Global ConfigManager instance
    """
    global _global_config
    if _global_config is None:
        _global_config = ConfigManager()
    return _global_config


def set_global_config(config_manager: ConfigManager) -> None:
    """
    Set the global configuration instance.
    
    Args:
        config_manager: ConfigManager instance to set as global
    """
    global _global_config
    _global_config = config_manager


def load_config(config_file: Optional[Union[str, Path]] = None,
               config_dict: Optional[Dict[str, Any]] = None,
               validate: bool = True) -> ConfigManager:
    """
    Load and return a configuration manager.
    
    Args:
        config_file: Path to configuration file
        config_dict: Direct configuration dictionary
        validate: Whether to validate configuration
        
    Returns:
        ConfigManager instance
        
    Example:
        config = load_config("my_config.yaml")
        config = load_config(config_dict={"storage": {"default_format": "json"}})
    """
    return ConfigManager(
        config_file=config_file,
        config_dict=config_dict,
        validate=validate
    )
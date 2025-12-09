#!/usr/bin/env python3
"""
FastGraph Configuration Example

This script demonstrates FastGraph configuration management including:
- Loading configurations from files
- Environment variable overrides
- Configuration validation
- Custom configurations
"""

import sys
import os
import tempfile
import json
import yaml
from pathlib import Path

# Add the parent directory to the path so we can import fastgraph
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastgraph import FastGraph
from fastgraph.config import ConfigManager, load_config, get_default_config
from fastgraph.exceptions import ConfigurationError


def main():
    """Demonstrate FastGraph configuration."""
    print("⚙️  FastGraph Configuration Example")
    print("=" * 45)
    
    # 1. Default configuration
    print("\n1. Default configuration...")
    default_config = get_default_config()
    print("Default settings:")
    print(f"  Cache size: {default_config['memory']['query_cache_size']}")
    print(f"  Auto index: {default_config['indexing']['auto_index']}")
    print(f"  Thread pool: {default_config['performance']['thread_pool_size']}")
    
    # Create graph with default config
    graph1 = FastGraph("graph1")
    print(f"✓ Graph created with default config: {graph1.name}")
    
    # 2. Configuration from file
    print("\n2. Loading configuration from file...")
    
    # Create temporary config file
    custom_config = {
        "engine": {
            "name": "CustomFastGraph",
            "version": "2.0.0"
        },
        "memory": {
            "query_cache_size": 256,
            "cache_ttl": 7200,
            "memory_limit_mb": 2048
        },
        "indexing": {
            "auto_index": True,
            "default_indexes": ["id", "type", "name", "category"]
        },
        "performance": {
            "thread_pool_size": 8,
            "batch_threshold": 500,
            "optimize_for_memory": True
        },
        "cli": {
            "default_output_format": "json",
            "verbose": True,
            "color_output": False
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(custom_config, f, indent=2)
        config_file = f.name
    
    try:
        # Load config from file
        config_manager = ConfigManager(config_file)
        graph2 = FastGraph("graph2", config=config_manager)
        
        print("✓ Loaded configuration from file:")
        print(f"  Cache size: {config_manager.get('memory.query_cache_size')}")
        print(f"  Thread pool: {config_manager.get('performance.thread_pool_size')}")
        print(f"  CLI format: {config_manager.get('cli.default_output_format')}")
        
    finally:
        # Cleanup
        os.unlink(config_file)
    
    # 3. YAML configuration
    print("\n3. YAML configuration...")
    
    yaml_config = {
        "storage": {
            "data_dir": "~/.fastgraph/custom_data",
            "default_format": "json",
            "backup_enabled": True
        },
        "memory": {
            "query_cache_size": 512,
            "cache_ttl": 1800
        },
        "indexing": {
            "auto_index": False,
            "default_indexes": ["user_id", "timestamp"]
        },
        "logging": {
            "level": "DEBUG",
            "file_logging": True,
            "log_file": "~/.fastgraph/logs/debug.log"
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(yaml_config, f, default_flow_style=False)
        yaml_file = f.name
    
    try:
        config_manager = ConfigManager(yaml_file)
        graph3 = FastGraph("graph3", config=config_manager)
        
        print("✓ Loaded YAML configuration:")
        print(f"  Data dir: {config_manager.get('storage.data_dir')}")
        print(f"  Format: {config_manager.get('storage.default_format')}")
        print(f"  Log level: {config_manager.get('logging.level')}")
        
    finally:
        os.unlink(yaml_file)
    
    # 4. Environment variables
    print("\n4. Environment variable overrides...")
    
    # Set environment variables
    env_vars = {
        'FASTGRAPH_CACHE_SIZE': '1024',
        'FASTGRAPH_AUTO_INDEX': 'false',
        'FASTGRAPH_THREAD_POOL_SIZE': '16',
        'FASTGRAPH_LOG_LEVEL': 'DEBUG'
    }
    
    # Save original env vars
    original_env = {}
    for key, value in env_vars.items():
        original_env[key] = os.getenv(key)
        os.environ[key] = value
    
    try:
        config_manager = ConfigManager()
        graph4 = FastGraph("graph4", config=config_manager)
        
        print("✓ Environment overrides applied:")
        print(f"  Cache size: {config_manager.get('memory.query_cache_size')}")
        print(f"  Auto index: {config_manager.get('indexing.auto_index')}")
        print(f"  Thread pool: {config_manager.get('performance.thread_pool_size')}")
        print(f"  Log level: {config_manager.get('logging.level')}")
        
    finally:
        # Restore original env vars
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    
    # 5. Direct configuration overrides
    print("\n5. Direct configuration overrides...")
    
    override_config = {
        "memory": {
            "query_cache_size": 2048
        },
        "indexing": {
            "auto_index": True,
            "default_indexes": ["id", "type", "category", "priority"]
        },
        "cli": {
            "default_output_format": "yaml",
            "verbose": False
        }
    }
    
    graph5 = FastGraph("graph5", config=override_config)
    print("✓ Direct overrides applied:")
    
    # 6. Configuration validation
    print("\n6. Configuration validation...")
    
    # Valid configuration
    valid_config = {
        "memory": {"query_cache_size": 128},
        "storage": {"default_format": "msgpack"}
    }
    
    try:
        config_manager = ConfigManager(config_dict=valid_config, validate=True)
        print("✓ Valid configuration accepted")
    except ConfigurationError as e:
        print(f"✗ Validation error: {e}")
    
    # Invalid configuration
    invalid_config = {
        "memory": {"query_cache_size": -1},  # Invalid negative value
        "storage": {"default_format": "invalid_format"}  # Invalid format
    }
    
    try:
        config_manager = ConfigManager(config_dict=invalid_config, validate=True)
        print("✗ Invalid configuration accepted (should not happen)")
    except ConfigurationError as e:
        print(f"✓ Invalid configuration rejected: {e.message}")
    
    # 7. Configuration priority
    print("\n7. Configuration priority demonstration...")
    
    # Create config file with base settings
    base_config = {
        "memory": {"query_cache_size": 100},
        "cli": {"verbose": False}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(base_config, f)
        base_file = f.name
    
    try:
        # Set env var
        os.environ['FASTGRAPH_CACHE_SIZE'] = '200'
        
        # Load with multiple sources
        config_manager = ConfigManager(
            config_file=base_file,
            config_dict={"memory": {"query_cache_size": 300}, "cli": {"verbose": True}}
        )
        
        print("Configuration priority (highest to lowest):")
        print("  1. Direct parameters: 300")
        print("  2. Environment variable: 200")
        print("  3. Config file: 100")
        print("Result:")
        print(f"  Cache size: {config_manager.get('memory.query_cache_size')} (should be 300)")
        print(f"  Verbose: {config_manager.get('cli.verbose')} (should be True)")
        
    finally:
        os.unlink(base_file)
        if 'FASTGRAPH_CACHE_SIZE' in os.environ:
            del os.environ['FASTGRAPH_CACHE_SIZE']
    
    # 8. Saving and loading configurations
    print("\n8. Configuration persistence...")
    
    # Create and modify configuration
    config_manager = ConfigManager()
    config_manager.set("memory.query_cache_size", 512)
    config_manager.set("performance.batch_threshold", 200)
    config_manager.set("new_section.new_setting", "test_value")
    
    # Save to file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        saved_config = f.name
    
    try:
        config_manager.save_config(saved_config)
        print(f"✓ Configuration saved to {saved_config}")
        
        # Load and verify
        loaded_manager = ConfigManager(saved_config)
        print(f"  Cache size: {loaded_manager.get('memory.query_cache_size')} (should be 512)")
        print(f"  Batch threshold: {loaded_manager.get('performance.batch_threshold')} (should be 200)")
        print(f"  New setting: {loaded_manager.get('new_section.new_setting')} (should be test_value)")
        
    finally:
        os.unlink(saved_config)
    
    # 9. Configuration utilities
    print("\n9. Configuration utilities...")
    
    config_manager = ConfigManager()
    
    # Check for specific settings
    print(f"Has 'memory.query_cache_size': {'memory.query_cache_size' in config_manager}")
    print(f"Cache size value: {config_manager.get('memory.query_cache_size', 'default')}")
    
    # Get all settings
    all_settings = config_manager.get_config()
    print(f"Total configuration sections: {len(all_settings)}")
    print(f"Section names: {list(all_settings.keys())}")
    
    # Update settings
    config_manager.set("test.setting", "value")
    print(f"Set test.setting: {config_manager.get('test.setting')}")
    
    print("\n✨ Configuration example completed!")
    print("\nConfiguration tips:")
    print("- Use config files for production environments")
    print("- Environment variables great for deployment flexibility")
    print("- Direct overrides best for one-time customizations")
    print("- Always validate critical configurations")
    print("- Priority: direct > env > file > defaults")


if __name__ == "__main__":
    main()
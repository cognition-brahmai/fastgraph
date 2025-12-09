# FastGraph Package Architecture Design

## Overview
This document outlines the architecture for reconceptualizing FastGraph as a modular Python package suitable for PyPI publishing, with configuration file support and CLI tools.

## Package Structure

```
fastgraph/
├── fastgraph/                    # Main package directory
│   ├── __init__.py              # Package initialization, main exports
│   ├── core/                    # Core graph database functionality
│   │   ├── __init__.py
│   │   ├── graph.py            # Main FastGraph class
│   │   ├── edge.py             # Edge dataclass and operations
│   │   ├── subgraph.py         # SubgraphView class
│   │   ├── indexing.py         # Index management
│   │   ├── traversal.py        # Graph traversal operations
│   │   └── persistence.py      # Save/load operations
│   ├── config/                  # Configuration management
│   │   ├── __init__.py
│   │   ├── manager.py          # ConfigManager class
│   │   ├── defaults.py         # Default configuration values
│   │   └── validator.py        # Configuration validation
│   ├── cli/                     # Command-line interface
│   │   ├── __init__.py
│   │   ├── main.py             # CLI entry point
│   │   ├── commands.py         # CLI command implementations
│   │   └── utils.py            # CLI utility functions
│   ├── exceptions.py            # Custom exception classes
│   ├── utils/                   # Utility functions
│   │   ├── __init__.py
│   │   ├── threading.py        # Thread safety utilities
│   │   ├── cache.py            # Caching utilities
│   │   └── memory.py           # Memory estimation utilities
│   └── types.py                 # Type definitions
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_core/
│   ├── test_config/
│   ├── test_cli/
│   └── fixtures/
├── examples/                    # Example usage
│   ├── basic_usage.py
│   ├── config_example.py
│   └── cli_demo.py
├── docs/                        # Documentation
│   ├── README.md
│   ├── API.md
│   └── CLI.md
├── pyproject.toml              # Modern Python packaging
├── setup.py                    # Legacy support
├── requirements.txt            # Dependencies
├── requirements-dev.txt        # Development dependencies
├── README.md                   # Project README
├── LICENSE                     # License file
├── CHANGELOG.md                # Version history
├── .github/                    # GitHub workflows
│   └── workflows/
│       ├── test.yml
│       └── publish.yml
├── .gitignore
├── .pre-commit-config.yaml
└── fastgraph.yaml              # Default configuration file
```

## Module Responsibilities

### Core Module (`fastgraph/core/`)
- **graph.py**: Main FastGraph class with optimized in-memory storage
- **edge.py**: Edge dataclass and edge-specific operations
- **subgraph.py**: SubgraphView implementation for memory-efficient views
- **indexing.py**: Node and edge indexing functionality
- **traversal.py**: Graph traversal algorithms and neighbor operations
- **persistence.py**: Save/load operations with multiple formats

### Config Module (`fastgraph/config/`)
- **manager.py**: ConfigManager class for loading and managing configurations
- **defaults.py**: Default configuration values (from example_config.json)
- **validator.py**: Configuration validation and schema checking

### CLI Module (`fastgraph/cli/`)
- **main.py**: CLI entry point and argument parsing
- **commands.py**: Implementations of CLI commands
- **utils.py**: Helper functions for CLI operations

### Utils Module (`fastgraph/utils/`)
- **threading.py**: Thread safety utilities and locks
- **cache.py**: LRU cache implementation and management
- **memory.py**: Memory usage estimation utilities

## Configuration System

The configuration system will support:
1. **Default configuration**: Built-in defaults from fastgraph.yaml
2. **User configuration**: ~/.fastgraph/config.yaml
3. **Environment-specific**: Environment variable overrides
4. **Runtime configuration**: Direct parameter overrides

### Configuration Loading Priority
1. Direct parameters (highest priority)
2. Environment variables
3. User config file
4. Package default config (lowest priority)

## CLI Design

### Basic Commands
- `fastgraph create [--name] [--config]` - Create new graph instance
- `fastgraph import <file> [--format] [--config]` - Import data from file
- `fastgraph export <file> [--format] [--graph]` - Export graph to file
- `fastgraph stats [--graph]` - Show graph statistics
- `fastgraph help` - Show help information

### CLI Architecture
- Uses Click framework for command-line interface
- Supports configuration file specification via `--config` flag
- Provides verbose output with `--verbose` flag
- Supports multiple output formats (JSON, table, plain text)

## Key Design Principles

### 1. Modularity
- Clean separation of concerns between modules
- Minimal dependencies between modules
- Clear interfaces and contracts

### 2. Configuration-Driven
- All configurable parameters exposed via config system
- Sensible defaults that work out-of-the-box
- Easy override mechanisms for different use cases

### 3. Backward Compatibility
- Maintain API compatibility with original FastGraph
- Provide migration path for existing users
- Support legacy configuration methods during transition

### 4. Performance
- Maintain high-performance characteristics of original implementation
- Minimal overhead from configuration system
- Efficient memory usage and CPU performance

### 5. Extensibility
- Plugin architecture for future enhancements
- Clear extension points for custom indexes, persistence, etc.
- Support for custom configuration schemas

## Dependencies

### Core Dependencies
- `msgpack`: For compressed serialization
- `click`: For CLI framework
- `pyyaml`: For configuration file parsing
- `typing-extensions`: For enhanced type hints

### Development Dependencies
- `pytest`: Testing framework
- `black`: Code formatting
- `flake8`: Linting
- `mypy`: Type checking
- `sphinx`: Documentation generation
- `coverage`: Test coverage

## Configuration Schema

Based on example_config.json, the configuration will include:

```yaml
engine:
  name: "FastGraph"
  version: "2.0.0"

storage:
  data_dir: "~/.cache/fastgraph/data"
  default_format: "msgpack"

memory:
  query_cache_size: 128
  cache_ttl: 3600

indexing:
  auto_index: true
  default_indexes: ["id", "type", "name"]

performance:
  thread_pool_size: 4
  batch_threshold: 100

cli:
  default_output_format: "table"
  verbose: false
```

## Next Steps

1. Implement the configuration management system
2. Refactor the core FastGraph class into modular components
3. Create the CLI interface with basic commands
4. Set up the package structure for PyPI publishing
5. Add comprehensive testing and documentation

This architecture provides a solid foundation for a professional Python package while maintaining the performance and functionality of the original FastGraph implementation.
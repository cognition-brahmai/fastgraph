# Changelog

All notable changes to FastGraph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.4] - 2025-12-09

### 🔧 Changed
- Smart compression defaults for different persistence formats:
  - msgpack/pickle formats: now compress by default
  - JSON format: no compression by default for human readability
- Maintains backward compatibility while providing sensible defaults

### 🐛 Fixed
- **TypeError in gzip file operations**: Fixed compression issues when saving to compressed JSON format
- Changed from using gzip.GzipFile with fileobj to directly using gzip.open()
- Updated both save and load operations for consistency
- Added comprehensive test coverage to prevent regressions

## [2.0.3] - 2025-12-09

### 🗑️ Removed
- Removed pyproject.toml configuration file
- Simplified project structure to use setup.py exclusively

### 🔧 Changed
- Updated README.md with latest project information
- Streamlined build configuration

## [2.0.2] - 2025-12-09

### 📄 Documentation
- Added project logo/branding image
- Updated README.md with improved documentation

## [2.0.1] - 2025-12-09

### 🐛 Fixed
- **Initialization Issues**: Fixed thread lock initialization order in FastGraph
- **Import Problems**: Resolved circular import issues by using forward references for Edge type
- **Validation Errors**: Fixed requirements parsing to ignore include directives in setup.py
- **Encoding Issues**: Added explicit encoding when reading README.md in validation script
- Updated validation script to remove emojis and fix installation path

## [2.0.0] - 2025-12-09

### 🎉 Major Release - Complete Reconstruction

This release represents a complete reconstruction of FastGraph as a professional Python package suitable for PyPI publishing.

### ✨ Added

#### Core Features
- **Modular Architecture**: Complete package restructuring with separated concerns
- **Configuration System**: JSON/YAML configuration support with hierarchical loading
- **CLI Tools**: Command-line interface for common operations
- **Enhanced Error Handling**: Comprehensive exception hierarchy
- **Performance Monitoring**: Built-in performance tracking and profiling
- **Memory Optimization**: Advanced memory estimation and management utilities
- **Thread Safety**: Robust concurrency management utilities

#### Configuration Management
- ConfigManager class for centralized configuration
- Support for default, user, environment, and runtime configurations
- Configuration validation with detailed error messages
- Environment variable override support
- Automatic configuration detection in standard locations

#### CLI Interface
- `fastgraph create` - Create new graph instances
- `fastgraph import` - Import data from various formats
- `fastgraph export` - Export data in multiple formats
- `fastgraph stats` - Graph statistics and analysis
- `fastgraph config` - Configuration management
- Multiple output formats (table, JSON, YAML, plain)
- Progress bars and verbose output options

#### Core Graph Engine
- Refactored FastGraph class with improved modularity
- Edge dataclass with optimization methods
- SubgraphView with memory efficiency
- IndexManager with automatic suggestions
- TraversalOperations with comprehensive algorithms
- PersistenceManager with streaming support

#### Utilities
- ThreadSafetyManager with various lock types
- CacheManager with LRU, TTL, and simple caches
- MemoryUtils with system monitoring
- PerformanceMonitor with detailed statistics

#### Performance
- O(1) edge lookups using adjacency lists
- Batch operations for bulk data handling
- Memory-efficient subgraph views
- Query result caching with TTL support
- Compressed persistence with msgpack
- Automatic index maintenance and optimization

#### Developer Experience
- Comprehensive type hints throughout
- Detailed docstrings and examples
- Professional package structure
- Development dependencies in requirements-dev.txt
- Pre-commit configuration hooks
- Modern pyproject.toml setup

### 🔧 Changed

#### Breaking Changes
- **Module Structure**: Complete reorganization into `fastgraph.core`, `fastgraph.config`, `fastgraph.cli`, `fastgraph.utils`
- **Configuration**: Now configuration-driven instead of parameter-based
- **CLI**: New command structure with `fastgraph` command
- **Imports**: Main imports now from `fastgraph` package root

#### Core API Changes
- FastGraph constructor now accepts `config` parameter
- Edge operations use new `Edge` dataclass
- Index management through dedicated `IndexManager`
- Traversal through `TraversalOperations`
- Persistence through `PersistenceManager`

#### Configuration Changes
- Default configuration moved to `example_config.json`
- Environment variable support added
- Configuration validation enforced
- Standard configuration paths supported

### 🗑️ Removed

- Legacy single-file implementation
- Hardcoded configuration parameters
- Basic error handling
- Simple performance tracking

### 🐛 Fixed

- Memory leaks in large graph operations
- Thread safety issues in concurrent access
- Configuration loading errors
- Edge lookup optimization bugs
- Index maintenance problems

### 📚 Documentation

- Complete README with examples
- API documentation in docstrings
- Configuration guide
- CLI usage documentation
- Performance optimization guide

### 🏗️ Development

- Modern Python packaging with pyproject.toml
- Development dependencies with pytest, black, flake8, mypy
- Pre-commit hooks for code quality
- CI/CD configuration templates
- Example scripts and demonstrations

## [1.0.0] - Legacy Version

### Features
- Basic in-memory graph operations
- Simple node and edge management
- Basic adjacency list implementation
- Simple persistence with pickle

### Limitations
- Single file implementation
- No configuration support
- Limited error handling
- No CLI tools
- No performance monitoring

---

## Migration Guide

### From 1.0.0 to 2.0.0

#### Basic Usage
```python
# Old (1.0.0)
from main import FastGraph
graph = FastGraph(name="my_graph", auto_index=True, cache_size=128)

# New (2.0.0)
from fastgraph import FastGraph
graph = FastGraph(name="my_graph", config="my_config.json")
```

#### Configuration
```python
# Old (1.0.0)
graph = FastGraph(name="graph", auto_index=True, cache_size=256)

# New (2.0.0)
# Either use config file:
graph = FastGraph(name="graph", config="config.yaml")

# Or config dict:
config = {"memory": {"query_cache_size": 256}}
graph = FastGraph(name="graph", config=config)
```

#### CLI
```bash
# Old (1.0.0) - No CLI available

# New (2.0.0)
fastgraph create --name "my_graph"
fastgraph import data.json
fastgraph stats --detailed
```

---

## Support

For help with migration:
- 📖 [Migration Guide](docs/migration.md)
- 🐛 [Issue Tracker](https://github.com/fastgraph/fastgraph/issues)
- 💬 [Discussions](https://github.com/fastgraph/fastgraph/discussions)

---

## Version History Summary

- **2.0.4**: Smart compression defaults and gzip fixes
- **2.0.3**: Project structure simplification (removed pyproject.toml)
- **2.0.2**: Documentation updates and branding
- **2.0.1**: Initialization, import, and validation fixes
- **2.0.0**: Complete reconstruction as professional Python package
- **1.0.0**: Original proof-of-concept implementation
# Changelog

All notable changes to FastGraph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2025-12-10

### 🎉 Major Release - Enhanced API v2.0

This release introduces the revolutionary Enhanced API that dramatically simplifies FastGraph usage while maintaining full backward compatibility.

### ✨ Enhanced API Features

#### 🔧 Smart Constructor and Configuration
- **Zero-Configuration Setup**: `FastGraph("my_graph")` auto-enables all enhanced features
- **Intelligent Defaults**: Sensible defaults for path resolution, format detection, and resource management
- **Backward Compatibility**: All existing code continues to work unchanged
- **Enhanced Configuration**: New `enhanced_api` configuration section with auto-save, path resolution, and resource management options

#### 📁 Smart Persistence and Auto-Resolution
- **Auto-Discovery**: `graph.load()` automatically finds graph files in standard locations
- **Smart Path Resolution**: `graph.save()` auto-resolves paths and formats based on hints and defaults
- **Format Auto-Detection**: Automatic format detection from file extensions and content
- **Existence Checking**: `graph.exists()` method to check if graph files exist

#### 🔄 Format Translation and Conversion
- **Built-in Format Conversion**: `graph.translate()` converts between JSON, MessagePack, Pickle, and YAML
- **Format Extraction**: `graph.get_translation()` extracts data to different formats
- **Auto-Format Detection**: Source format automatically detected when not specified
- **Streaming Conversion**: Efficient conversion for large files

#### 🏭 Factory Methods
- **FastGraph.from_file()**: Create and load graph from existing file
- **FastGraph.load_graph()**: Enhanced graph loading with auto-discovery
- **FastGraph.with_config()**: Create graph with specific configuration

#### 🛡️ Resource Management and Context Managers
- **Context Manager Support**: `with FastGraph() as graph:` for automatic cleanup
- **Auto-Save on Exit**: Configurable auto-save when context manager exits successfully
- **Explicit Cleanup**: `graph.cleanup()` method for manual resource management
- **Resource Tracking**: Automatic resource registration and cleanup

#### 💾 Backup and Restore Operations
- **Automatic Backups**: `graph.backup()` creates backups in multiple formats
- **Smart Restore**: `graph.restore_from_backup()` restores from most recent backup
- **Backup Management**: Configurable backup directories and retention

#### 🛠️ Enhanced Utilities
- **Path Resolver**: Intelligent path resolution across multiple search directories
- **Resource Manager**: Automatic resource tracking and cleanup
- **Format Detection**: Content-based format detection
- **Error Recovery**: Enhanced error handling with automatic fallbacks

### 🔧 Configuration Enhancements

#### New Configuration Sections
```yaml
enhanced_api:
  enabled: true                    # Enable enhanced features
  auto_save_on_exit: false         # Auto-save in context managers
  auto_save_on_cleanup: true       # Auto-save on explicit cleanup
  path_resolution: true            # Automatic path resolution
  format_detection: true           # Automatic format detection
  resource_management: true        # Resource tracking and cleanup

path_resolver:
  data_dir: "~/.cache/fastgraph/data"
  default_format: "msgpack"
  search_paths:
    - "./data"
    - "./graphs"
    - "~/.cache/fastgraph/data"
  format_preferences:
    - "msgpack"
    - "pickle"
    - "json"
```

### 📚 Documentation and Examples

#### Comprehensive Documentation
- **Enhanced API Overview**: Complete guide to new features and benefits
- **Migration Guide**: Step-by-step migration from legacy to enhanced API
- **API Reference**: Detailed documentation of all new methods and parameters
- **Configuration Guide**: Enhanced configuration options and examples

#### New Examples
- `examples/enhanced_basic_usage.py` - Simplified API demonstrations
- `examples/format_conversion_examples.py` - Format conversion workflows
- `examples/context_manager_examples.py` - Resource management patterns
- `examples/factory_method_examples.py` - Factory method patterns
- `examples/migration_examples.py` - Migration from legacy API
- `examples/performance_examples.py` - Performance optimization

### 🔄 Backward Compatibility

#### Full Compatibility Guarantee
- **No Breaking Changes**: All existing FastGraph v2.0.x code continues to work
- **Legacy Methods Support**: Traditional save/load methods remain functional
- **Configuration Compatibility**: Existing configurations continue to work
- **Gradual Migration**: Enhanced features can be adopted incrementally

#### Migration Support
- **Feature Detection**: Check for enhanced features with `hasattr()`
- **Hybrid Approaches**: Mix legacy and enhanced code in same application
- **Fallback Mechanisms**: Automatic fallback to legacy methods when enhanced features unavailable
- **Migration Timeline**: Phased adoption recommendations

### 🚀 Performance Improvements

#### Enhanced Performance
- **Auto-Resolution Overhead**: ~1-2ms for intelligent path/format detection
- **Context Manager Efficiency**: Zero-cost abstraction for resource management
- **Factory Method Optimization**: Optimized for common creation patterns
- **Streaming Conversion**: Efficient format conversion for large files

#### Memory and Resource Management
- **Automatic Cleanup**: Prevents resource leaks through context managers
- **Resource Tracking**: Monitors graph instances for proper cleanup
- **Memory Efficiency**: Enhanced garbage collection and memory pressure handling

### 🐛 Bug Fixes

- **Resource Leaks**: Fixed potential resource leaks in graph instances
- **Path Resolution**: Improved path resolution across different platforms
- **Format Detection**: Enhanced format detection reliability
- **Error Handling**: Better error messages and recovery mechanisms

### 🏗️ Development Improvements

#### Enhanced Testing
- **Enhanced API Tests**: Comprehensive test coverage for new features
- **Migration Tests**: Automated testing of legacy to enhanced migration
- **Performance Tests**: Benchmarks for enhanced features
- **Integration Tests**: End-to-end workflow testing

#### Code Quality
- **Type Safety**: Enhanced type hints for all new methods
- **Documentation**: Complete docstrings with examples
- **Error Handling**: Comprehensive exception handling
- **Code Coverage**: Increased test coverage for enhanced features

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

### 🔄 Migration Notes

#### From 2.0.x to 2.1.0 (Enhanced API)

**Breaking Changes**: None - Full backward compatibility maintained

**Recommended Migrations**:
1. **Enable Enhanced API**: Add `enhanced_api: enabled: true` to configuration or use `FastGraph("name")`
2. **Replace Manual Paths**: Use `graph.save()` and `graph.load()` instead of manual path management
3. **Add Context Managers**: Use `with FastGraph() as graph:` for automatic resource management
4. **Utilize Factory Methods**: Replace manual load patterns with `FastGraph.from_file()` or `FastGraph.load_graph()`
5. **Format Conversion**: Use `graph.translate()` instead of manual load/save for format changes

**Example Migration**:
```python
# Before (2.0.x)
graph = FastGraph(name="my_graph", config=config)
graph.load("data.msgpack", format="msgpack")
# ... operations ...
graph.save("output.msgpack", format="msgpack")

# After (2.1.0) - Enhanced
with FastGraph("my_graph") as graph:
    graph.load()  # Auto-discover
    # ... operations ...
    # Auto-save on exit
```

#### Enhanced API Benefits

- **Zero Configuration**: `FastGraph("my_graph")` enables all enhanced features
- **Auto-Discovery**: `graph.load()` automatically finds your graph files
- **Smart Paths**: `graph.save()` auto-resolves locations and formats
- **Resource Safety**: Context managers prevent resource leaks
- **Format Flexibility**: Easy conversion between serialization formats

---

## Support

For help with migration:
- 📖 [Migration Guide](FastGraph_Comprehensive_Documentation.md#migration-guide)
- 📚 [Enhanced API Documentation](FastGraph_Comprehensive_Documentation.md#enhanced-api-overview)
- 🐛 [Issue Tracker](https://github.com/fastgraph/fastgraph/issues)
- 💬 [Discussions](https://github.com/fastgraph/fastgraph/discussions)

---

## Version History Summary

- **2.1.0**: 🎉 Enhanced API v2.0 - Smart persistence, resource management, factory methods
- **2.0.4**: Smart compression defaults and gzip fixes
- **2.0.3**: Project structure simplification (removed pyproject.toml)
- **2.0.2**: Documentation updates and branding
- **2.0.1**: Initialization, import, and validation fixes
- **2.0.0**: Complete reconstruction as professional Python package
- **1.0.0**: Original proof-of-concept implementation
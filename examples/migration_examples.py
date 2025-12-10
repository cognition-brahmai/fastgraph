#!/usr/bin/env python3
"""
FastGraph Migration Examples

This file demonstrates how to migrate from legacy FastGraph API v1.x
to the enhanced FastGraph API v2.0, showing both old and new patterns
side by side for easy comparison.

Migration areas covered:
- Constructor usage patterns
- File operations and persistence
- Configuration management
- Resource management
- Error handling
- Performance optimizations
"""

from fastgraph import FastGraph
from fastgraph.config import ConfigManager, set_enhanced_api_config
import json
import tempfile
import os


def example_1_constructor_migration():
    """
    Example 1: Constructor pattern migration.
    
    Shows the evolution from legacy constructor to enhanced constructor
    with zero-configuration setup.
    """
    print("=== Example 1: Constructor Migration ===")
    
    # Legacy pattern (v1.x)
    print("LEGACY PATTERN (v1.x):")
    print("""
    # Required explicit configuration
    config = {
        "persistence": {
            "default_directory": "./data",
            "default_format": "json"
        }
    }
    graph = FastGraph("my_graph", config=config)
    graph.initialize()  # Manual initialization often required
    graph.load()  # Manual loading required
    """)
    
    # Enhanced pattern (v2.0)
    print("ENHANCED PATTERN (v2.0):")
    print("""
    # Zero-configuration setup
    graph = FastGraph("my_graph")  # Auto-configured
    # Auto-discovery and loading happen automatically
    """)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Legacy approach simulation
    print("Legacy approach:")
    legacy_config = {
        "persistence": {
            "default_directory": "./data",
            "default_format": "json"
        }
    }
    legacy_graph = FastGraph("legacy_graph", config=legacy_config)
    legacy_graph.add_node("legacy_node", {"migration": "old_way"})
    legacy_graph.save()  # Manual save
    print(f"Legacy graph created: {len(legacy_graph.graph['nodes'])} nodes")
    
    # Enhanced approach
    print("\nEnhanced approach:")
    enhanced_graph = FastGraph("enhanced_graph")  # Auto-configured
    enhanced_graph.add_node("enhanced_node", {"migration": "new_way"})
    # Auto-save on context exit or explicit save
    enhanced_graph.save()
    print(f"Enhanced graph created: {len(enhanced_graph.graph['nodes'])} nodes")
    
    print("✅ Migration: Remove explicit config, rely on auto-configuration")
    print()


def example_2_persistence_migration():
    """
    Example 2: Persistence operations migration.
    
    Shows how file operations have been simplified and enhanced.
    """
    print("=== Example 2: Persistence Migration ===")
    
    # Legacy pattern
    print("LEGACY PATTERN:")
    print("""
    # Manual file path management
    import os
    graph_dir = "./data"
    os.makedirs(graph_dir, exist_ok=True)
    graph_path = os.path.join(graph_dir, "my_graph.json")
    
    # Manual save/load operations
    with open(graph_path, 'w') as f:
        json.dump(graph.graph, f)
    
    with open(graph_path, 'r') as f:
        data = json.load(f)
        graph.graph = data
    """)
    
    # Enhanced pattern
    print("ENHANCED PATTERN:")
    print("""
    # Smart persistence with auto-discovery
    graph = FastGraph("my_graph")
    graph.save()  # Smart path resolution
    graph.load()  # Auto-discovery of files
    
    # Or even simpler with context managers
    with FastGraph("my_graph") as graph:
        # Auto-save on exit
        pass
    """)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Create a graph using legacy pattern simulation
    print("Legacy persistence simulation:")
    legacy_graph = FastGraph("legacy_persistence")
    legacy_graph.add_node("manual_save", {"pattern": "legacy"})
    
    # Manual path management (simulated)
    legacy_graph.save()  # Still works but enhanced underneath
    print(f"Legacy-style save completed: {legacy_graph.exists()}")
    
    # Enhanced persistence
    print("\nEnhanced persistence:")
    enhanced_graph = FastGraph("enhanced_persistence")
    enhanced_graph.add_node("smart_save", {"pattern": "enhanced"})
    enhanced_graph.save()  # Smart persistence
    print(f"Enhanced save completed: {enhanced_graph.exists()}")
    
    # Show auto-discovery
    print("\nAuto-discovery demonstration:")
    discovered_graph = FastGraph("enhanced_persistence")
    if discovered_graph.exists():
        discovered_graph.load()
        print(f"Auto-discovered and loaded: {len(discovered_graph.graph['nodes'])} nodes")
    
    print("✅ Migration: Replace manual file operations with smart persistence")
    print()


def example_3_configuration_migration():
    """
    Example 3: Configuration management migration.
    
    Shows the evolution from manual configuration to enhanced
    configuration system with better defaults.
    """
    print("=== Example 3: Configuration Migration ===")
    
    # Legacy pattern
    print("LEGACY PATTERN:")
    print("""
    # Manual configuration required
    config = {
        "persistence": {
            "default_directory": "./graphs",
            "default_format": "json",
            "compression": False,
            "backup_enabled": False
        },
        "performance": {
            "caching": {
                "enabled": False
            }
        }
    }
    graph = FastGraph("my_graph", config=config)
    """)
    
    # Enhanced pattern
    print("ENHANCED PATTERN:")
    print("""
    # Enhanced API auto-enabled with smart defaults
    graph = FastGraph("my_graph")  # Auto-configured
    
    # Or customize specific settings
    config = {
        "enhanced_api": {
            "enabled": True,
            "auto_discovery": True
        }
    }
    graph = FastGraph.with_config(config, "my_graph")
    """)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Legacy configuration
    print("Legacy configuration:")
    legacy_config = {
        "persistence": {
            "default_directory": "./legacy_data",
            "default_format": "json",
            "compression": False
        }
    }
    legacy_graph = FastGraph("legacy_config", config=legacy_config)
    legacy_graph.add_node("legacy_configured", {"style": "manual"})
    legacy_graph.save()
    print(f"Legacy config graph: {legacy_graph.config['persistence']['default_directory']}")
    
    # Enhanced configuration
    print("\nEnhanced configuration:")
    enhanced_graph = FastGraph("enhanced_config")  # Auto-configured
    enhanced_graph.add_node("enhanced_configured", {"style": "auto"})
    enhanced_graph.save()
    print(f"Enhanced config enabled: {enhanced_graph.config['enhanced_api']['enabled']}")
    
    print("✅ Migration: Use enhanced API defaults, customize only when needed")
    print()


def example_4_resource_management_migration():
    """
    Example 4: Resource management migration.
    
    Shows the transition from manual resource management
    to automatic cleanup with context managers.
    """
    print("=== Example 4: Resource Management Migration ===")
    
    # Legacy pattern
    print("LEGACY PATTERN:")
    print("""
    # Manual resource management
    graph = FastGraph("my_graph")
    try:
        # Operations here
        graph.add_node("data", value=1)
        graph.save()
    finally:
        # Manual cleanup required
        if hasattr(graph, 'cleanup'):
            graph.cleanup()
        # Manual memory management
        del graph
    """)
    
    # Enhanced pattern
    print("ENHANCED PATTERN:")
    print("""
    # Automatic resource management
    with FastGraph("my_graph") as graph:
        # Operations here
        graph.add_node("data", value=1)
        # Auto-save and cleanup on exit
    
    # Or factory methods with built-in management
    graph = FastGraph.load_graph("my_graph")  # Managed loading
    """)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Legacy resource management simulation
    print("Legacy resource management:")
    legacy_graph = FastGraph("legacy_resources")
    try:
        legacy_graph.add_node("manual_resource", {"cleanup": "manual"})
        legacy_graph.save()
        print("Legacy operations completed")
    finally:
        legacy_graph.cleanup()
        print("Legacy cleanup completed")
    
    # Enhanced resource management
    print("\nEnhanced resource management:")
    with FastGraph("enhanced_resources") as enhanced_graph:
        enhanced_graph.add_node("auto_resource", {"cleanup": "automatic"})
        print("Enhanced operations completed")
        # Auto-cleanup happens here
    
    print("✅ Migration: Use context managers for automatic resource management")
    print()


def example_5_error_handling_migration():
    """
    Example 5: Error handling migration.
    
    Shows how error handling has been improved and simplified
    in the enhanced API.
    """
    print("=== Example 5: Error Handling Migration ===")
    
    # Legacy pattern
    print("LEGACY PATTERN:")
    print("""
    # Manual error checking
    graph = FastGraph("my_graph")
    try:
        graph.load()
    except FileNotFoundError:
        # Create new graph
        graph.graph = {"nodes": {}, "edges": {}}
    except json.JSONDecodeError:
        # Handle corrupted file
        print("File corrupted, creating new graph")
        graph.graph = {"nodes": {}, "edges": {}}
    
    # Manual validation
    if not isinstance(graph.graph, dict):
        graph.graph = {"nodes": {}, "edges": {}}
    """)
    
    # Enhanced pattern
    print("ENHANCED PATTERN:")
    print("""
    # Built-in error handling and recovery
    graph = FastGraph("my_graph")  # Auto-handles missing files
    
    # Or with explicit error handling
    try:
        graph = FastGraph.load_graph("my_graph")
    except Exception as e:
        print(f"Load failed: {e}")
        graph = FastGraph("my_graph")  # Create new
    """)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Enhanced error handling
    print("Enhanced error handling:")
    try:
        # Try to load non-existent graph
        error_graph = FastGraph("non_existent")
        if error_graph.exists():
            error_graph.load()
        else:
            print("Graph doesn't exist, creating new one")
            error_graph.add_node("new", {"created": True})
    except Exception as e:
        print(f"Error handled gracefully: {e}")
    
    # Factory method error handling
    print("\nFactory method error handling:")
    try:
        safe_graph = FastGraph.load_graph("non_existent")
    except Exception as e:
        print(f"Factory method handled error: {type(e).__name__}")
        # Fallback to creation
        safe_graph = FastGraph("safe_fallback")
        safe_graph.add_node("fallback", {"safe": True})
    
    print("✅ Migration: Rely on built-in error handling and recovery")
    print()


def example_6_performance_optimization_migration():
    """
    Example 6: Performance optimization migration.
    
    Shows how to migrate to enhanced performance features
    and optimizations.
    """
    print("=== Example 6: Performance Optimization Migration ===")
    
    # Legacy pattern
    print("LEGACY PATTERN:")
    print("""
    # Manual performance tuning
    config = {
        "performance": {
            "caching": {
                "enabled": True,
                "max_size": 1000
            }
        }
    }
    graph = FastGraph("my_graph", config=config)
    
    # Manual optimization
    graph.optimize()  # If available
    """)
    
    # Enhanced pattern
    print("ENHANCED PATTERN:")
    print("""
    # Automatic performance optimization
    graph = FastGraph("my_graph")  # Auto-optimized
    
    # Or explicit performance configuration
    config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        },
        "performance": {
            "caching": {"enabled": True},
            "memory": {"optimization": "auto"}
        }
    }
    graph = FastGraph.with_config(config, "my_graph")
    """)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Legacy performance (simulated)
    print("Legacy performance setup:")
    legacy_config = {
        "performance": {
            "caching": {"enabled": False}
        }
    }
    legacy_perf_graph = FastGraph("legacy_performance", config=legacy_config)
    legacy_perf_graph.add_node("legacy_perf", {"optimized": False})
    print(f"Legacy performance: {legacy_perf_graph.config['performance']['caching']['enabled']}")
    
    # Enhanced performance
    print("\nEnhanced performance setup:")
    enhanced_perf_graph = FastGraph("enhanced_performance")
    enhanced_perf_graph.add_node("enhanced_perf", {"optimized": True})
    print(f"Enhanced performance: {enhanced_perf_graph.config['performance']['caching']['enabled']}")
    
    print("✅ Migration: Use enhanced API for automatic performance optimization")
    print()


def example_7_step_by_step_migration():
    """
    Example 7: Step-by-step migration guide.
    
    Provides a practical migration path for existing code.
    """
    print("=== Example 7: Step-by-Step Migration ===")
    
    print("MIGRATION STEPS:")
    print()
    
    # Step 1
    print("Step 1: Update imports (no changes needed)")
    print("  from fastgraph import FastGraph  # Same import")
    print()
    
    # Step 2
    print("Step 2: Replace constructor calls")
    print("  OLD: FastGraph(name, config=config)")
    print("  NEW: FastGraph(name)  # Auto-configured")
    print()
    
    # Step 3
    print("Step 3: Update persistence calls")
    print("  OLD: Manual file path management")
    print("  NEW: graph.save() / graph.load()  # Smart persistence")
    print()
    
    # Step 4
    print("Step 4: Add context managers where appropriate")
    print("  OLD: try/finally with manual cleanup")
    print("  NEW: with FastGraph(name) as graph:")
    print()
    
    # Step 5
    print("Step 5: Update error handling")
    print("  OLD: Manual file existence checks")
    print("  NEW: graph.exists() and built-in error handling")
    print()
    
    # Demonstration
    print("MIGRATION DEMONSTRATION:")
    
    # Before migration
    print("\nBefore migration (legacy code):")
    legacy_code = '''
    # Legacy code pattern
    config = {"persistence": {"default_directory": "./data"}}
    graph = FastGraph("my_graph", config=config)
    try:
        graph.load()
    except FileNotFoundError:
        graph.graph = {"nodes": {}, "edges": {}}
    
    graph.add_node("data", value=1)
    graph.save()
    graph.cleanup()
    '''
    print(legacy_code)
    
    # After migration
    print("After migration (enhanced code):")
    enhanced_code = '''
    # Enhanced code pattern
    graph = FastGraph("my_graph")  # Auto-configured
    graph.add_node("data", value=1)
    graph.save()  # Smart persistence
    
    # Or with context manager
    with FastGraph("my_graph") as graph:
        graph.add_node("data", value=1)
        # Auto-save and cleanup
    '''
    print(enhanced_code)
    
    print("✅ Migration: Follow step-by-step approach for smooth transition")
    print()


def example_8_compatibility_and_testing():
    """
    Example 8: Compatibility and testing migration.
    
    Shows how to ensure compatibility and test migration.
    """
    print("=== Example 8: Compatibility and Testing ===")
    
    print("COMPATIBILITY STRATEGY:")
    print()
    
    # Compatibility layer
    print("1. Maintain compatibility during transition:")
    compatibility_code = '''
    # Compatibility wrapper for gradual migration
    def create_graph(name, config=None):
        """Compatibility wrapper for migration."""
        if config is None:
            # Use enhanced API
            return FastGraph(name)
        else:
            # Use legacy API for now
            return FastGraph(name, config=config)
    
    # Gradual migration possible
    old_style = create_graph("old", legacy_config)
    new_style = create_graph("new")  # Enhanced
    '''
    print(compatibility_code)
    
    # Testing strategy
    print("\n2. Testing migration:")
    testing_code = '''
    # Test both old and new patterns
    def test_migration():
        # Test legacy pattern still works
        legacy_graph = FastGraph("test_legacy", config=legacy_config)
        legacy_graph.add_node("test", {"legacy": True})
        legacy_graph.save()
        
        # Test enhanced pattern
        enhanced_graph = FastGraph("test_enhanced")
        enhanced_graph.add_node("test", {"enhanced": True})
        enhanced_graph.save()
        
        # Verify both work
        assert legacy_graph.exists()
        assert enhanced_graph.exists()
        
        # Test data equivalence
        legacy_data = legacy_graph.graph
        enhanced_data = enhanced_graph.graph
        
        # Structures should be compatible
        assert set(legacy_data.keys()) == set(enhanced_data.keys())
    '''
    print(testing_code)
    
    # Demonstration
    print("\nDemonstration:")
    
    # Test compatibility
    print("Testing compatibility:")
    
    # Legacy style should still work
    legacy_test_config = {"persistence": {"default_format": "json"}}
    legacy_test = FastGraph("compatibility_legacy", config=legacy_test_config)
    legacy_test.add_node("compat_test", {"style": "legacy"})
    legacy_test.save()
    print(f"Legacy style compatibility: ✅")
    
    # Enhanced style
    enhanced_test = FastGraph("compatibility_enhanced")
    enhanced_test.add_node("compat_test", {"style": "enhanced"})
    enhanced_test.save()
    print(f"Enhanced style: ✅")
    
    # Verify both exist
    print(f"Both graphs created successfully: {legacy_test.exists() and enhanced_test.exists()}")
    
    print("✅ Migration: Test compatibility and gradual transition")
    print()


def main():
    """
    Run all migration examples.
    """
    print("FastGraph Migration Examples")
    print("=" * 50)
    print("Migrating from FastGraph v1.x to v2.0 Enhanced API")
    print()
    
    try:
        # Run all examples
        example_1_constructor_migration()
        example_2_persistence_migration()
        example_3_configuration_migration()
        example_4_resource_management_migration()
        example_5_error_handling_migration()
        example_6_performance_optimization_migration()
        example_7_step_by_step_migration()
        example_8_compatibility_and_testing()
        
        print("All migration examples completed!")
        print()
        print("MIGRATION SUMMARY:")
        print("✅ Enhanced API provides backward compatibility")
        print("✅ Zero-configuration setup available")
        print("✅ Smart persistence simplifies file operations")
        print("✅ Context managers enable automatic resource management")
        print("✅ Built-in error handling and recovery")
        print("✅ Performance optimizations enabled by default")
        print("✅ Gradual migration path available")
        
    except Exception as e:
        print(f"Error running migration examples: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up any remaining resources
        print("\nFinal cleanup:")
        cleanup_resources()


def cleanup_resources():
    """
    Clean up any remaining resources from migration examples.
    """
    # Clean up temporary files created during examples
    temp_files = [
        "legacy_graph.json",
        "enhanced_graph.json",
        "legacy_persistence.json",
        "enhanced_persistence.json",
        "legacy_config.json",
        "enhanced_config.json",
        "legacy_resources.json",
        "enhanced_resources.json",
        "legacy_performance.json",
        "enhanced_performance.json",
        "compatibility_legacy.json",
        "compatibility_enhanced.json"
    ]
    
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                print(f"Cleaned up {temp_file}")
            except Exception as e:
                print(f"Failed to clean up {temp_file}: {e}")


if __name__ == "__main__":
    main()
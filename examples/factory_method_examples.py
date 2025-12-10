#!/usr/bin/env python3
"""
FastGraph Factory Method Examples

This file demonstrates the factory methods introduced in FastGraph v2.0 Enhanced API
for creating and configuring FastGraph instances with different patterns.

Factory methods demonstrated:
- from_file() - Create from existing graph files
- load_graph() - Load with automatic configuration
- with_config() - Create with custom configuration
- Combination patterns for complex workflows
"""

from fastgraph import FastGraph
from fastgraph.config import ConfigManager, set_enhanced_api_config
import json
import tempfile
import os


def example_1_from_file_basic():
    """
    Example 1: Basic from_file() usage.
    
    Shows how to create FastGraph instances from existing files
    with automatic format detection and configuration.
    """
    print("=== Example 1: Basic from_file() Usage ===")
    
    # First, create a sample graph file
    sample_data = {
        "nodes": {
            "source": {"type": "data_source", "format": "json"},
            "processor": {"type": "processor", "format": "json"},
            "output": {"type": "output", "format": "json"}
        },
        "edges": {
            ("source", "processor"): {"type": "data_flow"},
            ("processor", "output"): {"type": "result"}
        }
    }
    
    # Save to different formats for demonstration
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_data, f, indent=2)
        json_file = f.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_data, f)  # Compact format
        compact_file = f.name
    
    try:
        # Load from file with automatic detection
        print("Loading from JSON file:")
        graph = FastGraph.from_file(json_file, "file_loaded_graph")
        print(f"Loaded graph: {len(graph.graph['nodes'])} nodes, {len(graph.graph['edges'])} edges")
        
        # Verify the data
        assert "source" in graph.graph['nodes']
        assert "processor" in graph.graph['nodes']
        assert "output" in graph.graph['nodes']
        print("✅ All nodes loaded correctly")
        
        # Load from compact format
        print("\nLoading from compact JSON file:")
        compact_graph = FastGraph.from_file(compact_file, "compact_loaded_graph")
        print(f"Loaded compact graph: {len(compact_graph.graph['nodes'])} nodes")
        
        print()
        
    finally:
        # Cleanup temporary files
        os.unlink(json_file)
        os.unlink(compact_file)


def example_2_from_file_with_options():
    """
    Example 2: from_file() with advanced options.
    
    Demonstrates using from_file() with custom configuration
    options and format specifications.
    """
    print("=== Example 2: from_file() with Advanced Options ===")
    
    # Create sample data with different structures
    complex_data = {
        "graph_data": {
            "nodes": {
                "complex_node_1": {
                    "properties": {"type": "complex", "weight": 0.8},
                    "metadata": {"created": "2023-01-01", "version": "1.0"}
                },
                "complex_node_2": {
                    "properties": {"type": "complex", "weight": 0.6},
                    "metadata": {"created": "2023-01-02", "version": "1.1"}
                }
            },
            "edges": {
                ("complex_node_1", "complex_node_2"): {
                    "relationship": "connected",
                    "strength": 0.9
                }
            }
        }
    }
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(complex_data, f, indent=2)
        temp_file = f.name
    
    try:
        # Load with custom configuration
        config = {
            "enhanced_api": {
                "enabled": True,
                "auto_discovery": True
            },
            "persistence": {
                "default_format": "json",
                "compression": True
            }
        }
        
        print("Loading with custom configuration:")
        graph = FastGraph.from_file(temp_file, "complex_graph", config=config)
        print(f"Loaded complex graph: {len(graph.graph['nodes'])} nodes")
        
        # Add some additional data
        graph.add_node("additional", {"added": "after_loading"})
        print("Added additional node")
        
        # Save with enhanced settings
        graph.save()
        print("Saved with enhanced configuration")
        
        print()
        
    finally:
        os.unlink(temp_file)


def example_3_load_graph_convenience():
    """
    Example 3: load_graph() convenience method.
    
    Shows the simplified loading pattern with automatic
    configuration and error handling.
    """
    print("=== Example 3: load_graph() Convenience Method ===")
    
    # Create a sample graph first
    with FastGraph("sample_for_loading") as sample_graph:
        sample_graph.add_node("load_test_1", data="test_data_1")
        sample_graph.add_node("load_test_2", data="test_data_2")
        sample_graph.add_edge("load_test_1", "load_test_2", "test_edge")
        sample_graph.save()
    
    # Load using the convenience method
    print("Loading with load_graph() convenience method:")
    try:
        loaded_graph = FastGraph.load_graph("sample_for_loading")
        print(f"Successfully loaded graph: {len(loaded_graph.graph['nodes'])} nodes")
        
        # Verify data integrity
        assert loaded_graph.graph['nodes']['load_test_1']['data'] == "test_data_1"
        assert loaded_graph.graph['edges'][('load_test_1', 'load_test_2')]['test_edge'] is not None
        print("✅ Data integrity verified")
        
    except Exception as e:
        print(f"❌ Failed to load: {e}")
    
    print()
    
    # Try loading non-existent graph
    print("Loading non-existent graph (should fail gracefully):")
    try:
        non_existent = FastGraph.load_graph("does_not_exist")
        print("Unexpectedly succeeded")
    except Exception as e:
        print(f"✅ Expected failure: {type(e).__name__}")
    
    print()


def example_4_with_config_customization():
    """
    Example 4: with_config() for custom configurations.
    
    Demonstrates creating FastGraph instances with
    specific configuration overrides.
    """
    print("=== Example 4: with_config() Custom Configuration ===")
    
    # Define custom configurations
    performance_config = {
        "enhanced_api": {
            "enabled": True,
            "auto_discovery": True,
            "resource_management": True
        },
        "persistence": {
            "auto_save_on_exit": True,
            "compression": True,
            "backup_enabled": True
        },
        "performance": {
            "caching": {
                "enabled": True,
                "max_memory_mb": 512
            }
        }
    }
    
    minimal_config = {
        "enhanced_api": {
            "enabled": True,
            "auto_discovery": False
        },
        "persistence": {
            "auto_save_on_exit": False
        }
    }
    
    # Create with performance configuration
    print("Creating graph with performance configuration:")
    perf_graph = FastGraph.with_config(performance_config, "performance_graph")
    perf_graph.add_node("perf_node", {"optimized": True})
    print(f"Performance graph created: {perf_graph}")
    
    # Create with minimal configuration
    print("\nCreating graph with minimal configuration:")
    minimal_graph = FastGraph.with_config(minimal_config, "minimal_graph")
    minimal_graph.add_node("minimal_node", {"simple": True})
    print(f"Minimal graph created: {minimal_graph}")
    
    # Show configuration differences
    print(f"\nPerformance graph auto-save: {perf_graph.config['persistence']['auto_save_on_exit']}")
    print(f"Minimal graph auto-save: {minimal_graph.config['persistence']['auto_save_on_exit']}")
    
    print()


def example_5_factory_method_chaining():
    """
    Example 5: Chaining factory methods.
    
    Shows how to combine factory methods for
    complex initialization patterns.
    """
    print("=== Example 5: Factory Method Chaining ===")
    
    # Create a base configuration
    base_config = {
        "enhanced_api": {"enabled": True},
        "persistence": {"compression": True}
    }
    
    # Create base graph with configuration
    base_graph = FastGraph.with_config(base_config, "base_chain")
    base_graph.add_node("base", {"level": 1})
    base_graph.save()
    
    print("Created base graph with configuration")
    
    # Load and extend using factory methods
    print("Loading and extending using factory methods:")
    extended_graph = FastGraph.load_graph("base_chain")
    extended_graph.add_node("extended", {"level": 2})
    extended_graph.add_edge("base", "extended", "hierarchy")
    extended_graph.save("extended_chain")
    
    print(f"Extended graph: {len(extended_graph.graph['nodes'])} nodes")
    
    # Create another variation
    print("Creating variation from extended graph:")
    variation_graph = FastGraph.from_file("extended_chain.json", "variation_graph")
    variation_graph.add_node("variation", {"level": 3})
    variation_graph.add_edge("extended", "variation", "evolution")
    
    print(f"Variation graph: {len(variation_graph.graph['nodes'])} nodes")
    print()


def example_6_configuration_inheritance():
    """
    Example 6: Configuration inheritance patterns.
    
    Demonstrates how configurations can be inherited
    and modified using factory methods.
    """
    print("=== Example 6: Configuration Inheritance ===")
    
    # Define parent configuration
    parent_config = {
        "enhanced_api": {
            "enabled": True,
            "auto_discovery": True,
            "resource_management": True
        },
        "persistence": {
            "default_format": "json",
            "compression": True,
            "backup_enabled": True
        },
        "performance": {
            "caching": {
                "enabled": True,
                "max_memory_mb": 256
            }
        }
    }
    
    # Child configuration that inherits and overrides
    child_config = parent_config.copy()
    child_config["persistence"]["compression"] = False  # Override
    child_config["performance"]["caching"]["max_memory_mb"] = 512  # Override
    child_config["logging"] = {"level": "DEBUG"}  # Add new
    
    # Create graphs with different configurations
    print("Parent configuration graph:")
    parent_graph = FastGraph.with_config(parent_config, "parent_config_graph")
    parent_graph.add_node("parent", {"config": "parent"})
    print(f"Parent compression: {parent_graph.config['persistence']['compression']}")
    print(f"Parent memory: {parent_graph.config['performance']['caching']['max_memory_mb']}")
    
    print("\nChild configuration graph:")
    child_graph = FastGraph.with_config(child_config, "child_config_graph")
    child_graph.add_node("child", {"config": "child"})
    print(f"Child compression: {child_graph.config['persistence']['compression']}")
    print(f"Child memory: {child_graph.config['performance']['caching']['max_memory_mb']}")
    print(f"Child logging: {child_graph.config.get('logging', 'not_set')}")
    
    print()


def example_7_error_handling_patterns():
    """
    Example 7: Error handling with factory methods.
    
    Shows robust error handling patterns when using
    factory methods for graph creation and loading.
    """
    print("=== Example 7: Error Handling Patterns ===")
    
    # Safe loading pattern
    def safe_load_graph(graph_name, fallback_config=None):
        """Safely load a graph with fallback handling."""
        try:
            return FastGraph.load_graph(graph_name)
        except Exception as e:
            print(f"Failed to load '{graph_name}': {e}")
            if fallback_config:
                print("Creating new graph with fallback configuration")
                return FastGraph.with_config(fallback_config, graph_name)
            else:
                print("Creating new graph with default configuration")
                return FastGraph(graph_name)
    
    # Test safe loading
    fallback_config = {
        "enhanced_api": {"enabled": True},
        "persistence": {"auto_save_on_exit": False}
    }
    
    print("Testing safe loading with non-existent graph:")
    safe_graph = safe_load_graph("non_existent", fallback_config)
    safe_graph.add_node("safe_loaded", {"fallback": True})
    print(f"Safe graph created: {len(safe_graph.graph['nodes'])} nodes")
    
    # Safe file loading pattern
    def safe_load_from_file(file_path, graph_name, config=None):
        """Safely load from file with error handling."""
        try:
            return FastGraph.from_file(file_path, graph_name, config=config)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return None
        except json.JSONDecodeError as e:
            print(f"Invalid JSON in file: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error loading file: {e}")
            return None
    
    # Test with invalid file
    print("\nTesting safe file loading with invalid path:")
    invalid_graph = safe_load_from_file("invalid.json", "test")
    if invalid_graph is None:
        print("✅ Correctly handled invalid file")
    
    print()


def example_8_workflow_patterns():
    """
    Example 8: Common workflow patterns with factory methods.
    
    Demonstrates real-world workflow patterns using
    factory methods for different scenarios.
    """
    print("=== Example 8: Workflow Patterns ===")
    
    # Pattern 1: Data processing pipeline
    print("Pattern 1: Data Processing Pipeline")
    
    # Stage 1: Load raw data
    raw_config = {
        "enhanced_api": {"enabled": True},
        "persistence": {"compression": False}  # Faster access
    }
    
    # Create raw data graph
    raw_graph = FastGraph.with_config(raw_config, "pipeline_raw")
    raw_graph.add_node("raw_1", {"stage": "raw", "processed": False})
    raw_graph.add_node("raw_2", {"stage": "raw", "processed": False})
    raw_graph.save()
    
    # Stage 2: Process data
    processed_graph = FastGraph.load_graph("pipeline_raw")
    for node_id, node_data in processed_graph.graph['nodes'].items():
        node_data['processed'] = True
        node_data['stage'] = 'processed'
    processed_graph.save("pipeline_processed")
    
    print(f"Processed {len(processed_graph.graph['nodes'])} nodes")
    
    # Pattern 2: Configuration testing
    print("\nPattern 2: Configuration Testing")
    
    test_configs = [
        {"name": "minimal", "config": {"enhanced_api": {"enabled": True}}},
        {"name": "standard", "config": {
            "enhanced_api": {"enabled": True, "auto_discovery": True},
            "persistence": {"compression": True}
        }},
        {"name": "performance", "config": {
            "enhanced_api": {"enabled": True, "resource_management": True},
            "performance": {"caching": {"enabled": True}}
        }}
    ]
    
    for test_case in test_configs:
        test_graph = FastGraph.with_config(test_case["config"], f"test_{test_case['name']}")
        test_graph.add_node("test", {"config_type": test_case["name"]})
        print(f"Tested {test_case['name']} configuration")
    
    # Pattern 3: Backup and restore workflow
    print("\nPattern 3: Backup and Restore Workflow")
    
    # Create original graph
    original_graph = FastGraph.with_config(
        {"enhanced_api": {"enabled": True, "backup_enabled": True}}, 
        "workflow_original"
    )
    original_graph.add_node("important", {"data": "critical"})
    original_graph.save()
    
    # Create backup using factory method
    backup_graph = FastGraph.load_graph("workflow_original")
    backup_paths = backup_graph.backup()
    print(f"Created backup: {backup_paths}")
    
    # Restore from backup
    restored_graph = FastGraph.load_graph("workflow_original")
    restored_graph.restore_from_backup()
    print("Restored from backup")
    
    print()


def main():
    """
    Run all factory method examples.
    """
    print("FastGraph Factory Method Examples")
    print("=" * 50)
    print()
    
    try:
        # Run all examples
        example_1_from_file_basic()
        example_2_from_file_with_options()
        example_3_load_graph_convenience()
        example_4_with_config_customization()
        example_5_factory_method_chaining()
        example_6_configuration_inheritance()
        example_7_error_handling_patterns()
        example_8_workflow_patterns()
        
        print("All factory method examples completed!")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up any remaining resources
        print("\nFinal cleanup:")
        cleanup_resources()


def cleanup_resources():
    """
    Clean up any remaining resources from examples.
    """
    # Clean up temporary files and graphs created during examples
    temp_files = [
        "sample_for_loading.json",
        "base_chain.json",
        "extended_chain.json",
        "pipeline_raw.json",
        "pipeline_processed.json",
        "workflow_original.json"
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
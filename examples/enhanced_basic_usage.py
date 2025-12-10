#!/usr/bin/env python3
"""
Enhanced FastGraph Basic Usage Examples

This file demonstrates the simplified Enhanced API v2.0 features that make
FastGraph easier to use with intelligent defaults and auto-resolution.

Key concepts demonstrated:
- Zero-configuration graph creation
- Smart persistence with auto-discovery
- Context managers for resource management
- Simplified workflows with enhanced features
"""

from fastgraph import FastGraph
import tempfile
import os


def example_1_zero_configuration_graph():
    """
    Example 1: Create and use a graph with zero configuration.
    
    The Enhanced API automatically enables all features when you create
    a graph with just a name parameter.
    """
    print("=== Example 1: Zero-Configuration Graph ===")
    
    # Enhanced API - auto-enables all features
    with FastGraph("social_network") as graph:
        # Add nodes with attributes
        graph.add_node("alice", name="Alice Smith", age=30, type="Person")
        graph.add_node("bob", name="Bob Johnson", age=25, type="Person")
        graph.add_node("charlie", name="Charlie Davis", age=35, type="Person")
        graph.add_node("techcorp", name="TechCorp", type="Company")
        
        # Add relationships
        graph.add_edge("alice", "bob", "friends", since=2020, close=True)
        graph.add_edge("bob", "charlie", "friends", since=2019)
        graph.add_edge("alice", "techcorp", "works_at", role="Engineer")
        graph.add_edge("bob", "techcorp", "works_at", role="Manager")
        
        # Query the graph
        people = graph.find_nodes(type="Person")
        print(f"Found {len(people)} people in the network")
        
        # Find Alice's friends
        alice_friends = graph.neighbors_out("alice", rel="friends")
        print(f"Alice's friends: {[friend for friend, edge in alice_friends]}")
        
        # Auto-save on context exit
        print("Graph auto-saved on context exit")
    
    print()


def example_2_smart_persistence():
    """
    Example 2: Smart persistence with auto-discovery and path resolution.
    
    Demonstrates how the Enhanced API automatically handles file paths,
    formats, and discovery without manual specification.
    """
    print("=== Example 2: Smart Persistence ===")
    
    # Create a graph with enhanced features
    with FastGraph("knowledge_graph") as graph:
        # Build a simple knowledge graph
        concepts = [
            ("python", {"type": "language", "paradigm": "multi"}),
            ("fastgraph", {"type": "library", "language": "python"}),
            ("graph_db", {"type": "concept", "domain": "database"}),
            ("performance", {"type": "attribute", "category": "quality"})
        ]
        
        for concept_id, attrs in concepts:
            graph.add_node(concept_id, **attrs)
        
        # Add relationships
        relationships = [
            ("fastgraph", "python", "implemented_in"),
            ("fastgraph", "graph_db", "is_a"),
            ("fastgraph", "performance", "has_attribute"),
            ("python", "performance", "optimizes_for")
        ]
        
        for src, dst, rel in relationships:
            graph.add_edge(src, dst, rel)
        
        print(f"Created knowledge graph with {len(graph.graph['nodes'])} concepts")
        
        # Smart save - auto-resolves path and format
        saved_path = graph.save()
        print(f"Graph saved to: {saved_path}")
    
    # Smart loading - auto-discovers the file
    graph = FastGraph("knowledge_graph")
    if graph.exists():
        loaded_path = graph.load()
        print(f"Graph loaded from: {loaded_path}")
        print(f"Loaded graph has {len(graph.graph['nodes'])} nodes")
    
    print()


def example_3_automatic_format_detection():
    """
    Example 3: Automatic format detection and smart defaults.
    
    Shows how FastGraph automatically detects formats and uses
    intelligent defaults for different scenarios.
    """
    print("=== Example 3: Automatic Format Detection ===")
    
    # Create graph and save in different formats
    with FastGraph("format_demo") as graph:
        # Add some test data
        graph.add_node("user1", name="User One", email="user1@example.com")
        graph.add_node("user2", name="User Two", email="user2@example.com")
        graph.add_edge("user1", "user2", "knows", since=2023)
        
        # Save with different format hints
        json_path = graph.save("demo_data.json")
        msgpack_path = graph.save("demo_data.msgpack")
        
        print(f"Saved JSON to: {json_path}")
        print(f"Saved MessagePack to: {msgpack_path}")
    
    # Load with auto-detection
    graph = FastGraph("format_demo")
    
    # Auto-detect JSON format
    graph.load("demo_data.json")
    print(f"Loaded JSON graph: {len(graph.graph['nodes'])} nodes")
    
    # Auto-detect MessagePack format
    graph.load("demo_data.msgpack")
    print(f"Loaded MessagePack graph: {len(graph.graph['nodes'])} nodes")
    
    print()


def example_4_resource_management():
    """
    Example 4: Automatic resource management and cleanup.
    
    Demonstrates context managers and automatic resource cleanup
    that prevent memory leaks and resource issues.
    """
    print("=== Example 4: Resource Management ===")
    
    # Context manager ensures automatic cleanup
    print("Using context manager for automatic cleanup:")
    with FastGraph("temp_analysis") as graph:
        graph.add_node("data1", value=100, category="A")
        graph.add_node("data2", value=200, category="B")
        graph.add_node("data3", value=150, category="A")
        
        # Find nodes by category
        category_a = graph.find_nodes(category="A")
        print(f"Category A nodes: {len(category_a)}")
        
        # Calculate statistics
        total_value = sum(attrs.get('value', 0) for _, attrs in category_a)
        print(f"Total value for category A: {total_value}")
        
        # Resources automatically cleaned up on exit
    
    print("Resources automatically cleaned up")
    
    # Manual cleanup when not using context manager
    print("Manual cleanup approach:")
    graph = FastGraph("manual_cleanup")
    try:
        graph.add_node("temp", data="temporary")
        # ... do work ...
    finally:
        graph.cleanup()  # Explicit cleanup
        print("Manually cleaned up resources")
    
    print()


def example_5_existence_checking():
    """
    Example 5: Graph existence checking and conditional operations.
    
    Shows how to check if graph files exist and conditionally
    load or create graphs.
    """
    print("=== Example 5: Existence Checking ===")
    
    graph_name = "conditional_graph"
    
    # Check if graph exists
    if FastGraph(graph_name).exists():
        print("Graph exists, loading existing data")
        graph = FastGraph(graph_name)
        graph.load()
        print(f"Loaded graph with {len(graph.graph['nodes'])} nodes")
    else:
        print("Graph does not exist, creating new graph")
        with FastGraph(graph_name) as graph:
            graph.add_node("starter", data="initial_data")
            graph.add_node("seed", value=42)
            print("Created new graph with initial data")
    
    # Check specific paths
    graph = FastGraph("checker")
    if graph.exists(f"{graph_name}.msgpack"):
        print(f"Found {graph_name}.msgpack file")
    elif graph.exists(f"{graph_name}.json"):
        print(f"Found {graph_name}.json file")
    else:
        print(f"No {graph_name} graph file found")
    
    print()


def example_6_enhanced_error_handling():
    """
    Example 6: Enhanced error handling with automatic fallbacks.
    
    Demonstrates improved error handling in the Enhanced API
    with automatic fallbacks and better error messages.
    """
    print("=== Example 6: Enhanced Error Handling ===")
    
    # Enhanced error handling with auto-fallback
    graph = FastGraph("error_demo")
    
    try:
        # Try to load with auto-discovery
        graph.load()
        print("Successfully loaded with auto-discovery")
    except Exception as e:
        print(f"Auto-discovery failed: {e}")
        try:
            # Fallback to explicit path
            graph.load("error_demo.msgpack")
            print("Successfully loaded with explicit path")
        except Exception as e2:
            print(f"Explicit load also failed: {e2}")
            print("Creating new graph instead")
            graph.add_node("fallback", data="created_due_to_error")
    
    # Enhanced save with error recovery
    try:
        saved_path = graph.save()
        print(f"Saved successfully to: {saved_path}")
    except Exception as e:
        print(f"Save failed: {e}")
        # Try alternative location
        try:
            temp_path = graph.save("temp_error_demo")
            print(f"Saved to alternative location: {temp_path}")
        except Exception as e2:
            print(f"Alternative save also failed: {e2}")
    
    print()


def main():
    """
    Run all enhanced basic usage examples.
    """
    print("FastGraph Enhanced API v2.0 - Basic Usage Examples")
    print("=" * 60)
    print()
    
    # Run all examples
    example_1_zero_configuration_graph()
    example_2_smart_persistence()
    example_3_automatic_format_detection()
    example_4_resource_management()
    example_5_existence_checking()
    example_6_enhanced_error_handling()
    
    print("All examples completed successfully!")
    print()
    print("Key Benefits of Enhanced API:")
    print("✅ Zero configuration required")
    print("✅ Automatic path and format resolution")
    print("✅ Smart persistence with auto-discovery")
    print("✅ Automatic resource management")
    print("✅ Enhanced error handling")
    print("✅ Backward compatibility maintained")


if __name__ == "__main__":
    main()
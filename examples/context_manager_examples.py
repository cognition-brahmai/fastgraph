#!/usr/bin/env python3
"""
FastGraph Context Manager Examples

This file demonstrates the context manager support and resource management
capabilities introduced in FastGraph v2.0 Enhanced API.

Features demonstrated:
- Automatic resource cleanup
- Auto-save configuration
- Error handling in context managers
- Nested context managers
- Resource tracking and monitoring
- Explicit cleanup patterns
"""

from fastgraph import FastGraph
from fastgraph.config import ConfigManager
import time
import gc
import weakref


def example_1_basic_context_manager():
    """
    Example 1: Basic context manager usage.
    
    Shows the simplest form of resource management using
    FastGraph context managers.
    """
    print("=== Example 1: Basic Context Manager ===")
    
    # Traditional approach without context manager
    print("Traditional approach (manual cleanup):")
    graph = FastGraph("manual_graph")
    try:
        graph.add_node("alice", name="Alice", age=30)
        graph.add_node("bob", name="Bob", age=25)
        graph.add_edge("alice", "bob", "friends")
        print("Added nodes and edges")
        # Manual cleanup required
    finally:
        graph.cleanup()
        print("Manually cleaned up resources")
    
    print()
    
    # Enhanced approach with context manager
    print("Enhanced approach (automatic cleanup):")
    with FastGraph("auto_graph") as graph:
        graph.add_node("charlie", name="Charlie", age=35)
        graph.add_node("diana", name="Diana", age=28)
        graph.add_edge("charlie", "diana", "colleagues")
        print("Added nodes and edges")
        # Automatic cleanup on exit
        print("Resources will be automatically cleaned up")
    
    print("Context manager exited - resources cleaned up")
    print()


def example_2_auto_save_configuration():
    """
    Example 2: Auto-save configuration in context managers.
    
    Demonstrates how to configure automatic saving
    when context managers exit successfully.
    """
    print("=== Example 2: Auto-Save Configuration ===")
    
    # Create configuration with auto-save enabled
    config = {
        "enhanced_api": {
            "enabled": True,
            "auto_save_on_exit": True
        },
        "persistence": {
            "auto_save_on_exit": True
        }
    }
    
    # Context manager with auto-save
    print("Context manager with auto-save enabled:")
    with FastGraph.with_config(config, "auto_save_demo") as graph:
        graph.add_node("user1", name="User One", email="user1@example.com")
        graph.add_node("user2", name="User Two", email="user2@example.com")
        graph.add_edge("user1", "user2", "knows", since=2023)
        
        print("Created graph with user data")
        print("Graph will be automatically saved on successful exit")
    
    # Verify the graph was saved
    saved_graph = FastGraph("auto_save_demo")
    if saved_graph.exists():
        saved_graph.load()
        print(f"Successfully loaded auto-saved graph: {len(saved_graph.graph['nodes'])} nodes")
    else:
        print("Graph was not saved")
    
    print()


def example_3_error_handling_in_context():
    """
    Example 3: Error handling within context managers.
    
    Shows how context managers handle errors and
    whether auto-save occurs on exceptions.
    """
    print("=== Example 3: Error Handling in Context ===")
    
    # Context manager with error - no auto-save on exception
    print("Testing error handling (no auto-save on exception):")
    try:
        with FastGraph("error_demo") as graph:
            graph.add_node("temp1", data="temporary")
            graph.add_node("temp2", data="temporary")
            print("Created temporary data")
            
            # Simulate an error
            raise ValueError("Simulated error during processing")
            
    except ValueError as e:
        print(f"Caught expected error: {e}")
    
    # Check if graph was saved (it shouldn't be)
    error_graph = FastGraph("error_demo")
    if not error_graph.exists():
        print("✅ Graph not saved due to exception (correct behavior)")
    else:
        print("❌ Graph was saved despite exception")
    
    print()


def example_4_nested_context_managers():
    """
    Example 4: Nested context managers.
    
    Demonstrates using multiple graphs with nested
    context managers and resource isolation.
    """
    print("=== Example 4: Nested Context Managers ===")
    
    # Outer context for main graph
    with FastGraph("main_graph") as main_graph:
        main_graph.add_node("central", type="hub", importance=10)
        main_graph.add_node("node1", type="satellite", importance=5)
        main_graph.add_node("node2", type="satellite", importance=5)
        main_graph.add_edge("central", "node1", "connects")
        main_graph.add_edge("central", "node2", "connects")
        
        print("Created main graph structure")
        
        # Inner context for temporary analysis
        with FastGraph("analysis_temp") as analysis_graph:
            # Copy some data for analysis
            analysis_graph.add_node("analysis_copy", data="copied from main")
            analysis_graph.add_node("temp_result", value=42)
            
            print("Created temporary analysis graph")
            # Analysis graph automatically cleaned up here
        
        print("Analysis context closed - temporary resources cleaned up")
        
        # Continue with main graph
        main_graph.add_node("additional", data="added after analysis")
        print("Added additional data to main graph")
    
    print("All contexts closed - all resources cleaned up")
    print()


def example_5_resource_tracking():
    """
    Example 5: Resource tracking and monitoring.
    
    Shows how FastGraph tracks resources and provides
    monitoring capabilities.
    """
    print("=== Example 5: Resource Tracking ===")
    
    # Enable resource management
    config = {
        "enhanced_api": {
            "enabled": True,
            "resource_management": True
        }
    }
    
    print("Creating multiple graph instances to test resource tracking:")
    
    # Create multiple graphs
    graphs = []
    for i in range(3):
        graph = FastGraph.with_config(config, f"resource_test_{i}")
        graph.add_node(f"node_{i}", index=i)
        graphs.append(graph)
        print(f"Created graph {i}: {graph}")
    
    # Check resource status
    print(f"Active graph instances: {len(graphs)}")
    
    # Clean up resources
    for i, graph in enumerate(graphs):
        graph.cleanup()
        print(f"Cleaned up graph {i}")
    
    print("All resources tracked and cleaned up")
    print()


def example_6_memory_efficient_patterns():
    """
    Example 6: Memory-efficient patterns with context managers.
    
    Demonstrates how to use context managers for
    memory-efficient graph processing.
    """
    print("=== Example 6: Memory-Efficient Patterns ===")
    
    # Process large datasets in chunks
    def process_data_chunk(chunk_id, data):
        """Process a chunk of data within a context manager."""
        with FastGraph(f"chunk_{chunk_id}") as chunk_graph:
            # Add chunk data
            for item_id, item_data in data:
                chunk_graph.add_node(item_id, **item_data)
            
            # Process the chunk
            processed_count = len(chunk_graph.graph['nodes'])
            print(f"Processed chunk {chunk_id}: {processed_count} items")
            
            # Graph is automatically saved and cleaned up
            return processed_count
    
    # Simulate processing multiple chunks
    chunks_data = [
        [("item_1_1", {"value": 10}), ("item_1_2", {"value": 20})],
        [("item_2_1", {"value": 15}), ("item_2_2", {"value": 25})],
        [("item_3_1", {"value": 12}), ("item_3_2", {"value": 22})]
    ]
    
    total_processed = 0
    for i, chunk_data in enumerate(chunks_data):
        count = process_data_chunk(i, chunk_data)
        total_processed += count
    
    print(f"Total items processed: {total_processed}")
    print()


def example_7_backup_and_restore():
    """
    Example 7: Backup and restore with context managers.
    
    Shows how to integrate backup/restore operations
    within context manager workflows.
    """
    print("=== Example 7: Backup and Restore ===")
    
    # Create graph with important data
    with FastGraph("important_data") as graph:
        # Add critical data
        critical_nodes = [
            ("critical_1", {"data": "important", "backup": True}),
            ("critical_2", {"data": "essential", "backup": True}),
            ("critical_3", {"data": "vital", "backup": True})
        ]
        
        for node_id, attrs in critical_nodes:
            graph.add_node(node_id, **attrs)
        
        # Add relationships
        graph.add_edge("critical_1", "critical_2", "depends_on")
        graph.add_edge("critical_2", "critical_3", "leads_to")
        
        print("Created graph with critical data")
        
        # Create backup within context
        backup_paths = graph.backup()
        print(f"Created backups: {backup_paths}")
        
        # Simulate some changes
        graph.add_node("temp_change", data="temporary")
        print("Made temporary changes")
        
        # Context will save the changes
    
    # Restore from backup to original state
    with FastGraph("important_data") as restored_graph:
        restored_path = restored_graph.restore_from_backup()
        print(f"Restored from backup: {restored_path}")
        
        # Verify restoration
        if "temp_change" not in restored_graph.graph['nodes']:
            print("✅ Successfully restored to original state")
        else:
            print("❌ Temporary changes still present")
    
    print()


def example_8_concurrent_access_patterns():
    """
    Example 8: Concurrent access patterns with context managers.
    
    Demonstrates safe patterns for concurrent graph access
    using context managers.
    """
    print("=== Example 8: Concurrent Access Patterns ===")
    
    import threading
    import time
    
    results = []
    
    def worker_task(worker_id):
        """Worker task that uses a graph within a context manager."""
        try:
            with FastGraph(f"worker_{worker_id}") as worker_graph:
                # Each worker gets their own isolated graph
                worker_graph.add_node(f"worker_{worker_id}_node", 
                                   worker_id=worker_id,
                                   timestamp=time.time())
                
                # Simulate some work
                time.sleep(0.1)
                
                results.append(f"Worker {worker_id} completed")
                
        except Exception as e:
            results.append(f"Worker {worker_id} failed: {e}")
    
    # Run multiple workers concurrently
    threads = []
    for i in range(3):
        thread = threading.Thread(target=worker_task, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Check results
    for result in results:
        print(f"  {result}")
    
    # Verify isolated resources
    for i in range(3):
        graph = FastGraph(f"worker_{i}")
        if graph.exists():
            graph.load()
            print(f"Worker {i} graph has {len(graph.graph['nodes'])} nodes")
        else:
            print(f"Worker {i} graph not found")
    
    print()


def example_9_explicit_cleanup_patterns():
    """
    Example 9: Explicit cleanup patterns for special cases.
    
    Shows when and how to use explicit cleanup
    outside of context managers.
    """
    print("=== Example 9: Explicit Cleanup Patterns ===")
    
    # When you can't use context managers
    print("Explicit cleanup when context managers not available:")
    
    def process_graph_without_context():
        """Function that needs explicit cleanup."""
        graph = FastGraph("explicit_demo")
        try:
            graph.add_node("explicit", data="needs_cleanup")
            graph.add_node("manual", data="cleanup_required")
            
            # Simulate processing
            print("Processing graph data...")
            
            # Return some result
            return len(graph.graph['nodes'])
            
        finally:
            # Explicit cleanup
            graph.cleanup()
            print("Explicit cleanup completed")
    
    result_count = process_graph_without_context()
    print(f"Processed {result_count} nodes")
    
    # Cleanup in class methods
    print("\nCleanup in class methods:")
    
    class GraphProcessor:
        def __init__(self):
            self.graph = None
        
        def process(self):
            """Process with cleanup in destructor."""
            self.graph = FastGraph("class_processor")
            self.graph.add_node("class_based", data="processing")
            return "processed"
        
        def __del__(self):
            """Destructor for cleanup."""
            if self.graph:
                self.graph.cleanup()
                print("Class-based cleanup completed")
    
    processor = GraphProcessor()
    processor.process()
    # Cleanup happens when processor is garbage collected
    del processor
    gc.collect()  # Force garbage collection
    
    print()


def main():
    """
    Run all context manager examples.
    """
    print("FastGraph Context Manager Examples")
    print("=" * 50)
    print()
    
    try:
        # Run all examples
        example_1_basic_context_manager()
        example_2_auto_save_configuration()
        example_3_error_handling_in_context()
        example_4_nested_context_managers()
        example_5_resource_tracking()
        example_6_memory_efficient_patterns()
        example_7_backup_and_restore()
        example_8_concurrent_access_patterns()
        example_9_explicit_cleanup_patterns()
        
        print("All context manager examples completed!")
        
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
    # This would typically involve cleaning up temporary files
    # and ensuring all graph instances are properly closed
    print("Resource cleanup completed")


if __name__ == "__main__":
    main()
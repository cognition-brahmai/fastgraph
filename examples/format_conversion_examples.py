#!/usr/bin/env python3
"""
FastGraph Format Conversion Examples

This file demonstrates the enhanced format conversion capabilities
introduced in FastGraph v2.0, making it easy to convert between
different serialization formats.

Features demonstrated:
- Automatic format detection
- Built-in format conversion
- Batch format conversion
- Format extraction workflows
- Streaming conversion for large files
"""

from fastgraph import FastGraph
import tempfile
import os
import json
from pathlib import Path


def create_sample_graph():
    """
    Create a sample graph for format conversion examples.
    """
    graph = FastGraph("sample")
    
    # Add nodes
    people = [
        ("alice", {"name": "Alice Smith", "age": 30, "department": "Engineering"}),
        ("bob", {"name": "Bob Johnson", "age": 25, "department": "Marketing"}),
        ("charlie", {"name": "Charlie Davis", "age": 35, "department": "Engineering"}),
        ("diana", {"name": "Diana Prince", "age": 28, "department": "Sales"}),
        ("eve", {"name": "Eve Wilson", "age": 32, "department": "Engineering"})
    ]
    
    for person_id, attrs in people:
        graph.add_node(person_id, **attrs)
    
    # Add edges
    relationships = [
        ("alice", "bob", "colleagues", since=2021, project="Alpha"),
        ("alice", "charlie", "mentors", since=2020),
        ("bob", "diana", "collaborates", project="Beta"),
        ("charlie", "eve", "manages", since=2019),
        ("diana", "eve", "reports_to", since=2022)
    ]
    
    for src, dst, rel, **attrs in relationships:
        graph.add_edge(src, dst, rel, **attrs)
    
    return graph


def example_1_basic_format_conversion():
    """
    Example 1: Basic format conversion between JSON and MessagePack.
    
    Shows the simplest way to convert between formats using the
    enhanced translate() method.
    """
    print("=== Example 1: Basic Format Conversion ===")
    
    # Create and save sample graph in JSON
    graph = create_sample_graph()
    json_path = graph.save("sample_graph.json", format="json")
    print(f"Created sample graph: {json_path}")
    
    # Convert JSON to MessagePack
    graph = FastGraph("format_demo")
    msgpack_path = graph.translate("sample_graph.json", "sample_graph.msgpack", 
                                  "json", "msgpack")
    print(f"Converted JSON to MessagePack: {msgpack_path}")
    
    # Convert MessagePack to Pickle
    pickle_path = graph.translate("sample_graph.msgpack", "sample_graph.pkl",
                                "msgpack", "pickle")
    print(f"Converted MessagePack to Pickle: {pickle_path}")
    
    # Convert Pickle back to JSON
    json_path2 = graph.translate("sample_graph.pkl", "sample_graph_v2.json",
                                "pickle", "json")
    print(f"Converted Pickle to JSON: {json_path2}")
    
    print()


def example_2_automatic_format_detection():
    """
    Example 2: Automatic format detection during conversion.
    
    Demonstrates how FastGraph automatically detects source formats
    and converts to target formats.
    """
    print("=== Example 2: Automatic Format Detection ===")
    
    # Create graphs in different formats
    graph = create_sample_graph()
    
    # Save in different formats without specifying format
    json_file = "auto_demo.json"
    msgpack_file = "auto_demo.msgpack"
    
    graph.save(json_file, format="json")
    graph.save(msgpack_file, format="msgpack")
    
    # Convert with auto-detected source format
    converter = FastGraph("auto_converter")
    
    # Auto-detect JSON and convert to MessagePack
    result1 = converter.translate(json_file, "converted_auto.msgpack")
    print(f"Auto-detected JSON, converted to: {result1}")
    
    # Auto-detect MessagePack and convert to JSON
    result2 = converter.translate(msgpack_file, "converted_auto.json")
    print(f"Auto-detected MessagePack, converted to: {result2}")
    
    # Auto-detect and convert to Pickle
    result3 = converter.translate(json_file, "converted_auto.pkl")
    print(f"Auto-detected JSON, converted to Pickle: {result3}")
    
    print()


def example_3_format_extraction():
    """
    Example 3: Extract data to different formats using get_translation().
    
    Shows how to extract graph data to specific formats without
    needing to specify output paths.
    """
    print("=== Example 3: Format Extraction ===")
    
    # Create sample graph
    graph = create_sample_graph()
    original_path = graph.save("extraction_demo.json", format="json")
    print(f"Original file: {original_path}")
    
    # Extract to different formats
    extractor = FastGraph("extractor")
    
    # Extract to MessagePack
    msgpack_path = extractor.get_translation("extraction_demo.json", "msgpack")
    print(f"Extracted to MessagePack: {msgpack_path}")
    
    # Extract to Pickle
    pickle_path = extractor.get_translation("extraction_demo.json", "pickle")
    print(f"Extracted to Pickle: {pickle_path}")
    
    # Extract to JSON (for validation/comparison)
    json_path = extractor.get_translation("extraction_demo.json", "json")
    print(f"Extracted to JSON: {json_path}")
    
    print()


def example_4_batch_format_conversion():
    """
    Example 4: Batch conversion of multiple formats.
    
    Demonstrates converting a single source file to multiple
    target formats efficiently.
    """
    print("=== Example 4: Batch Format Conversion ===")
    
    # Create source graph
    graph = create_sample_graph()
    source_path = graph.save("batch_source.json", format="json")
    print(f"Source file: {source_path}")
    
    # Convert to multiple formats
    converter = FastGraph("batch_converter")
    
    target_formats = ["msgpack", "pickle", "json"]
    converted_files = []
    
    for target_format in target_formats:
        target_file = f"batch_source.{target_format}"
        try:
            result = converter.translate("batch_source.json", target_file, "json", target_format)
            converted_files.append(result)
            print(f"Converted to {target_format}: {result}")
        except Exception as e:
            print(f"Failed to convert to {target_format}: {e}")
    
    print(f"Successfully converted {len(converted_files)} files")
    print()


def example_5_custom_output_directories():
    """
    Example 5: Format conversion with custom output directories.
    
    Shows how to specify custom output directories for converted files.
    """
    print("=== Example 5: Custom Output Directories ===")
    
    # Create source graph
    graph = create_sample_graph()
    source_path = graph.save("directory_demo.json", format="json")
    
    # Create temporary directory for conversions
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")
        
        converter = FastGraph("dir_converter")
        
        # Convert to MessagePack in custom directory
        msgpack_path = converter.translate(
            "directory_demo.json", 
            Path(temp_dir) / "converted.msgpack"
        )
        print(f"Converted to MessagePack in custom dir: {msgpack_path}")
        
        # Extract to Pickle in custom directory
        pickle_path = converter.get_translation(
            "directory_demo.json", 
            "pickle", 
            temp_dir
        )
        print(f"Extracted to Pickle in custom dir: {pickle_path}")
        
        # List all files in temp directory
        temp_files = list(Path(temp_dir).glob("*"))
        print(f"Files in temp directory: {[f.name for f in temp_files]}")
    
    print()


def example_6_format_validation():
    """
    Example 6: Format conversion with validation and error handling.
    
    Demonstrates robust format conversion with validation
    and proper error handling.
    """
    print("=== Example 6: Format Validation and Error Handling ===")
    
    # Create valid source
    graph = create_sample_graph()
    valid_source = graph.save("validation_demo.json", format="json")
    
    # Test valid conversions
    validator = FastGraph("validator")
    
    print("Testing valid conversions:")
    try:
        result = validator.translate(valid_source, "valid_output.msgpack")
        print(f"✅ Valid conversion: {result}")
    except Exception as e:
        print(f"❌ Valid conversion failed: {e}")
    
    # Test invalid source file
    print("\nTesting invalid source file:")
    invalid_source = "invalid_file.txt"
    with open(invalid_source, 'w') as f:
        f.write("This is not a valid graph file")
    
    try:
        result = validator.translate(invalid_source, "should_fail.msgpack")
        print(f"❌ Unexpected success: {result}")
    except Exception as e:
        print(f"✅ Expected failure: {e}")
    
    # Clean up
    if os.path.exists(invalid_source):
        os.remove(invalid_source)
    
    print()


def example_7_large_file_conversion():
    """
    Example 7: Conversion of larger graphs with streaming.
    
    Demonstrates efficient conversion of larger graph files
    using streaming approaches.
    """
    print("=== Example 7: Large File Conversion ===")
    
    # Create a larger graph for demonstration
    large_graph = FastGraph("large_demo")
    
    # Add more nodes and edges to simulate a larger graph
    print("Creating larger graph...")
    for i in range(100):
        node_id = f"node_{i}"
        large_graph.add_node(node_id, 
                          index=i, 
                          category=f"cat_{i % 10}",
                          value=i * 10)
    
    # Add edges creating a connected network
    for i in range(99):
        large_graph.add_edge(f"node_{i}", f"node_{i+1}", "connects", weight=i % 5)
    
    # Add some additional connections
    for i in range(0, 90, 5):
        large_graph.add_edge(f"node_{i}", f"node_{i+10}", "jumps", distance=10)
    
    print(f"Created graph with {len(large_graph.graph['nodes'])} nodes and {len(large_graph._edges)} edges")
    
    # Save in JSON (larger, human-readable)
    json_path = large_graph.save("large_demo.json", format="json")
    print(f"Saved JSON file: {json_path}")
    
    # Convert to MessagePack (more compact)
    converter = FastGraph("large_converter")
    msgpack_path = converter.translate("large_demo.json", "large_demo.msgpack")
    print(f"Converted to MessagePack: {msgpack_path}")
    
    # Compare file sizes
    json_size = os.path.getsize("large_demo.json")
    msgpack_size = os.path.getsize("large_demo.msgpack")
    
    print(f"JSON file size: {json_size:,} bytes")
    print(f"MessagePack file size: {msgpack_size:,} bytes")
    print(f"Compression ratio: {msgpack_size / json_size:.2%}")
    
    print()


def example_8_round_trip_conversion():
    """
    Example 8: Round-trip conversion to test data integrity.
    
    Converts data through multiple formats and verifies
    that the data remains intact.
    """
    print("=== Example 8: Round-Trip Conversion Testing ===")
    
    # Create original graph
    original_graph = create_sample_graph()
    original_data = {
        'nodes': original_graph.graph['nodes'].copy(),
        'edges_count': len(original_graph._edges)
    }
    
    print(f"Original graph: {len(original_data['nodes'])} nodes, {original_data['edges_count']} edges")
    
    # Perform round-trip conversion: JSON -> MessagePack -> Pickle -> JSON
    converter = FastGraph("roundtrip")
    
    # Step 1: JSON to MessagePack
    step1 = converter.translate("roundtrip_source.json", "step1.msgpack")
    
    # Step 2: MessagePack to Pickle  
    step2 = converter.translate("step1.msgpack", "step2.pkl")
    
    # Step 3: Pickle back to JSON
    step3 = converter.translate("step2.pkl", "roundtrip_final.json")
    
    print(f"Round-trip conversion completed: {step3}")
    
    # Verify data integrity
    final_graph = FastGraph("final")
    final_graph.load("roundtrip_final.json")
    
    final_data = {
        'nodes': final_graph.graph['nodes'],
        'edges_count': len(final_graph._edges)
    }
    
    # Compare data
    nodes_match = original_data['nodes'] == final_data['nodes']
    edges_match = original_data['edges_count'] == final_data['edges_count']
    
    print(f"Data integrity check:")
    print(f"  Nodes match: {nodes_match}")
    print(f"  Edges count match: {edges_match}")
    
    if nodes_match and edges_match:
        print("✅ Round-trip conversion successful - data integrity maintained")
    else:
        print("❌ Round-trip conversion failed - data corruption detected")
    
    print()


def main():
    """
    Run all format conversion examples.
    """
    print("FastGraph Format Conversion Examples")
    print("=" * 50)
    print()
    
    # Clean up any existing files
    cleanup_files()
    
    try:
        # Run all examples
        example_1_basic_format_conversion()
        example_2_automatic_format_detection()
        example_3_format_extraction()
        example_4_batch_format_conversion()
        example_5_custom_output_directories()
        example_6_format_validation()
        example_7_large_file_conversion()
        example_8_round_trip_conversion()
        
        print("All format conversion examples completed!")
        
    finally:
        # Clean up generated files
        cleanup_files()


def cleanup_files():
    """
    Clean up files generated during examples.
    """
    patterns = [
        "*.json", "*.msgpack", "*.pkl", "*.txt",
        "converted_*", "batch_*", "auto_*", "directory_*",
        "validation_*", "large_*", "roundtrip_*", "step*",
        "sample_*", "extraction_*", "temp_*"
    ]
    
    import glob
    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception:
                pass  # Ignore cleanup errors


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Comprehensive test suite for FastGraph encoding parameter fix.

This test suite verifies that the fix for the gzip encoding parameter issue
works correctly and doesn't introduce any regressions.
"""

import os
import sys
import tempfile
import json
import traceback
from pathlib import Path

# Add the fastgraph module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastgraph import FastGraph
from fastgraph.exceptions import PersistenceError


def test_original_failing_code():
    """Test the original failing code snippet from the error report."""
    print("=" * 60)
    print("Testing original failing code snippet...")
    print("=" * 60)
    
    try:
        # Create the graph exactly as in the original failing code
        graph = FastGraph("my_graph")
        
        graph.add_node("alice", name="Alice", age=30, type="Person")
        graph.add_node("bob", name="Bob", age=25, type="Person")
        graph.add_node("company", name="TechCorp", type="Company")
        
        graph.add_edge("alice", "bob", "friends", since=2021)
        graph.add_edge("alice", "company", "works_at", role="Engineer")
        graph.add_edge("bob", "company", "works_at", role="Manager")
        
        people = graph.find_nodes(type="Person")
        print(f"Found {len(people)} people")
        
        friends = graph.neighbors_out("alice", rel="friends")
        print(f"Alice's friends: {[n for n, edge in friends]}")
        
        # This was the line that failed with TypeError
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            temp_path = tmp.name
        
        print(f"Saving to: {temp_path}")
        graph.save(temp_path, format="json")
        print("Save successful - no TypeError!")
        
        # Verify the file was created and contains valid data
        if os.path.exists(temp_path):
            file_size = os.path.getsize(temp_path)
            print(f"File created successfully ({file_size} bytes)")
            
            # Check if it's gzipped by reading first few bytes
            with open(temp_path, 'rb') as f:
                header = f.read(2)
                is_gzipped = header == b'\x1f\x8b'
                print(f"File is {'gzipped' if is_gzipped else 'uncompressed'}")
        
        # Clean up
        os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"FAIL: Test failed: {e}")
        print(f"Exception type: {type(e).__name__}")
        traceback.print_exc()
        return False


def test_compressed_uncompressed_json():
    """Test both compressed and uncompressed JSON saving/loading."""
    print("\n" + "=" * 60)
    print("Testing compressed and uncompressed JSON...")
    print("=" * 60)
    
    try:
        # Create test graph
        graph = FastGraph("test_graph")
        graph.add_node("node1", name="Test Node 1", value=42, type="test")
        graph.add_node("node2", name="Test Node 2", value=84, type="test")
        graph.add_edge("node1", "node2", "test_edge", weight=1.5)
        
        # Test compressed JSON (default)
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            compressed_path = tmp.name
        
        print(f"Testing compressed JSON save to: {compressed_path}")
        graph.save(compressed_path, format="json")
        
        # Verify compressed file
        with open(compressed_path, 'rb') as f:
            header = f.read(2)
            is_compressed = header == b'\x1f\x8b'
            print(f"Compression status: {'compressed' if is_compressed else 'uncompressed'}")
        
        # Load and verify
        graph2 = FastGraph("loaded_graph")
        graph2.load(compressed_path, format="json")
        
        # Verify data integrity
        original_nodes = len(graph.graph["nodes"])
        loaded_nodes = len(graph2.graph["nodes"])
        original_edges = len(graph._edges)
        loaded_edges = len(graph2._edges)
        
        print(f"Original: {original_nodes} nodes, {original_edges} edges")
        print(f"Loaded: {loaded_nodes} nodes, {loaded_edges} edges")
        
        assert original_nodes == loaded_nodes, "Node count mismatch"
        assert original_edges == loaded_edges, "Edge count mismatch"
        
        # Test uncompressed JSON
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            uncompressed_path = tmp.name
        
        print(f"Testing uncompressed JSON save to: {uncompressed_path}")
        # We need to modify the persistence manager to disable compression
        # For now, let's test by manually calling the persistence manager
        from fastgraph.core.persistence import PersistenceManager
        import threading
        
        pm = PersistenceManager(threading.RLock())
        data = {
            "nodes": graph.graph["nodes"],
            "_edges": graph._edges,
            "metadata": graph.graph["metadata"],
            "node_indexes": graph.index_manager.node_indexes
        }
        
        # Save without compression
        pm.save(data, uncompressed_path, format="json", compress=False)
        
        # Verify uncompressed file
        with open(uncompressed_path, 'rb') as f:
            header = f.read(2)
            is_uncompressed_file = header != b'\x1f\x8b'
            print(f"Uncompressed file status: {'uncompressed' if is_uncompressed_file else 'compressed'}")
        
        # Load uncompressed file
        graph3 = FastGraph("loaded_uncompressed")
        graph3.load(uncompressed_path, format="json")
        
        # Verify data integrity for uncompressed
        loaded_nodes2 = len(graph3.graph["nodes"])
        loaded_edges2 = len(graph3._edges)
        
        print(f"Uncompressed loaded: {loaded_nodes2} nodes, {loaded_edges2} edges")
        assert original_nodes == loaded_nodes2, "Node count mismatch in uncompressed"
        assert original_edges == loaded_edges2, "Edge count mismatch in uncompressed"
        
        # Clean up
        os.unlink(compressed_path)
        os.unlink(uncompressed_path)
        
        return True
        
    except Exception as e:
        print(f"FAIL: Compressed/uncompressed test failed: {e}")
        traceback.print_exc()
        return False


def test_data_integrity():
    """Test data integrity after save/load cycles."""
    print("\n" + "=" * 60)
    print("Testing data integrity...")
    print("=" * 60)
    
    try:
        # Create a more complex graph
        graph = FastGraph("integrity_test")
        
        # Add various types of nodes and attributes
        graph.add_node("person1", name="Alice", age=30, type="Person", scores=[85, 90, 78])
        graph.add_node("person2", name="Bob", age=25, type="Person", scores=[92, 88, 95])
        graph.add_node("company1", name="TechCorp", type="Company", founded=2010, employees=500)
        graph.add_node("project1", name="ProjectX", type="Project", budget=100000.50, active=True)
        
        # Add various types of edges
        graph.add_edge("person1", "company1", "works_at", role="Engineer", since=2020)
        graph.add_edge("person2", "company1", "works_at", role="Manager", since=2019)
        graph.add_edge("person1", "project1", "assigned_to", hours=40)
        graph.add_edge("person2", "project1", "manages", since=2021)
        
        # Store original data for comparison
        original_people = list(graph.find_nodes(type="Person"))
        original_companies = list(graph.find_nodes(type="Company"))
        original_projects = list(graph.find_nodes(type="Project"))
        original_edges = list(graph.find_edges())
        
        print(f"Original graph: {len(graph.graph['nodes'])} nodes, {len(graph._edges)} edges")
        print(f"People: {len(original_people)}")
        print(f"Companies: {len(original_companies)}")
        print(f"Projects: {len(original_projects)}")
        print(f"Edges: {len(original_edges)}")
        
        # Test multiple save/load cycles
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            temp_path = tmp.name
        
        for cycle in range(3):
            print(f"\nSave/load cycle {cycle + 1}:")
            
            # Save
            graph.save(temp_path, format="json")
            print(f"  Saved to {temp_path}")
            
            # Clear and reload
            graph.clear()
            graph.load(temp_path, format="json")
            print(f"  Loaded from {temp_path}")
            
            # Verify data integrity
            current_people = list(graph.find_nodes(type="Person"))
            current_companies = list(graph.find_nodes(type="Company"))
            current_projects = list(graph.find_nodes(type="Project"))
            current_edges = list(graph.find_edges())
            
            print(f"  Current: {len(graph.graph['nodes'])} nodes, {len(graph._edges)} edges")
            
            # Detailed verification
            assert len(current_people) == len(original_people), f"People count mismatch: {len(current_people)} vs {len(original_people)}"
            assert len(current_companies) == len(original_companies), f"Companies count mismatch"
            assert len(current_projects) == len(original_projects), f"Projects count mismatch"
            assert len(current_edges) == len(original_edges), f"Edges count mismatch"
            
            # Verify specific attributes
            for person_id, person_attrs in current_people:
                original_attrs = dict(original_people[[i for i, (pid, _) in enumerate(original_people) if pid == person_id][0]][1])
                assert person_attrs['name'] == original_attrs['name'], f"Name mismatch for {person_id}"
                assert person_attrs['age'] == original_attrs['age'], f"Age mismatch for {person_id}"
                assert person_attrs['type'] == original_attrs['type'], f"Type mismatch for {person_id}"
                assert person_attrs['scores'] == original_attrs['scores'], f"Scores mismatch for {person_id}"
        
        print("\nAll data integrity checks passed!")
        
        # Clean up
        os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"FAIL: Data integrity test failed: {e}")
        traceback.print_exc()
        return False


def test_error_conditions():
    """Test error conditions and edge cases."""
    print("\n" + "=" * 60)
    print("Testing error conditions...")
    print("=" * 60)
    
    try:
        graph = FastGraph("error_test")
        graph.add_node("test", name="Test")
        
        # Test loading non-existent file
        try:
            graph.load("/non/existent/file.json", format="json")
            print("Should have failed for non-existent file")
            return False
        except PersistenceError:
            print("Correctly failed for non-existent file")
        
        # Test invalid format
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            temp_path = tmp.name
        
        try:
            graph.save(temp_path, format="invalid_format")
            print("Should have failed for invalid format")
            return False
        except PersistenceError:
            print("Correctly failed for invalid format")
        
        # Test corrupted file
        with open(temp_path, 'w') as f:
            f.write("invalid json content")
        
        try:
            graph.load(temp_path, format="json")
            print("Should have failed for corrupted file")
            return False
        except (PersistenceError, json.JSONDecodeError):
            print("Correctly failed for corrupted file")
        
        # Clean up
        os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"FAIL: Error conditions test failed: {e}")
        traceback.print_exc()
        return False


def test_multiple_formats():
    """Test that JSON fix doesn't break other formats."""
    print("\n" + "=" * 60)
    print("Testing multiple formats...")
    print("=" * 60)
    
    try:
        graph = FastGraph("multi_format_test")
        graph.add_node("test1", name="Test1", value=42)
        graph.add_node("test2", name="Test2", value=84)
        graph.add_edge("test1", "test2", "test_edge", weight=1.5)
        
        original_nodes = len(graph.graph["nodes"])
        original_edges = len(graph._edges)
        
        formats_to_test = ["json", "msgpack", "pickle"]
        
        for fmt in formats_to_test:
            print(f"Testing {fmt} format...")
            
            with tempfile.NamedTemporaryFile(suffix=f'.{fmt}', delete=False) as tmp:
                temp_path = tmp.name
            
            # Save
            graph.save(temp_path, format=fmt)
            print(f"  Saved {fmt}")
            
            # Load
            graph2 = FastGraph(f"loaded_{fmt}")
            graph2.load(temp_path, format=fmt)
            print(f"  Loaded {fmt}")
            
            # Verify
            assert len(graph2.graph["nodes"]) == original_nodes, f"Node count mismatch for {fmt}"
            assert len(graph2._edges) == original_edges, f"Edge count mismatch for {fmt}"
            
            # Clean up
            os.unlink(temp_path)
        
        print("All formats work correctly!")
        return True
        
    except Exception as e:
        print(f"FAIL: Multiple formats test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("FastGraph Encoding Parameter Fix - Comprehensive Test Suite")
    print("=" * 80)
    
    tests = [
        ("Original Failing Code", test_original_failing_code),
        ("Compressed/Uncompressed JSON", test_compressed_uncompressed_json),
        ("Data Integrity", test_data_integrity),
        ("Error Conditions", test_error_conditions),
        ("Multiple Formats", test_multiple_formats),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\nRunning {test_name} test...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"FAIL: {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nALL TESTS PASSED! The fix is working correctly.")
        print("No TypeError occurs during JSON save operations")
        print("Data integrity is maintained across save/load cycles")
        print("Both compressed and uncompressed JSON work correctly")
        print("Other formats remain unaffected")
        return True
    else:
        print(f"\n{total - passed} test(s) failed. Please review the issues above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
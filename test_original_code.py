#!/usr/bin/env python3
"""
Test the exact original failing code snippet to demonstrate the fix.
"""

import os
import sys
import tempfile

# Add the fastgraph module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastgraph import FastGraph

# This is the EXACT code that was failing before the fix
print("Running the exact original failing code snippet...")
print("=" * 50)

graph = FastGraph("my_graph")

graph.add_node("alice", name="Alice", age=30, type="Person")
graph.add_node("bob", name="Bob", age=25, type="Person")
graph.add_node("company", name="TechCorp", type="Company")

graph.add_edge("alice", "bob", "friends", since=2021)
graph.add_edge("alice", "company", "works_at", role="Engineer")
graph.add_edge("bob", "company", "works_at", role="Manager")

people = graph.find_nodes(type="Person")
print(len(people))

friends = graph.neighbors_out("alice", rel="friends")
print([n for n, edge in friends])

# This line was causing: TypeError: open() got an unexpected keyword argument 'encoding'
# It should now work without any error
graph.save("my_graph.json", format="json")

print("SUCCESS! The original failing code now works correctly.")
print("No TypeError occurred during the save operation.")

# Clean up the created file
if os.path.exists("my_graph.json"):
    os.unlink("my_graph.json")
    print("Cleaned up test file.")
#!/usr/bin/env python3
"""
FastGraph Basic Usage Example

This script demonstrates basic FastGraph operations including:
- Creating graphs
- Adding nodes and edges
- Querying the graph
- Using indexes
- Saving and loading
"""

import sys
import time
from pathlib import Path

# Add the parent directory to the path so we can import fastgraph
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastgraph import FastGraph
from fastgraph.config import ConfigManager


def main():
    """Demonstrate basic FastGraph usage."""
    print("🚀 FastGraph Basic Usage Example")
    print("=" * 40)
    
    # 1. Create a graph with default configuration
    print("\n1. Creating graph...")
    graph = FastGraph("social_network")
    print(f"✓ Created graph: {graph}")
    
    # 2. Add nodes
    print("\n2. Adding nodes...")
    
    # People
    graph.add_node("alice", name="Alice Smith", age=30, type="Person", city="New York")
    graph.add_node("bob", name="Bob Johnson", age=25, type="Person", city="San Francisco")
    graph.add_node("charlie", name="Charlie Brown", age=35, type="Person", city="New York")
    graph.add_node("diana", name="Diana Prince", age=28, type="Person", city="Los Angeles")
    
    # Organizations
    graph.add_node("techcorp", name="TechCorp Inc.", type="Company", industry="Technology")
    graph.add_node("startupx", name="StartupX", type="Company", industry="AI")
    
    print(f"✓ Added {len(graph.graph['nodes'])} nodes")
    
    # 3. Add edges
    print("\n3. Adding edges...")
    
    # Friendships
    graph.add_edge("alice", "bob", "friends", since=2021, close=True)
    graph.add_edge("alice", "charlie", "friends", since=2019, close=False)
    graph.add_edge("bob", "diana", "friends", since=2022, close=True)
    
    # Employment
    graph.add_edge("alice", "techcorp", "works_at", role="Engineer", since=2020, salary=95000)
    graph.add_edge("bob", "techcorp", "works_at", role="Manager", since=2019, salary=120000)
    graph.add_edge("charlie", "startupx", "works_at", role="CTO", since=2021, salary=150000)
    graph.add_edge("diana", "startupx", "works_at", role="Data Scientist", since=2022, salary=110000)
    
    # Other relationships
    graph.add_edge("alice", "startupx", "consults_for", since=2023)
    graph.add_edge("charlie", "alice", "mentors", since=2020)
    
    print(f"✓ Added {len(graph._edges)} edges")
    
    # 4. Basic queries
    print("\n4. Basic queries...")
    
    # Find all people
    people = graph.find_nodes(type="Person")
    print(f"Found {len(people)} people:")
    for person_id, attrs in people:
        print(f"  - {attrs['name']} ({attrs['age']}, {attrs['city']})")
    
    # Find employees at TechCorp
    techcorp_employees = graph.traversal_ops.neighbors_in("techcorp", rel="works_at")
    print(f"\nTechCorp employees:")
    for emp_id, edge in techcorp_employees:
        employee_attrs = graph.get_node(emp_id)
        print(f"  - {employee_attrs['name']}: {edge.get_attribute('role')} (${edge.get_attribute('salary'):,})")
    
    # 5. Build indexes for faster queries
    print("\n5. Building indexes...")
    graph.build_node_index("type")
    graph.build_node_index("city")
    graph.build_node_index("age")
    
    # Indexed query (much faster)
    start_time = time.time()
    ny_people = graph.find_nodes(city="New York")
    query_time = time.time() - start_time
    print(f"✓ Found {len(ny_people)} people in New York in {query_time:.6f}s")
    
    # 6. Traversal operations
    print("\n6. Traversal operations...")
    
    # Alice's friends
    alice_friends = graph.neighbors_out("alice", rel="friends")
    print(f"Alice's friends: {[graph.get_node(friend_id)['name'] for friend_id, _ in alice_friends]}")
    
    # Shortest path
    bob_to_charlie = graph.traversal_ops.shortest_path("bob", "charlie")
    if bob_to_charlie:
        print(f"Shortest path Bob → Charlie: {' → '.join(bob_to_charlie)}")
    
    # 7. Subgraph views
    print("\n7. Subgraph views...")
    
    # Create subgraph of people in New York
    ny_view = graph.create_subgraph_view(
        "new_york",
        lambda nid, attrs: attrs.get("city") == "New York"
    )
    print(f"New York subgraph: {ny_view.node_count} nodes, {ny_view.edge_count} edges")
    print(f"Connected: {ny_view.is_connected()}")
    
    # 8. Performance statistics
    print("\n8. Performance statistics...")
    stats = graph.stats()
    print("Graph Statistics:")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")
    
    # 9. Save and load
    print("\n9. Persistence...")
    
    # Save graph
    save_file = "examples/social_network.msgpack"
    graph.save(save_file)
    file_size = Path(save_file).stat().st_size
    print(f"✓ Saved graph to {save_file} ({file_size:,} bytes)")
    
    # Load graph
    loaded_graph = FastGraph("loaded_network")
    loaded_graph.load(save_file)
    print(f"✓ Loaded graph: {len(loaded_graph.graph['nodes'])} nodes, {len(loaded_graph._edges)} edges")
    
    # Verify data integrity
    original_alice = graph.get_node("alice")
    loaded_alice = loaded_graph.get_node("alice")
    print(f"✓ Data integrity check: {'PASS' if original_alice == loaded_alice else 'FAIL'}")
    
    # 10. Memory usage
    print("\n10. Memory analysis...")
    from fastgraph.utils.memory import get_global_memory_utils
    memory_utils = get_global_memory_utils()
    
    memory_estimate = memory_utils.estimate_graph_memory(graph)
    print("Memory Usage Estimate:")
    for component, size_bytes in memory_estimate.items():
        if component != "total":
            size_mb = size_bytes / (1024 * 1024)
            print(f"  {component}: {size_mb:.2f} MB")
    
    total_mb = memory_estimate["total"] / (1024 * 1024)
    print(f"  Total: {total_mb:.2f} MB")
    
    print("\n✨ Example completed successfully!")
    print("\nNext steps:")
    print("- Try the config_example.py to see configuration management")
    print("- Use the CLI: fastgraph --help")
    print("- Check the documentation for advanced features")


if __name__ == "__main__":
    main()
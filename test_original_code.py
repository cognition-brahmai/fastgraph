#!/usr/bin/env python3
"""
Test the exact original failing code snippet to demonstrate the fix.
"""

from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    from fastgraph import FastGraph

    print("Running the original failing code snippet...")
    print("=" * 50)
    with TemporaryDirectory(prefix="fastgraph-original-") as directory:
        graph = FastGraph("my_graph", config={"storage": {"data_dir": directory}})
        graph.add_node("alice", name="Alice", age=30, type="Person")
        graph.add_node("bob", name="Bob", age=25, type="Person")
        graph.add_node("company", name="TechCorp", type="Company")

        graph.add_edge("alice", "bob", "friends", since=2021)
        graph.add_edge("alice", "company", "works_at", role="Engineer")
        graph.add_edge("bob", "company", "works_at", role="Manager")

        people = graph.find_nodes(type="Person")
        print(len(people))
        friends = graph.neighbors_out("alice", rel="friends")
        print([node for node, edge in friends])

        # Keep the manual reproduction outside the caller's working directory.
        graph.save(Path(directory) / "my_graph.json", format="json")
        graph.close()
        print("The save completed without TypeError.")


if __name__ == "__main__":
    main()

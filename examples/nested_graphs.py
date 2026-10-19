"""Compound nodes stay ordinary nodes until traversal enters their child scope."""

from fastgraph import FastGraph


def main():
    with FastGraph("nested-demo") as graph:
        graph.add_node("company", kind="organization")
        graph.add_node("customer", kind="person")

        company = graph["company"].graph
        company.add_node("engineering", kind="department")
        company.add_node("sales", kind="department")
        company.add_edge("engineering", "sales", "collaborates")

        engineering = company["engineering"].graph
        alice = engineering.add_node("alice", kind="person")
        bob = engineering.add_node("bob", kind="person")
        engineering.add_edge(alice, bob, "mentors")

        # This is one store: a relationship can cross a graph boundary explicitly.
        graph.add_edge("customer", alice, "works_with")

        flat = graph.bfs("company")
        nested = graph.bfs("company", nested=True)
        print("Parent-only traversal:", [node.path for node in flat.nodes])
        print("Nested traversal:", [node.path for node in nested.nodes])
        print("Qualified selection:", graph.resolve(("company", "engineering", "alice")))
        print(
            "Forward cross-scope path:",
            [
                node.path
                for node in graph.shortest_path("customer", ("company", "engineering", "bob"))
            ],
        )
        print("All person nodes:", graph.find_nodes(recursive=True, kind="person"))


if __name__ == "__main__":
    main()

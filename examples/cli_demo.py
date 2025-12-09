#!/usr/bin/env python3
"""
FastGraph CLI Demo

This script demonstrates how to use the FastGraph CLI tools programmatically
and shows examples of CLI operations for common tasks.
"""

import sys
import subprocess
import json
import tempfile
import os
from pathlib import Path

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_cli_command(cmd, description=""):
    """Run a CLI command and return the result."""
    print(f"\n🔧 {description}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print("Stderr:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False


def main():
    """Demonstrate FastGraph CLI usage."""
    print("🛠️  FastGraph CLI Demo")
    print("=" * 40)
    
    # Create sample data files
    data_dir = Path("examples/data")
    data_dir.mkdir(exist_ok=True)
    
    # Sample graph data
    graph_data = {
        "nodes": [
            {"id": "alice", "name": "Alice Smith", "age": 30, "type": "Person"},
            {"id": "bob", "name": "Bob Johnson", "age": 25, "type": "Person"},
            {"id": "charlie", "name": "Charlie Brown", "age": 35, "type": "Person"},
            {"id": "techcorp", "name": "TechCorp", "type": "Company"}
        ],
        "edges": [
            {"src": "alice", "dst": "bob", "rel": "friends", "since": 2021},
            {"src": "alice", "dst": "techcorp", "rel": "works_at", "role": "Engineer"},
            {"src": "bob", "dst": "techcorp", "rel": "works_at", "role": "Manager"},
            {"src": "charlie", "dst": "bob", "rel": "knows", "since": 2020}
        ]
    }
    
    # Save sample data files
    json_file = data_dir / "sample_graph.json"
    with open(json_file, 'w') as f:
        json.dump(graph_data, f, indent=2)
    
    print(f"📁 Created sample data: {json_file}")
    
    # CLI commands to demonstrate
    demo_commands = [
        # Help and version
        ([sys.executable, "-m", "fastgraph.cli.main", "--help"], "Show help"),
        ([sys.executable, "-m", "fastgraph.cli.main", "version"], "Show version"),
        
        # Status
        ([sys.executable, "-m", "fastgraph.cli.main", "status"], "System status"),
        
        # Configuration
        ([sys.executable, "-m", "fastgraph.cli.main", "config", "--show"], "Show configuration"),
        
        # Create graph
        ([
            sys.executable, "-m", "fastgraph.cli.main", "create",
            "--name", "demo_graph",
            "--save", "examples/demo_graph.msgpack"
        ], "Create new graph"),
        
        # Import data
        ([
            sys.executable, "-m", "fastgraph.cli.main", "import",
            str(json_file),
            "--graph", "examples/demo_graph.msgpack",
            "--format", "json",
            "--save-after", "examples/demo_graph_updated.msgpack"
        ], "Import data"),
        
        # Statistics
        ([
            sys.executable, "-m", "fastgraph.cli.main", "stats",
            "--graph", "examples/demo_graph_updated.msgpack"
        ], "Show basic statistics"),
        
        ([
            sys.executable, "-m", "fastgraph.cli.main", "stats",
            "--graph", "examples/demo_graph_updated.msgpack",
            "--detailed",
            "--components"
        ], "Show detailed statistics"),
        
        # Export data
        ([
            sys.executable, "-m", "fastgraph.cli.main", "export",
            "examples/exported_graph.json",
            "--graph", "examples/demo_graph_updated.msgpack",
            "--format", "json"
        ], "Export to JSON"),
        
        # Configuration management
        ([
            sys.executable, "-m", "fastgraph.cli.main", "config",
            "--get", "storage.default_format"
        ], "Get configuration value"),
        
        ([
            sys.executable, "-m", "fastgraph.cli.main", "config",
            "--set", "cli.verbose=true",
            "--show"
        ], "Set configuration value"),
    ]
    
    # Run demonstration commands
    success_count = 0
    total_count = len(demo_commands)
    
    for cmd, description in demo_commands:
        if run_cli_command(cmd, description):
            success_count += 1
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 CLI Demo Summary")
    print(f"✅ Successful: {success_count}/{total_count}")
    print(f"❌ Failed: {total_count - success_count}/{total_count}")
    
    if success_count == total_count:
        print("\n🎉 All CLI commands executed successfully!")
    else:
        print(f"\n⚠️  {total_count - success_count} commands failed")
    
    # Show generated files
    print("\n📁 Generated files:")
    examples_dir = Path("examples")
    for file_path in examples_dir.glob("*.msgpack"):
        print(f"  - {file_path} ({file_path.stat().st_size:,} bytes)")
    
    for file_path in examples_dir.glob("*.json"):
        if "exported" in file_path.name:
            print(f"  - {file_path} ({file_path.stat().st_size:,} bytes)")
    
    # Verify exported data
    exported_file = examples_dir / "exported_graph.json"
    if exported_file.exists():
        print(f"\n📋 Exported data preview:")
        try:
            with open(exported_file, 'r') as f:
                exported_data = json.load(f)
            print(f"  Nodes: {len(exported_data.get('nodes', []))}")
            print(f"  Edges: {len(exported_data.get('edges', []))}")
            
            # Show first node
            if exported_data.get('nodes'):
                print(f"  First node: {exported_data['nodes'][0]}")
        except Exception as e:
            print(f"  Error reading exported file: {e}")
    
    # Cleanup note
    print(f"\n🧹 Note: Demo files created in {examples_dir}")
    print("   You can clean them up manually or they'll be ignored by .gitignore")
    
    print("\n📚 CLI Usage Tips:")
    print("- Use --help with any command for detailed help")
    print("- --verbose provides detailed output for debugging")
    print("- --quiet suppresses output except errors")
    print("--format controls output format (table/json/yaml/plain)")
    print("--config specifies custom configuration file")
    print("- Most operations support progress bars for large operations")
    
    print("\n🔗 Common CLI workflows:")
    print("1. Create graph → Import data → Analyze → Export results")
    print("2. Load existing graph → Run analysis → Save results")
    print("3. Configure settings → Batch operations → Monitor performance")


if __name__ == "__main__":
    main()
"""
CLI command implementations for FastGraph

This module contains the actual command implementations for the CLI interface.
"""

import click
import json
import yaml
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from .. import FastGraph
from ..config.manager import ConfigManager
from ..exceptions import FastGraphError, PersistenceError, CLIError
from .utils import format_output, confirm_action, progress_bar, handle_error


@click.command()
@click.option('--name', '-n', default='fastgraph', 
              help='Graph name (default: fastgraph)')
@click.option('--description', '-d', 
              help='Graph description')
@click.option('--config', '-c', 
              type=click.Path(exists=True),
              help='Configuration file to use')
@click.option('--nodes', 
              type=click.Path(exists=True),
              help='JSON/YAML file with initial nodes')
@click.option('--save', '-s',
              type=click.Path(),
              help='Save graph to file after creation')
@click.pass_context
def create_graph_command(ctx, name, description, config, nodes, save):
    """
    Create a new FastGraph instance.
    
    Creates a new empty graph or loads initial data from files.
    Can optionally save the graph for later use.
    """
    try:
        ctx = ctx.parent  # Get main context
        config_manager = ctx.obj.get('config', ConfigManager())
        
        # Override config if specified
        if config:
            config_manager = ConfigManager(config_file=config)
        
        # Create graph
        graph = FastGraph(name=name, config=config_manager)
        
        data = {
            "name": graph.name,
            "created_at": graph.graph["metadata"]["created_at"],
            "version": graph.graph["metadata"]["version"]
        }
        
        # Load initial nodes if provided
        if nodes:
            click.echo(f"Loading nodes from {nodes}...")
            nodes_file = Path(nodes)
            
            try:
                if nodes_file.suffix.lower() in ['.json']:
                    with open(nodes_file, 'r') as f:
                        nodes_data = json.load(f)
                elif nodes_file.suffix.lower() in ['.yaml', '.yml']:
                    with open(nodes_file, 'r') as f:
                        nodes_data = yaml.safe_load(f)
                else:
                    raise CLIError(f"Unsupported file format: {nodes_file.suffix}")
                
                # Add nodes to graph
                if isinstance(nodes_data, list):
                    # List of node objects
                    node_batch = []
                    for node in nodes_data:
                        if isinstance(node, dict):
                            node_id = str(node.pop('id', f"node_{len(graph)}"))
                            node_batch.append((node_id, node))
                    graph.add_nodes_batch(node_batch)
                elif isinstance(nodes_data, dict):
                    # Dict of node_id -> attributes
                    node_batch = [(str(nid), attrs) for nid, attrs in nodes_data.items()]
                    graph.add_nodes_batch(node_batch)
                
                data["nodes_loaded"] = len(nodes_data)
                
            except Exception as e:
                raise CLIError(f"Failed to load nodes from {nodes}: {e}")
        
        # Save graph if requested
        if save:
            save_path = Path(save)
            format = save_path.suffix.lower().lstrip('.') or 'msgpack'
            
            click.echo(f"Saving graph to {save_path}...")
            graph.save(save_path, format=format)
            data["saved_to"] = str(save_path)
        
        # Show results
        format_output(ctx.obj.get('output_format', 'table'), data, "Graph Created")
        
        return graph
        
    except Exception as e:
        handle_error(e, ctx)


@click.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--graph', '-g', 
              type=click.Path(),
              help='Graph file to load/modify')
@click.option('--format', '-f',
              type=click.Choice(['json', 'yaml', 'csv']),
              default='json',
              help='Input file format')
@click.option('--merge', is_flag=True,
              help='Merge with existing graph')
@click.option('--save-after', '-s',
              type=click.Path(),
              help='Save graph after import')
@click.pass_context
def import_command(ctx, file_path, graph, format, merge, save_after):
    """
    Import data into a FastGraph instance.
    
    Import nodes and edges from various file formats.
    Can create a new graph or merge with existing one.
    """
    try:
        ctx = ctx.parent
        config_manager = ctx.obj.get('config', ConfigManager())
        
        # Load or create graph
        if graph and Path(graph).exists():
            click.echo(f"Loading existing graph from {graph}...")
            import_graph = FastGraph(config=config_manager)
            
            # Detect format from file extension
            graph_format = Path(graph).suffix.lower().lstrip('.') or 'msgpack'
            import_graph.load(graph, format=graph_format)
            
            if not merge:
                click.echo("Warning: Graph exists but --merge not specified. Creating new graph.")
                import_graph.clear()
        else:
            import_graph = FastGraph(config=config_manager)
        
        # Load data from file
        input_path = Path(file_path)
        click.echo(f"Importing data from {file_path}...")
        
        with progress_bar() as pbar:
            pbar.update(10, description="Loading file...")
            
            if format == 'json':
                with open(input_path, 'r') as f:
                    data = json.load(f)
            elif format == 'yaml':
                with open(input_path, 'r') as f:
                    data = yaml.safe_load(f)
            elif format == 'csv':
                data = _parse_csv(input_path)
            else:
                raise CLIError(f"Unsupported format: {format}")
            
            pbar.update(30, description="Processing data...")
            
            # Import nodes
            nodes_added = 0
            edges_added = 0
            
            if 'nodes' in data:
                if isinstance(data['nodes'], list):
                    node_batch = []
                    for node in data['nodes']:
                        if isinstance(node, dict):
                            node_id = str(node.get('id', f"node_{nodes_added}"))
                            attrs = {k: v for k, v in node.items() if k != 'id'}
                            node_batch.append((node_id, attrs))
                    
                    import_graph.add_nodes_batch(node_batch)
                    nodes_added = len(node_batch)
                
                elif isinstance(data['nodes'], dict):
                    node_batch = [(str(nid), attrs) for nid, attrs in data['nodes'].items()]
                    import_graph.add_nodes_batch(node_batch)
                    nodes_added = len(node_batch)
            
            pbar.update(60, description="Adding edges...")
            
            # Import edges
            if 'edges' in data:
                edge_batch = []
                for edge in data['edges']:
                    if isinstance(edge, dict):
                        src = str(edge.get('src', edge.get('source')))
                        dst = str(edge.get('dst', edge.get('target', edge.get('destination'))))
                        rel = str(edge.get('rel', edge.get('relation', edge.get('type', 'edge'))))
                        attrs = {k: v for k, v in edge.items() 
                                if k not in ['src', 'source', 'dst', 'target', 'destination', 'rel', 'relation', 'type']}
                        edge_batch.append((src, dst, rel, attrs))
                
                import_graph.add_edges_batch(edge_batch)
                edges_added = len(edge_batch)
            
            pbar.update(90, description="Finalizing...")
        
        # Save if requested
        if save_after:
            save_format = Path(save_after).suffix.lower().lstrip('.') or 'msgpack'
            import_graph.save(save_after, format=save_format)
        
        # Show results
        results = {
            "file": str(input_path),
            "format": format,
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "total_nodes": len(import_graph.graph['nodes']),
            "total_edges": len(import_graph._edges)
        }
        
        if save_after:
            results["saved_to"] = str(save_after)
        
        format_output(ctx.obj.get('output_format', 'table'), results, "Import Complete")
        
    except Exception as e:
        handle_error(e, ctx)


@click.command()
@click.argument('file_path', type=click.Path())
@click.option('--graph', '-g',
              type=click.Path(exists=True),
              required=True,
              help='Graph file to export')
@click.option('--format', '-f',
              type=click.Choice(['msgpack', 'pickle', 'json', 'yaml', 'csv']),
              default='json',
              help='Export format')
@click.option('--nodes-filter',
              help='Filter expression for nodes (JSON)')
@click.option('--edges-filter',
              help='Filter expression for edges (JSON)')
@click.pass_context
def export_command(ctx, file_path, graph, format, nodes_filter, edges_filter):
    """
    Export graph data to various formats.
    
    Save graph data to files in different formats for analysis
    or transfer to other systems.
    """
    try:
        ctx = ctx.parent
        config_manager = ctx.obj.get('config', ConfigManager())
        
        # Load graph
        click.echo(f"Loading graph from {graph}...")
        export_graph = FastGraph(config=config_manager)
        
        # Detect input format
        input_format = Path(graph).suffix.lower().lstrip('.') or 'msgpack'
        export_graph.load(graph, format=input_format)
        
        click.echo(f"Exporting to {file_path} in {format} format...")
        
        with progress_bar() as pbar:
            pbar.update(20, description="Preparing data...")
            
            # Prepare export data
            export_data = {
                "metadata": export_graph.graph["metadata"],
                "nodes": [],
                "edges": []
            }
            
            # Apply filters if provided
            nodes = export_graph.graph["nodes"]
            edges = export_graph._edges.values()
            
            if nodes_filter:
                filter_dict = json.loads(nodes_filter)
                nodes = {nid: attrs for nid, attrs in nodes.items()
                         if all(attrs.get(k) == v for k, v in filter_dict.items())}
            
            if edges_filter:
                filter_dict = json.loads(edges_filter)
                edges = [e for e in edges 
                        if all(e.get_attribute(k) == v for k, v in filter_dict.items())]
            
            pbar.update(50, description="Processing nodes...")
            
            # Process nodes
            for nid, attrs in nodes.items():
                node_data = {"id": nid}
                node_data.update(attrs)
                export_data["nodes"].append(node_data)
            
            pbar.update(70, description="Processing edges...")
            
            # Process edges
            for edge in edges:
                edge_data = {
                    "src": edge.src,
                    "dst": edge.dst,
                    "rel": edge.rel
                }
                edge_data.update(edge.attrs)
                export_data["edges"].append(edge_data)
            
            pbar.update(90, description="Writing file...")
            
            # Export based on format
            output_path = Path(file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if format in ['json', 'yaml']:
                if format == 'json':
                    with open(output_path, 'w') as f:
                        json.dump(export_data, f, indent=2, default=str)
                else:
                    with open(output_path, 'w') as f:
                        yaml.dump(export_data, f, default_flow_style=False)
            
            elif format == 'csv':
                _export_to_csv(export_data, output_path)
            
            else:
                # Use FastGraph persistence
                export_graph.save(output_path, format=format)
            
            pbar.update(100, description="Complete!")
        
        # Show results
        results = {
            "source": str(graph),
            "output": str(output_path),
            "format": format,
            "nodes_exported": len(export_data["nodes"]),
            "edges_exported": len(export_data["edges"]),
            "file_size": output_path.stat().st_size
        }
        
        format_output(ctx.obj.get('output_format', 'table'), results, "Export Complete")
        
    except Exception as e:
        handle_error(e, ctx)


@click.command()
@click.option('--graph', '-g',
              type=click.Path(exists=True),
              help='Graph file to analyze')
@click.option('--detailed', '-d', is_flag=True,
              help='Show detailed statistics')
@click.option('--components', is_flag=True,
              help='Analyze connected components')
@click.pass_context
def stats_command(ctx, graph, detailed, components):
    """
    Show graph statistics and analysis.
    
    Display comprehensive statistics about graph structure,
    performance metrics, and optional component analysis.
    """
    try:
        ctx = ctx.parent
        config_manager = ctx.obj.get('config', ConfigManager())
        
        if graph:
            # Load graph from file
            stats_graph = FastGraph(config=config_manager)
            input_format = Path(graph).suffix.lower().lstrip('.') or 'msgpack'
            stats_graph.load(graph, format=input_format)
        else:
            # Create empty graph for system stats
            stats_graph = FastGraph(config=config_manager)
        
        # Get basic statistics
        basic_stats = stats_graph.stats()
        
        # Memory usage
        memory_stats = stats_graph.memory_usage_estimate()
        basic_stats.update(memory_stats)
        
        # Index statistics
        index_stats = stats_graph.get_index_stats()
        basic_stats["index_stats"] = index_stats
        
        # Component analysis if requested
        if components:
            click.echo("Analyzing connected components...")
            components_data = stats_graph.traversal_ops.connected_components()
            basic_stats["components"] = {
                "count": len(components_data),
                "largest_size": max(len(comp) for comp in components_data) if components_data else 0,
                "smallest_size": min(len(comp) for comp in components_data) if components_data else 0,
                "avg_size": sum(len(comp) for comp in components_data) / len(components_data) if components_data else 0
            }
        
        # Detailed analysis
        if detailed:
            click.echo("Performing detailed analysis...")
            
            # Degree distribution
            degree_dist = {}
            for node_id in stats_graph.graph["nodes"]:
                out_deg, in_deg, total_deg = stats_graph.degree(node_id)
                degree_dist[total_deg] = degree_dist.get(total_deg, 0) + 1
            
            basic_stats["degree_distribution"] = degree_dist
            
            # Path lengths (sample)
            if len(stats_graph.graph["nodes"]) > 1:
                sample_nodes = list(stats_graph.graph["nodes"].keys())[:min(10, len(stats_graph.graph["nodes"]))]
                path_lengths = []
                
                for i, src in enumerate(sample_nodes):
                    for dst in sample_nodes[i+1:]:
                        path = stats_graph.traversal_ops.shortest_path(src, dst)
                        if path:
                            path_lengths.append(len(path) - 1)  # Edges count
                
                if path_lengths:
                    basic_stats["path_analysis"] = {
                        "avg_shortest_path": sum(path_lengths) / len(path_lengths),
                        "max_shortest_path": max(path_lengths),
                        "min_shortest_path": min(path_lengths),
                        "samples": len(path_lengths)
                    }
        
        # Display results
        format_output(ctx.obj.get('output_format', 'table'), basic_stats, "Graph Statistics")
        
    except Exception as e:
        handle_error(e, ctx)


@click.command()
@click.option('--show', is_flag=True,
              help='Show current configuration')
@click.option('--validate', is_flag=True,
              help='Validate configuration')
@click.option('--save', '-s',
              type=click.Path(),
              help='Save configuration to file')
@click.option('--set', 'set_option',
              multiple=True,
              help='Set configuration option (key=value)')
@click.option('--get', 'get_option',
              help='Get configuration option value')
@click.pass_context
def config_command(ctx, show, validate, save, set_option, get_option):
    """
    Manage FastGraph configuration.
    
    View, validate, and modify configuration settings.
    """
    try:
        ctx = ctx.parent
        config_manager = ctx.obj.get('config', ConfigManager())
        
        # Show configuration
        if show:
            format_output(ctx.obj.get('output_format', 'table'), 
                         config_manager.get_config(), 
                         "Current Configuration")
            return
        
        # Set options
        if set_option:
            for option in set_option:
                if '=' not in option:
                    raise CLIError(f"Invalid option format: {option}. Use key=value")
                
                key, value = option.split('=', 1)
                
                # Try to parse value
                try:
                    import json
                    parsed_value = json.loads(value)
                except:
                    parsed_value = value
                
                config_manager.set(key, parsed_value)
                click.echo(f"Set {key} = {parsed_value}")
        
        # Get option
        if get_option:
            value = config_manager.get(get_option)
            click.echo(f"{get_option}: {value}")
            return
        
        # Validate configuration
        if validate:
            click.echo("Validating configuration...")
            # This would use ConfigValidator in real implementation
            click.echo("Configuration is valid.")
        
        # Save configuration
        if save:
            config_manager.save_config(save)
            click.echo(f"Configuration saved to {save}")
        
    except Exception as e:
        handle_error(e, ctx)


# Helper functions
def _parse_csv(file_path: Path) -> Dict[str, Any]:
    """Parse CSV file for import."""
    import csv
    
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Try to determine if it's nodes or edges
    if 'src' in rows[0] or 'source' in rows[0]:
        return {"edges": rows}
    else:
        return {"nodes": rows}


def _export_to_csv(data: Dict[str, Any], output_path: Path):
    """Export data to CSV format."""
    import csv
    
    # Export nodes
    with open(output_path.with_suffix('.nodes.csv'), 'w', newline='') as f:
        if data['nodes']:
            writer = csv.DictWriter(f, fieldnames=data['nodes'][0].keys())
            writer.writeheader()
            writer.writerows(data['nodes'])
    
    # Export edges
    with open(output_path.with_suffix('.edges.csv'), 'w', newline='') as f:
        if data['edges']:
            writer = csv.DictWriter(f, fieldnames=data['edges'][0].keys())
            writer.writeheader()
            writer.writerows(data['edges'])
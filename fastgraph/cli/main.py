"""
Main CLI entry point for FastGraph

This module provides the main CLI interface using Click framework.
"""

import click
import sys
import os
from pathlib import Path
from typing import Optional

from ..config.manager import load_config, ConfigManager
from ..exceptions import FastGraphError, CLIError, ConfigurationError
from .commands import (
    create_graph_command,
    import_command,
    export_command,
    stats_command,
    config_command
)
from .utils import setup_logging, format_output, handle_error


@click.group()
@click.option('--config', '-c', 
              type=click.Path(exists=True), 
              help='Configuration file path')
@click.option('--verbose', '-v', 
              is_flag=True, 
              help='Enable verbose output')
@click.option('--quiet', '-q', 
              is_flag=True, 
              help='Suppress output except errors')
@click.option('--format', 'output_format', 
              type=click.Choice(['table', 'json', 'yaml', 'plain']),
              default='table',
              help='Output format')
@click.option('--log-file', 
              type=click.Path(),
              help='Log file path')
@click.pass_context
def main(ctx, config, verbose, quiet, output_format, log_file):
    """
    FastGraph CLI - High-Performance Graph Database Command Line Tool
    
    This command-line interface provides tools for managing graph databases,
    importing/exporting data, and analyzing graph structures.
    
    Global options:
    \b
    -c, --config PATH  Configuration file path
    -v, --verbose      Enable verbose output
    -q, --quiet        Suppress output except errors
    --format FORMAT    Output format (table/json/yaml/plain)
    --log-file PATH    Log file path
    """
    # Ensure context exists
    ctx.ensure_object(dict)
    
    # Store global options in context
    ctx.obj['config_file'] = config
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet
    ctx.obj['output_format'] = output_format
    ctx.obj['log_file'] = log_file
    
    # Setup logging
    try:
        log_level = 'DEBUG' if verbose else ('WARNING' if quiet else 'INFO')
        setup_logging(log_level, log_file)
    except Exception as e:
        click.echo(f"Warning: Failed to setup logging: {e}", err=True)
    
    # Load configuration
    try:
        if config:
            ctx.obj['config'] = load_config(config_file=config)
        else:
            # Try to find default config
            ctx.obj['config'] = ConfigManager()
    except ConfigurationError as e:
        click.echo(f"Configuration error: {e}", err=True)
        if not quiet:
            click.echo("Using default configuration.", err=True)
        ctx.obj['config'] = ConfigManager(validate=False)
    except Exception as e:
        click.echo(f"Warning: Failed to load configuration: {e}", err=True)
        ctx.obj['config'] = ConfigManager(validate=False)
    
    # Set console output level
    if quiet:
        ctx.obj['console_output'] = False
    else:
        ctx.obj['console_output'] = True


@main.command()
@click.option('--version', is_flag=True, help='Show version information')
@click.pass_context
def help(ctx, version):
    """Show help information."""
    if version:
        from .. import __version__, __description__
        click.echo(f"FastGraph v{__version__}")
        click.echo(__description__)
        click.echo()
        click.echo("License: MIT")
        click.echo("Website: https://github.com/fastgraph/fastgraph")
        return
    
    # Show main help
    click.echo(main.get_help(ctx))


@main.command()
@click.pass_context
def version(ctx):
    """Show version information."""
    from .. import __version__, __description__
    
    data = {
        "version": __version__,
        "description": __description__,
        "python_version": sys.version,
        "platform": sys.platform
    }
    
    format_output(ctx.obj.get('output_format', 'table'), data, "Version Information")


@main.command()
@click.pass_context
def status(ctx):
    """Show FastGraph system status."""
    try:
        config = ctx.obj['config']
        
        # System information
        data = {
            "fastgraph_version": "2.0.0",
            "python_version": sys.version,
            "platform": sys.platform,
            "config_file": ctx.obj.get('config_file', 'default'),
            "log_level": "DEBUG" if ctx.obj.get('verbose') else "INFO"
        }
        
        # Configuration status
        data["configuration"] = {
            "storage_format": config.get("storage.default_format"),
            "cache_enabled": config.get("memory.query_cache_size", 0) > 0,
            "auto_index": config.get("indexing.auto_index"),
            "data_directory": config.get("storage.data_dir")
        }
        
        # Test if we can create a graph
        try:
            from .. import FastGraph
            test_graph = FastGraph("test", config=config)
            data["graph_creation"] = "OK"
            test_graph.clear()  # Clean up
        except Exception as e:
            data["graph_creation"] = f"ERROR: {e}"
        
        format_output(ctx.obj.get('output_format', 'table'), data, "System Status")
        
    except Exception as e:
        handle_error(e, ctx)


# Add command groups
main.add_command(create_graph_command, name='create')
main.add_command(import_command, name='import')
main.add_command(export_command, name='export')
main.add_command(stats_command, name='stats')
main.add_command(config_command, name='config')


# Error handling
def cli_error_handler(func):
    """Decorator for CLI error handling."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            click.echo("\nOperation cancelled by user.", err=True)
            sys.exit(1)
        except FastGraphError as e:
            handle_error(e, kwargs.get('ctx'))
            sys.exit(1)
        except Exception as e:
            handle_error(e, kwargs.get('ctx'))
            sys.exit(1)
    return wrapper


# Apply error handling to all commands
for command in main.commands.values():
    command.callback = cli_error_handler(command.callback)


# Entry point for script execution
def run_cli():
    """Run the CLI application."""
    try:
        main()
    except Exception as e:
        # Last resort error handling
        click.echo(f"Fatal error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    run_cli()
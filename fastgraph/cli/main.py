"""Command-line tools for the embedded native graph engine."""

import sys
from pathlib import Path

import click

from .. import FastGraph, __description__, __version__
from ..config.manager import ConfigManager
from .commands import (
    config_command,
    create_graph_command,
    export_command,
    import_command,
    nested_command,
    query_command,
    stats_command,
)
from .utils import cli_errors, emit


@click.group()
@click.version_option(version=__version__, prog_name="FastGraph")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON or YAML configuration file.",
)
@click.option("--verbose", "-v", is_flag=True, help="Expose tracebacks for command failures.")
@click.option("--quiet", "-q", is_flag=True, help="Suppress successful command output.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "yaml", "plain"]),
    default="table",
    show_default=True,
    help="Console output format.",
)
@click.pass_context
@cli_errors
def main(ctx, config, verbose, quiet, output_format):
    """Create, inspect and convert local FastGraph snapshots."""
    ctx.ensure_object(dict)
    ctx.obj.update(verbose=verbose, quiet=quiet, output_format=output_format, config_file=config)
    ctx.obj["config"] = ConfigManager(config_file=config)


@main.command()
@click.pass_context
def version(ctx):
    """Show the actual runtime version."""
    emit(
        ctx,
        {
            "version": __version__,
            "description": __description__,
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
        },
        "Version",
    )


@main.command(name="help")
@click.option("--version", "show_version", is_flag=True)
@click.pass_context
def help_command(ctx, show_version):
    """Show command help or version information."""
    if show_version:
        ctx.invoke(version)
    else:
        click.echo(main.get_help(ctx.parent))


@main.command()
@click.pass_context
@cli_errors
def status(ctx):
    """Inspect the local engine and configuration, not a network service."""
    graph = FastGraph(config=ctx.obj["config"])
    try:
        emit(
            ctx,
            {
                "version": __version__,
                "backend": graph.stats()["backend"],
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
                "configuration": graph.config.get_config(),
            },
            "Local Engine",
        )
    finally:
        graph.close()


main.add_command(create_graph_command, name="create")
main.add_command(import_command, name="import")
main.add_command(export_command, name="export")
main.add_command(stats_command, name="stats")
main.add_command(config_command, name="config")
main.add_command(query_command, name="query")
main.add_command(nested_command, name="nested")


def run_cli():
    main()


if __name__ == "__main__":
    run_cli()

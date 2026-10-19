"""Small Click output and error helpers."""

from functools import wraps
import json

import click
import yaml


def cli_errors(function):
    """Translate command failures to Click's nonzero error exit."""

    @wraps(function)
    def callback(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except click.ClickException:
            raise
        except Exception as error:
            context = click.get_current_context(silent=True)
            if context and context.obj and context.obj.get("verbose"):
                raise
            raise click.ClickException(str(error)) from error

    return callback


def format_output(output_format, data, title=None):
    if output_format == "json":
        click.echo(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2))
    elif output_format in {"yaml", "table"}:
        # Normalize tuple paths to arrays, without emitting Python-specific YAML tags.
        values = json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))
        if title and output_format == "table":
            click.echo(title)
        click.echo(yaml.safe_dump(values, allow_unicode=True, sort_keys=False), nl=False)
    elif output_format == "plain":
        click.echo(str(data))
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def emit(context, data, title=None):
    if not context.obj.get("quiet"):
        format_output(context.obj["output_format"], data, title)

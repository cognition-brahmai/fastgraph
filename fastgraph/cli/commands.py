"""CLI operations using the public graph and safe persistence APIs."""

import json
from pathlib import Path

import click

from .. import FastGraph
from ..config.manager import ConfigManager
from .utils import cli_errors, emit


_INPUT = click.Path(exists=True, dir_okay=False, path_type=Path)
_OUTPUT = click.Path(dir_okay=False, path_type=Path)
_FORMATS = click.Choice(["json", "msgpack"])


def _snapshot_format(path, requested=None):
    suffixes = path.suffixes
    if suffixes and suffixes[-1].lower() == ".gz":
        suffixes = suffixes[:-1]
    suffix = suffixes[-1].lower() if suffixes else ""
    if suffix in {".pickle", ".pkl"}:
        raise click.ClickException("Pickle is unsupported; use JSON or MessagePack snapshots.")
    if requested is not None:
        return requested
    if suffix == ".json":
        return "json"
    if suffix in {".msgpack", ".mpk"}:
        return "msgpack"
    if suffix:
        raise click.ClickException(
            f"Unsupported snapshot suffix {suffix}; specify json or msgpack."
        )
    return None


def _save(graph, path, format=None, compress=False):
    selected = _snapshot_format(path, format) or graph.config.get(
        "storage.default_format", "msgpack"
    )
    return graph.save(path, format=selected, compress=compress or path.suffix.lower() == ".gz")


def _load(ctx, path, format=None):
    return FastGraph.from_file(
        path, format=_snapshot_format(path, format), config=ctx.obj["config"]
    )


def _read_json(path, config):
    def unique_object(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError(f"Duplicate JSON object key: {key}")
            values[key] = value
        return values

    def reject_constant(value):
        raise ValueError(f"Non-finite JSON numbers are unsupported: {value}")

    limit = config.get("persistence.max_bytes", 256 * 1024 * 1024)
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise click.ClickException(f"JSON input exceeds max_bytes={limit}")
    return json.loads(payload, object_pairs_hook=unique_object, parse_constant=reject_constant)


def _node_batch(data):
    if isinstance(data, dict):
        batch = list(data.items())
    elif isinstance(data, list):
        batch = []
        for node in data:
            if not isinstance(node, dict) or "id" not in node:
                raise click.ClickException("Node records require an id and object properties.")
            if "attrs" in node:
                if set(node) - {"id", "attrs"}:
                    raise click.ClickException(
                        "Put node properties inside attrs or beside id, not both."
                    )
                attrs = node["attrs"]
            else:
                attrs = {key: value for key, value in node.items() if key != "id"}
            batch.append((node["id"], attrs))
    else:
        raise click.ClickException("Nodes must be an id-to-properties object or a list of records.")
    if any(
        not isinstance(node_id, str) or not node_id or not isinstance(attrs, dict)
        for node_id, attrs in batch
    ):
        raise click.ClickException(
            "Node IDs must be nonempty strings and properties must be objects."
        )
    return batch


@click.command()
@click.option("--name", "-n", default="fastgraph", show_default=True)
@click.option("--config", "-c", type=_INPUT, help="Override the global configuration file.")
@click.option("--nodes", type=_INPUT, help="Initial nodes in a JSON object or record list.")
@click.option("--save", "-s", type=_OUTPUT, help="Save the created graph to this path.")
@click.option(
    "--format", "-f", type=_FORMATS, help="Snapshot format; otherwise inferred from the path."
)
@click.option("--compress", is_flag=True, help="Gzip the saved snapshot (.gz also enables gzip).")
@click.pass_context
@cli_errors
def create_graph_command(ctx, name, config, nodes, save, format, compress):
    """Create a graph, optionally populated from JSON nodes."""
    configuration = ConfigManager(config_file=config) if config else ctx.obj["config"]
    graph = FastGraph(name=name, config=configuration)
    try:
        if nodes:
            if nodes.suffix.lower() != ".json":
                raise click.ClickException("Initial nodes must be a JSON file.")
            graph.add_nodes_batch(_node_batch(_read_json(nodes, configuration)))
        data = graph.stats()
        if save:
            data["saved_to"] = str(_save(graph, save, format, compress))
        emit(ctx, data, "Graph Created")
    finally:
        graph.close()


@click.command()
@click.argument("file_path", type=_INPUT)
@click.option("--name", "-n", help="Name for a flat JSON import.")
@click.option(
    "--format", "-f", type=_FORMATS, help="Input format; otherwise inferred from the path."
)
@click.option(
    "--save-after", "--save", "-s", type=_OUTPUT, help="Save the imported graph to this path."
)
@click.option("--compress", is_flag=True, help="Gzip the output snapshot.")
@click.pass_context
@cli_errors
def import_command(ctx, file_path, name, format, save_after, compress):
    """Import a full snapshot or flat JSON nodes/edges into a new graph.

    Full snapshots preserve their name, properties, indexes and scope hierarchy.
    Flat JSON accepts nodes as an object or id records and edges with src/dst/rel.
    """
    selected = _snapshot_format(file_path, format)
    flat = None
    if selected == "json" and file_path.suffix.lower() != ".gz":
        data = _read_json(file_path, ctx.obj["config"])
        if isinstance(data, dict) and "format" not in data and "version" not in data:
            flat = data
    if flat is None:
        graph = _load(ctx, file_path, format)
    else:
        if not ({"nodes", "edges"} & set(flat)) or set(flat) - {"nodes", "edges", "metadata"}:
            raise click.ClickException(
                "Flat JSON requires nodes and/or edges, with optional metadata."
            )
        metadata = flat.get("metadata", {})
        if not isinstance(metadata, dict):
            raise click.ClickException("Flat JSON metadata must be an object.")
        nodes = _node_batch(flat.get("nodes", {}))
        records = flat.get("edges", [])
        if not isinstance(records, list):
            raise click.ClickException("Edges must be a list of src/dst/rel records.")
        edges = []
        for edge in records:
            if not isinstance(edge, dict) or any(
                not isinstance(edge.get(key), str) or not edge[key] for key in ("src", "dst", "rel")
            ):
                raise click.ClickException("Edges require nonempty string src, dst and rel fields.")
            if "attrs" in edge:
                if set(edge) - {"src", "dst", "rel", "attrs"}:
                    raise click.ClickException(
                        "Put edge properties inside attrs or beside rel, not both."
                    )
                attrs = edge["attrs"]
            else:
                attrs = {
                    key: value for key, value in edge.items() if key not in {"src", "dst", "rel"}
                }
            if not isinstance(attrs, dict):
                raise click.ClickException("Edge properties must be objects.")
            edges.append((edge["src"], edge["dst"], edge["rel"], attrs))
        graph = FastGraph(name=name or metadata.get("name", "fastgraph"), config=ctx.obj["config"])
        try:
            graph.add_nodes_batch(nodes)
            graph.add_edges_batch(edges)
        except Exception:
            graph.close()
            raise
    try:
        result = graph.stats(recursive=True)
        result["source"] = str(file_path)
        if save_after:
            result["saved_to"] = str(_save(graph, save_after, compress=compress))
        emit(ctx, result, "Graph Imported")
    finally:
        graph.close()


@click.command()
@click.argument("file_path", type=_OUTPUT)
@click.option("--graph", "-g", type=_INPUT, required=True, help="Input snapshot.")
@click.option("--format", "-f", type=_FORMATS, default="json", show_default=True)
@click.option("--compress", is_flag=True, help="Gzip the exported snapshot.")
@click.pass_context
@cli_errors
def export_command(ctx, file_path, graph, format, compress):
    """Export the complete graph, including its nested hierarchy."""
    loaded = _load(ctx, graph)
    try:
        result = loaded.stats(recursive=True)
        result.update(
            source=str(graph), output=str(_save(loaded, file_path, format, compress)), format=format
        )
        emit(ctx, result, "Graph Exported")
    finally:
        loaded.close()


@click.command()
@click.option(
    "--graph", "-g", type=_INPUT, help="Snapshot to inspect; otherwise inspect an empty graph."
)
@click.option(
    "--detailed", "-d", is_flag=True, help="Include components and native memory estimates."
)
@click.option("--recursive", is_flag=True, help="Include all descendant scopes.")
@click.pass_context
@cli_errors
def stats_command(ctx, graph, detailed, recursive):
    """Show actual graph statistics; detailed analysis is opt-in."""
    loaded = _load(ctx, graph) if graph else FastGraph(config=ctx.obj["config"])
    try:
        emit(ctx, loaded.stats(recursive=recursive, detailed=detailed), "Graph Statistics")
    finally:
        loaded.close()


@click.command()
@click.argument("graph", type=_INPUT)
@click.option(
    "--where", default="{}", show_default=True, help="JSON property filters, e.g. age__gte."
)
@click.option("--recursive", is_flag=True, help="Return absolute paths from all descendant scopes.")
@click.option("--limit", type=click.IntRange(min=1), help="Maximum number of matching nodes.")
@click.pass_context
@cli_errors
def query_command(ctx, graph, where, recursive, limit):
    """List matching nodes; JSON output represents qualified paths as arrays."""
    filters = json.loads(where)
    if not isinstance(filters, dict):
        raise click.BadParameter(
            "Expected a JSON object of property filters.", param_hint="--where"
        )
    if set(filters) & {"recursive", "limit"}:
        raise click.BadParameter(
            "recursive and limit are query options, not filter keys.", param_hint="--where"
        )
    loaded = _load(ctx, graph)
    try:
        nodes = [
            {"path" if recursive else "id": key, "attrs": attrs}
            for key, attrs in loaded.find_nodes(recursive=recursive, limit=limit, **filters)
        ]
        emit(ctx, {"nodes": nodes, "count": len(nodes)}, "Query Results")
    finally:
        loaded.close()


@click.command()
@click.argument("graph", type=_INPUT)
@click.pass_context
@cli_errors
def nested_command(ctx, graph):
    """Inspect the versioned native snapshot of the whole scope hierarchy."""
    loaded = _load(ctx, graph)
    try:
        emit(ctx, loaded.snapshot(), "Nested Snapshot")
    finally:
        loaded.close()


@click.command()
@click.option("--show", is_flag=True, help="Show the complete configuration.")
@click.option("--validate", is_flag=True, help="Run the actual configuration validator.")
@click.option("--save", "-s", type=_OUTPUT, help="Save configuration as JSON or YAML.")
@click.option("--set", "set_option", multiple=True, help="Set a dotted configuration key=value.")
@click.option("--get", "get_option", help="Read a dotted configuration key.")
@click.pass_context
@cli_errors
def config_command(ctx, show, validate, save, set_option, get_option):
    """Read, validate and explicitly save configuration."""
    configuration = ctx.obj["config"]
    updates = {}
    for option in set_option:
        if "=" not in option:
            raise click.BadParameter("Use key=value.", param_hint="--set")
        key, value = option.split("=", 1)
        if not key or any(not part for part in key.split(".")):
            raise click.BadParameter("A nonempty dotted key is required.", param_hint="--set")
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
        configuration.set(key, value)
        updates[key] = value
    if updates or validate or save:
        configuration = ConfigManager(config_dict=configuration.get_config())
    result = (
        configuration.get_config()
        if show or not (validate or save or updates or get_option)
        else {}
    )
    if updates:
        result["updated"] = updates
    if get_option:
        missing = object()
        value = configuration.get(get_option, missing)
        if value is missing:
            raise click.BadParameter(f"Unknown configuration key: {get_option}", param_hint="--get")
        result[get_option] = value
    if validate:
        result["valid"] = True
    if save:
        if save.suffix.lower() not in {".json", ".yaml", ".yml"}:
            raise click.BadParameter(
                "Configuration files must be JSON or YAML.", param_hint="--save"
            )
        save.parent.mkdir(parents=True, exist_ok=True)
        configuration.save_config(save)
        result["saved_to"] = str(save)
    emit(ctx, result, "Configuration")

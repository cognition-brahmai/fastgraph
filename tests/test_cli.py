"""Real CLI regressions in isolated filesystems, without native mocks."""

import gzip
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from fastgraph import FastGraph, __version__
from fastgraph.cli.main import main


@pytest.fixture
def runner(monkeypatch):
    cli = CliRunner()
    with cli.isolated_filesystem():
        directory = str(Path.cwd())
        monkeypatch.setenv("HOME", directory)
        monkeypatch.setenv("USERPROFILE", directory)
        monkeypatch.setenv("FASTGRAPH_DATA_DIR", str(Path.cwd() / "storage"))
        monkeypatch.delenv("FASTGRAPH_DEFAULT_FORMAT", raising=False)
        yield cli


def _json(runner, arguments):
    result = runner.invoke(main, ["--format", "json", *arguments])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _nested_graph(path):
    graph = FastGraph("nested-cli")
    graph.add_nodes_batch(
        [("company", {"kind": "Organization"}), ("alice", {"kind": "Person", "age": 52})]
    )
    child = graph["company"].graph
    child.add_nodes_batch(
        [
            ("alice", {"kind": "Person", "age": 31}),
            ("bob", {"kind": "Person", "age": 20}),
            ("team", {"kind": "Team"}),
        ]
    )
    child["team"].graph.add_node("alice", kind="Person", age=40)
    child.add_edge("alice", "bob", "KNOWS", attrs={"src": "property"})
    graph.add_edge(graph["alice"], child["alice"], "MENTORS")
    child.build_node_index("kind")
    snapshot = graph.snapshot()
    graph.save(path)
    graph.close()
    return snapshot


def test_help_and_runtime_version(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for command in ("create", "import", "export", "stats", "config", "query", "nested"):
        assert command in result.output
    assert _json(runner, ["version"])["version"] == __version__
    assert __version__ in runner.invoke(main, ["--version"]).output
    assert runner.invoke(main, ["help"]).exit_code == 0
    assert runner.invoke(main, ["help", "--version"]).exit_code == 0


def test_status_reports_native_engine_without_service_claims(runner):
    status = _json(runner, ["status"])
    assert status["version"] == __version__
    assert status["backend"] == "rust"
    assert "server" not in status
    assert not Path("storage").exists()


@pytest.mark.parametrize("suffix", ["json", "msgpack", "json.gz", "msgpack.gz"])
def test_create_documented_arguments_and_safe_formats(runner, suffix):
    path = Path(f"graph.{suffix}")
    created = _json(runner, ["create", "--name", "cli-created", "--save", str(path)])
    assert created["name"] == "cli-created"
    assert created["nodes"] == 0
    assert path.is_file()
    if suffix.endswith(".gz"):
        assert gzip.decompress(path.read_bytes())
    graph = FastGraph.from_file(path)
    try:
        assert graph.name == "cli-created"
        assert graph.stats()["nodes"] == 0
    finally:
        graph.close()


@pytest.mark.parametrize(
    "nodes",
    [
        {"a": {"name": "Alice"}, "b": {"id": "property"}},
        [{"id": "a", "name": "Alice"}, {"id": "b", "attrs": {"id": "property"}}],
    ],
)
def test_create_batches_initial_nodes_without_losing_reserved_properties(runner, nodes):
    Path("nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    created = _json(runner, ["create", "--nodes", "nodes.json", "--save", "graph.json"])
    assert created["nodes"] == 2
    graph = FastGraph.from_file("graph.json")
    try:
        assert graph.get_node("a") == {"name": "Alice"}
        assert graph.get_node("b") == {"id": "property"}
    finally:
        graph.close()


def test_import_flat_json_and_batch_edges(runner):
    data = {
        "metadata": {"name": "imported"},
        "nodes": {"a": {"kind": "Person"}, "b": {}},
        "edges": [
            {"src": "a", "dst": "b", "rel": "KNOWS", "attrs": {"src": "property", "weight": 2}}
        ],
    }
    Path("data.json").write_text(json.dumps(data), encoding="utf-8")
    imported = _json(runner, ["import", "data.json", "--save-after", "graph.msgpack"])
    assert imported["nodes"] == 2
    assert imported["edges"] == 1
    graph = FastGraph.from_file("graph.msgpack")
    try:
        assert graph.name == "imported"
        assert graph.get_edge("a", "b", "KNOWS").attrs == {"src": "property", "weight": 2}
    finally:
        graph.close()


@pytest.mark.parametrize("format", ["json", "msgpack"])
def test_import_and_export_keep_entire_native_hierarchy(runner, format):
    original = _nested_graph("nested.msgpack")
    imported = _json(runner, ["import", "nested.msgpack", "--save", "imported.json"])
    assert imported["nodes"] == 6
    assert imported["edges"] == 2
    output = f"export.{format}.gz"
    _json(runner, ["export", output, "--graph", "imported.json", "--format", format])
    graph = FastGraph.from_file(output)
    try:
        assert graph.snapshot() == original
        assert graph.resolve(("company", "team", "alice")).attrs["age"] == 40
        assert graph["company"].graph.get_edge("alice", "bob", "KNOWS").attrs == {
            "attrs": {"src": "property"}
        }
    finally:
        graph.close()


def test_nested_stats_and_query_paths_are_json_arrays(runner):
    original = _nested_graph("nested.json")
    assert _json(runner, ["stats", "--graph", "nested.json"])["nodes"] == 2
    stats = _json(runner, ["stats", "--graph", "nested.json", "--recursive", "--detailed"])
    assert stats["nodes"] == 6
    assert stats["edges"] == 2
    assert "memory" in stats
    assert _json(runner, ["nested", "nested.json"]) == original

    query = _json(
        runner,
        ["query", "nested.json", "--where", '{"kind":"Person","age__gte":30}', "--recursive"],
    )
    paths = [node["path"] for node in query["nodes"]]
    assert paths == [["alice"], ["company", "alice"], ["company", "team", "alice"]]
    limited = _json(runner, ["query", "nested.json", "--recursive", "--limit", "1"])
    assert limited["count"] == 1
    assert isinstance(limited["nodes"][0]["path"], list)
    local = _json(runner, ["query", "nested.json", "--where", '{"kind":"Person"}'])
    assert [node["id"] for node in local["nodes"]] == ["alice"]


def test_yaml_paths_are_safe_arrays(runner):
    _nested_graph("nested.json")
    result = runner.invoke(main, ["--format", "yaml", "query", "nested.json", "--recursive"])
    assert result.exit_code == 0, result.output
    output = yaml.safe_load(result.output)
    assert output["nodes"][0]["path"] == ["company"]


def test_config_validates_changes_and_saves_only_when_requested(runner):
    changed = _json(
        runner,
        [
            "config",
            "--set",
            "storage.default_format=json",
            "--validate",
            "--get",
            "storage.default_format",
            "--save",
            "settings/config.json",
        ],
    )
    assert changed["valid"] is True
    assert changed["storage.default_format"] == "json"
    assert (
        json.loads(Path("settings/config.json").read_text())["storage"]["default_format"] == "json"
    )
    loaded = _json(
        runner, ["--config", "settings/config.json", "config", "--get", "storage.default_format"]
    )
    assert loaded["storage.default_format"] == "json"
    assert not Path("storage").exists()


def test_config_saves_validated_value_types(runner):
    changed = _json(
        runner,
        [
            "config",
            "--set",
            "persistence.max_bytes=64.0",
            "--validate",
            "--get",
            "persistence.max_bytes",
            "--save",
            "config.json",
        ],
    )
    assert type(changed["persistence.max_bytes"]) is int
    persisted = json.loads(Path("config.json").read_text())
    assert type(persisted["persistence"]["max_bytes"]) is int


def test_quiet_suppresses_success_but_not_errors(runner):
    result = runner.invoke(main, ["--quiet", "create", "--save", "graph.json"])
    assert result.exit_code == 0
    assert result.output == ""
    result = runner.invoke(main, ["--quiet", "stats", "--graph", "missing.json"])
    assert result.exit_code != 0
    assert "Error" in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        ["create", "--save", "graph.pickle"],
        ["create", "--save", "graph.xyz"],
        ["create", "--save", "graph.json", "--format", "pickle"],
        ["create", "--save", "graph.json", "--format", "unknown"],
        ["export", "output.pickle", "--graph", "nested.json", "--format", "json"],
        ["export", "output.json", "--graph", "nested.json", "--format", "pickle"],
        ["export", "output.json", "--graph", "missing.json", "--format", "json"],
        ["import", "missing.json"],
        ["stats", "--graph", "missing.json"],
        ["query", "missing.json"],
        ["query", "nested.json", "--where", "[]"],
        ["query", "nested.json", "--where", "not-json"],
        ["query", "nested.json", "--where", '{"age__unknown":2}'],
        ["query", "nested.json", "--limit", "0"],
        ["query", "nested.json", "--where", '{"recursive":true}'],
        ["nested", "missing.json"],
        ["stats", "--graph", "bad.json"],
        ["import", "bad.json"],
        ["import", "graph.pickle"],
        ["config", "--set", "no-equals"],
        ["config", "--set", "=empty"],
        ["config", "--set", "storage.default_format=pickle", "--validate"],
        ["config", "--get", "unknown.key"],
        ["config", "--save", "settings.pickle"],
        ["--config", "bad.json", "version"],
    ],
)
def test_cli_errors_exit_nonzero_and_do_not_write_outputs(runner, arguments):
    _nested_graph("nested.json")
    Path("bad.json").write_text("not JSON", encoding="utf-8")
    Path("graph.pickle").write_bytes(b"\x80\x04N.")
    original = Path("graph.pickle").read_bytes()
    result = runner.invoke(main, arguments)
    assert result.exit_code != 0, result.output
    assert "Error" in result.output
    assert not Path("output.json").exists()
    assert not Path("output.pickle").exists()
    assert not Path("graph.xyz").exists()
    assert not Path("graph.json").exists()
    assert Path("graph.pickle").read_bytes() == original


@pytest.mark.parametrize(
    "data",
    [
        {"nodes": ["not a record"]},
        {"nodes": {"a": "not properties"}},
        {"nodes": [{"id": "a", "attrs": {}, "mixed": True}]},
        {"nodes": {"a": {}}, "edges": [{"src": "a", "dst": "missing", "rel": "r"}]},
        {"nodes": {}, "edges": [{"src": "a", "dst": "b"}]},
        {"nodes": {}, "edges": [{"src": "a", "dst": "b", "rel": "r", "attrs": []}]},
        {"nodes": {}, "edges": "not records"},
    ],
)
def test_malformed_flat_import_does_not_publish_a_partial_graph(runner, data):
    Path("input.json").write_text(json.dumps(data), encoding="utf-8")
    result = runner.invoke(main, ["import", "input.json", "--save", "output.json"])
    assert result.exit_code != 0, result.output
    assert not Path("output.json").exists()


@pytest.mark.parametrize(
    "contents",
    [
        '{"nodes":{"a":{},"a":{"overwritten":true}}}',
        '{"nodes":{"a":{"value":NaN}}}',
        '{"nodes":{"a":{"value":Infinity}}}',
    ],
)
def test_flat_json_rejects_ambiguous_keys_and_nonfinite_values(runner, contents):
    Path("input.json").write_text(contents, encoding="utf-8")
    result = runner.invoke(main, ["import", "input.json", "--save", "output.json"])
    assert result.exit_code != 0, result.output
    assert not Path("output.json").exists()


def test_flat_json_import_honors_configured_read_limit(runner):
    Path("config.json").write_text('{"persistence":{"max_bytes":32}}', encoding="utf-8")
    Path("input.json").write_text(
        json.dumps({"nodes": {"large": {"value": "x" * 64}}}), encoding="utf-8"
    )
    result = runner.invoke(
        main, ["--config", "config.json", "import", "input.json", "--save", "output.json"]
    )
    assert result.exit_code != 0, result.output
    assert "max_bytes=32" in result.output
    assert not Path("output.json").exists()


def test_legacy_demo_collection_cannot_overwrite_cwd_file(runner):
    demo = Path(__file__).resolve().parents[1] / "test_original_code.py"
    if not demo.exists():
        pytest.skip("Legacy demo is not part of the copied installed-package suite")
    sentinel = Path("my_graph.json")
    sentinel.write_bytes(b"existing user data")
    spec = importlib.util.spec_from_file_location("fastgraph_legacy_demo_guard", demo)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sentinel.read_bytes() == b"existing user data"
    assert callable(module.main)

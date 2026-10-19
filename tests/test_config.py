"""Only supported configuration knobs influence the embedded facade."""

import json

import pytest

from fastgraph import ConfigManager, FastGraph, PersistenceError, ValidationError


def test_configuration_snapshots_do_not_escape_mutable_nested_state():
    config = ConfigManager()
    snapshot = config.get_config()
    snapshot["storage"]["default_format"] = "pickle"
    assert config.get("storage.default_format") == "msgpack"
    with pytest.raises(ValidationError):
        ConfigManager(config_dict={"storage": {"default_format": "pickle"}})


def test_configured_read_size_limit_applies_and_explicit_override_wins(tmp_path):
    source = FastGraph("source")
    source.add_node("payload", value="x" * 2048)
    path = source.save(tmp_path / "graph.json")
    target = FastGraph("target", config={"persistence": {"max_bytes": 1024}})
    target.add_node("original")
    with pytest.raises(PersistenceError, match="max_bytes"):
        target.load(path)
    assert target.node_ids() == ("original",)
    target.load(path, max_bytes=10000)
    assert target.node_ids() == ("payload",)


def test_configured_durable_flag_and_explicit_override(tmp_path, monkeypatch):
    from fastgraph.core import persistence

    calls = []
    monkeypatch.setattr(persistence.os, "fsync", lambda fd: calls.append(fd))
    graph = FastGraph(config={"persistence": {"durable": False}})
    graph.add_node("n")
    graph.save(tmp_path / "graph.json")
    assert calls == []
    graph.save(tmp_path / "graph.json", durable=True)
    assert calls


def test_default_save_path_is_explicitly_configured_and_does_not_redirect(tmp_path):
    graph = FastGraph(
        "named", config={"storage": {"data_dir": str(tmp_path), "default_format": "json"}}
    )
    graph.add_node("n")
    path = graph.save()
    assert path == tmp_path / "named.json"
    assert json.loads(path.read_text())["format"] == "fastgraph"
    assert graph.exists()


def test_translation_honors_configured_limit_before_writing_target(tmp_path):
    source = FastGraph()
    source.add_node("n", value="x" * 2048)
    path = source.save(tmp_path / "source.json")
    graph = FastGraph(config={"persistence": {"max_bytes": 1000}})
    with pytest.raises(PersistenceError, match="max_bytes"):
        graph.translate(path, tmp_path / "target.msgpack")
    assert not (tmp_path / "target.msgpack").exists()

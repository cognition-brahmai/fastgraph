"""Native imports, public metadata, and the command entry point stay aligned."""

from importlib import metadata
from pathlib import Path

import fastgraph
from fastgraph import FastGraph, _native


def test_runtime_and_distribution_versions_match():
    assert metadata.version("fastgx") == fastgraph.__version__ == "3.0.0"
    assert FastGraph().stats()["backend"] == "rust"


def test_extension_is_a_compiled_module_not_a_python_fallback():
    assert Path(_native.__file__).suffix.lower() in {".so", ".pyd", ".dll"}
    assert _native.NativeStore.__module__ == "fastgraph._native"


def test_console_script_points_to_the_actual_click_entrypoint():
    distribution = metadata.distribution("fastgx")
    assert any(
        entry.group == "console_scripts"
        and entry.name == "fastgraph"
        and entry.value == "fastgraph.cli.main:main"
        for entry in distribution.entry_points
    )

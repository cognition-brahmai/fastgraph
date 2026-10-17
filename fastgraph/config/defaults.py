"""Defaults for the embedded engine; no hidden workers or network services."""

from pathlib import Path


def get_default_config() -> dict:
    return {
        "engine": {"name": "fastgraph", "version": "3.0.0"},
        "storage": {
            "data_dir": str(Path.home() / ".fastgraph" / "graphs"),
            "default_format": "msgpack",
            "backup_directory": str(Path.home() / ".fastgraph" / "backups"),
        },
        "persistence": {
            "max_bytes": 256 * 1024 * 1024,
            "durable": True,
            "auto_save_on_exit": False,
        },
        "enhanced_api": {"auto_save": False},
        "cli": {"default_output_format": "table", "verbose": False},
    }


def get_config_schema() -> dict:
    return {
        "engine": {
            "type": "dict", "required": True,
            "properties": {"name": {"type": "string", "required": True},
                           "version": {"type": "string", "required": True}},
        },
        "storage": {
            "type": "dict", "required": True,
            "properties": {
                "data_dir": {"type": "string", "required": True},
                "default_format": {"type": "string", "enum": ["msgpack", "json"],
                                   "required": True},
                "backup_directory": {"type": "string", "required": True},
            },
        },
        "persistence": {
            "type": "dict", "required": True,
            "properties": {
                "max_bytes": {"type": "integer", "min": 1},
                "durable": {"type": "boolean"},
                "auto_save_on_exit": {"type": "boolean"},
            },
        },
        "enhanced_api": {
            "type": "dict", "properties": {"auto_save": {"type": "boolean"}},
        },
        "cli": {
            "type": "dict", "properties": {
                "default_output_format": {"type": "string", "enum": ["table", "json", "yaml", "plain"]},
                "verbose": {"type": "boolean"},
            },
        },
    }


def get_env_config_mapping() -> dict[str, str]:
    return {"FASTGRAPH_DATA_DIR": "storage.data_dir",
            "FASTGRAPH_DEFAULT_FORMAT": "storage.default_format"}


def get_user_config_paths() -> list[Path]:
    home = Path.home()
    return [home / ".fastgraph" / "config.yaml", home / ".fastgraph" / "config.yml",
            home / ".fastgraph" / "config.json", Path.cwd() / "fastgraph.yaml",
            Path.cwd() / "fastgraph.yml"]

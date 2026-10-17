"""Versioned JSON/MessagePack snapshots with bounded reads and atomic publication."""

from __future__ import annotations

import errno
import gzip
import io
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Optional

import msgpack

from ..exceptions import PersistenceError


DEFAULT_MAX_BYTES = 256 * 1024 * 1024
_FORMATS = frozenset({"json", "msgpack"})
_ENVELOPE_KEYS = frozenset({"format", "version", "metadata", "store"})
_SUFFIX_FORMATS = {".json": "json", ".msgpack": "msgpack", ".mpk": "msgpack"}


def _normalize_format(format: str) -> str:
    if not isinstance(format, str) or format.lower() not in _FORMATS:
        raise ValueError("Unsupported snapshot format; use 'json' or 'msgpack' (never pickle)")
    return format.lower()


def _suffix_format(path: Path) -> Optional[str]:
    suffixes = path.suffixes
    if suffixes and suffixes[-1].lower() == ".gz":
        suffixes = suffixes[:-1]
    return _SUFFIX_FORMATS.get(suffixes[-1].lower()) if suffixes else None


def _validate_limit(max_bytes: int) -> None:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")


def _read_bounded(stream: BinaryIO, max_bytes: int, description: str) -> bytes:
    data = bytearray()
    while True:
        chunk = stream.read(min(64 * 1024, max_bytes - len(data) + 1))
        if not chunk:
            return bytes(data)
        if len(data) + len(chunk) > max_bytes:
            raise ValueError(f"Snapshot {description} exceeds max_bytes={max_bytes}")
        data.extend(chunk)


def _read_payload(path: Path, max_bytes: int) -> bytes:
    with path.open("rb") as stream:
        payload = _read_bounded(stream, max_bytes, "input")
    if payload.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            return _read_bounded(stream, max_bytes, "decoded size")
    return payload


def _payload_format(path: Path, payload: bytes) -> str:
    prefix = payload
    if prefix.startswith(b"\xef\xbb\xbf"):
        prefix = prefix[3:]
    prefix = prefix.lstrip(b" \t\r\n")
    if prefix.startswith((b"{", b"[")):
        return "json"
    if payload and (0x80 <= payload[0] <= 0x8F or payload[0] in (0xDE, 0xDF)):
        return "msgpack"
    format = _suffix_format(path)
    if format is None:
        raise ValueError("Cannot detect JSON/MessagePack snapshot format; pickle is unsupported")
    return format


def detect_format(path: Path | str, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """Inspect this file only, or infer a supported suffix for a missing path."""
    try:
        path = Path(path)
        _validate_limit(max_bytes)
        if path.is_file():
            return _payload_format(path, _read_payload(path, max_bytes))
        format = _suffix_format(path)
        if format is None:
            raise ValueError("Cannot detect snapshot format; use a .json or .msgpack suffix")
        return format
    except Exception as exc:
        raise PersistenceError(
            f"Failed to detect snapshot format: {exc}",
            file_path=str(path), operation="detect_format",
        ) from exc


def _unique_object(pairs: list[tuple[Any, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("Snapshot object keys must be strings")
        if key in result:
            raise ValueError(f"Duplicate snapshot object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is unsupported: {value}")


def _reject_extension(code: int, data: bytes) -> None:
    raise ValueError(f"MessagePack extension values are unsupported (code {code})")


def _validate_json_value(value: Any, active: Optional[set[int]] = None) -> None:
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return
    if kind is float:
        if not math.isfinite(value):
            raise ValueError("Snapshots require finite JSON numbers")
        return
    if kind not in (dict, list):
        raise TypeError(f"Snapshots support JSON values only, not {kind.__name__}")
    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        raise ValueError("Circular snapshot values are unsupported")
    active.add(identity)
    try:
        if kind is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError("Snapshot object keys must be strings")
                _validate_json_value(item, active)
        else:
            for item in value:
                _validate_json_value(item, active)
    finally:
        active.remove(identity)


def _validate_envelope(data: Any) -> None:
    if type(data) is not dict or set(data) != _ENVELOPE_KEYS:
        raise ValueError("Expected a FastGraph envelope with format, version, metadata, and store")
    if data["format"] != "fastgraph":
        raise ValueError("Snapshot envelope format must be 'fastgraph'")
    if type(data["version"]) is not int or data["version"] != 3:
        raise ValueError(f"Unsupported FastGraph snapshot version: {data['version']!r}")
    if type(data["metadata"]) is not dict or type(data["store"]) is not dict:
        raise ValueError("Snapshot metadata and store must be dictionaries")
    _validate_json_value(data)


def _migrate_v2(data: dict) -> dict:
    """Rebuild legacy flat data, not its potentially stale or lossy index postings."""
    _validate_json_value(data)
    version = data.get("version")
    if not (type(version) is int and version == 2 or version == "2.0.0"):
        raise ValueError(f"Unsupported legacy FastGraph snapshot version: {version!r}")
    if set(data) - {"version", "created_at", "nodes", "edges", "metadata", "indexes"}:
        raise ValueError("Unsupported fields in legacy snapshot")
    nodes = data.get("nodes")
    edges = data.get("edges", [])
    metadata = data.get("metadata", {})
    indexes = data.get("indexes", {})
    if type(nodes) is not dict or type(edges) is not list:
        raise ValueError("Legacy nodes must be a dictionary and edges must be a list")
    if type(metadata) is not dict or type(indexes) is not dict:
        raise ValueError("Legacy metadata and indexes must be dictionaries")
    if any(type(properties) is not dict for properties in nodes.values()):
        raise ValueError("Legacy node properties must be dictionaries")
    if any(type(postings) is not dict for postings in indexes.values()):
        raise ValueError("Legacy index postings must be dictionaries")
    for edge in edges:
        if type(edge) is not dict or any(type(edge.get(key)) is not str for key in ("src", "dst", "rel")):
            raise ValueError("Legacy edges require string src, dst, and rel fields")
        if edge["src"] not in nodes or edge["dst"] not in nodes:
            raise ValueError("Legacy edge references a missing node")

    # The local extension import avoids importing the graph facade during migration.
    from .._native import NativeStore

    store = NativeStore()
    node_ids = dict(zip(nodes, store.add_nodes(0, list(nodes.items()))))
    store.add_edges([
        (
            node_ids[edge["src"]], node_ids[edge["dst"]], edge["rel"],
            {key: value for key, value in edge.items() if key not in ("src", "dst", "rel")},
        )
        for edge in edges
    ])
    for property_name in indexes:
        store.create_index(0, property_name)
    metadata = dict(metadata)
    if "created_at" in data:
        metadata.setdefault("created_at", data["created_at"])
    return {
        "format": "fastgraph", "version": 3, "metadata": metadata,
        "store": json.loads(store.snapshot().decode("utf-8")),
    }


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    unsupported = {errno.EINVAL, errno.ENOTSUP}
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        if exc.errno not in unsupported:
            raise
        return
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno not in unsupported:
                raise
    finally:
        os.close(fd)


class PersistenceManager:
    """Persist complete envelopes; callers own synchronization of graph state."""

    detect_format = staticmethod(detect_format)

    def __init__(self, config: Optional[dict] = None, *, lock: Any = None):
        if config is not None and not isinstance(config, dict):
            if lock is not None or not callable(getattr(config, "acquire", None)) or not callable(getattr(config, "release", None)):
                raise TypeError("config must be a dictionary")
            lock, config = config, None
        self.config = dict(config or {})
        self.lock = lock

    def save(
        self, data: dict, path: Path | str, format: str = "msgpack",
        compress: bool = False, durable: bool = True,
    ) -> Path:
        """Encode before touching the destination, then atomically replace it."""
        temporary = None
        try:
            path = Path(path)
            format = _normalize_format(format) if format is not None else _suffix_format(path) or "msgpack"
            if type(compress) is not bool or type(durable) is not bool:
                raise TypeError("compress and durable must be booleans")
            _validate_envelope(data)
            if format == "json":
                payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            else:
                payload = msgpack.packb(data, use_bin_type=True)
            if compress:
                payload = gzip.compress(payload, mtime=0)

            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            try:
                stream = os.fdopen(fd, "wb")
            except Exception:
                os.close(fd)
                raise
            with stream:
                stream.write(payload)
                stream.flush()
                if durable:
                    os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            if durable:
                _fsync_directory(path.parent)
            return path
        except Exception as exc:
            raise PersistenceError(
                f"Failed to save graph to {path}: {exc}",
                file_path=str(path), operation="save", format=format,
            ) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def load(
        self, path: Path | str, format: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> dict:
        """Read one bounded, optionally gzipped snapshot without executable codecs."""
        try:
            path = Path(path)
            _validate_limit(max_bytes)
            if format is not None:
                format = _normalize_format(format)
            payload = _read_payload(path, max_bytes)
            if format is None:
                format = _payload_format(path, payload)
            if format == "json":
                data = json.loads(
                    payload.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                    parse_constant=_reject_constant,
                )
            else:
                data = msgpack.unpackb(
                    payload, raw=False, strict_map_key=True,
                    object_pairs_hook=_unique_object, ext_hook=_reject_extension,
                    max_str_len=max_bytes, max_bin_len=max_bytes,
                    max_array_len=max_bytes, max_map_len=max_bytes, max_ext_len=max_bytes,
                )
            if type(data) is dict and "nodes" in data and "store" not in data and "format" not in data:
                data = _migrate_v2(data)
            _validate_envelope(data)
            return data
        except Exception as exc:
            raise PersistenceError(
                f"Failed to load graph from {path}: {exc}",
                file_path=str(path), operation="load", format=format,
            ) from exc

    def translate(
        self, source_path: Path | str, target_path: Path | str,
        source_format: Optional[str] = None, target_format: Optional[str] = None,
        **kwargs: Any,
    ) -> Path:
        """Translate the same full envelope, preserving all opaque native store data."""
        max_bytes = kwargs.pop("max_bytes", DEFAULT_MAX_BYTES)
        data = self.load(source_path, format=source_format, max_bytes=max_bytes)
        format = target_format if target_format is not None else _suffix_format(Path(target_path)) or "msgpack"
        return self.save(data, target_path, format=format, **kwargs)

    def get_supported_formats(self) -> list[str]:
        return sorted(_FORMATS)

"""Detached, immutable-identity relationship results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ..exceptions import ValidationError


@dataclass(frozen=True, slots=True, eq=False)
class Edge:
    """A relationship snapshot; modify stored properties through FastGraph.update_edge."""

    src: str | tuple[str, ...]
    dst: str | tuple[str, ...]
    rel: str
    attrs: Mapping[str, Any] = field(default_factory=dict)
    _id: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.src or not self.dst or not isinstance(self.rel, str) or not self.rel:
            raise ValidationError("Relationship endpoints and type must be nonempty")
        if not isinstance(self.attrs, Mapping):
            raise ValidationError("Relationship properties must be a mapping", field="attrs")
        object.__setattr__(self, "attrs", MappingProxyType(deepcopy(dict(self.attrs))))

    @property
    def id(self) -> int | None:
        return self._id

    def key(self) -> tuple:
        return self.src, self.dst, self.rel

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "rel": self.rel,
                "attrs": deepcopy(dict(self.attrs))}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Edge:
        attrs = data.get("attrs")
        if attrs is None:
            attrs = {k: v for k, v in data.items() if k not in {"src", "dst", "rel"}}
        return cls(data["src"], data["dst"], data["rel"], attrs)

    def copy(self, **changes: Any) -> Edge:
        attrs = deepcopy(dict(self.attrs))
        src = changes.pop("src", self.src)
        dst = changes.pop("dst", self.dst)
        rel = changes.pop("rel", self.rel)
        attrs.update(changes)
        return Edge(src, dst, rel, attrs)

    def reverse(self) -> Edge:
        return Edge(self.dst, self.src, self.rel, self.attrs)

    def has_attribute(self, key: str) -> bool:
        return key in self.attrs

    def get_attribute(self, key: str, default: Any = None) -> Any:
        return deepcopy(self.attrs.get(key, default))

    def __hash__(self) -> int:
        return hash(self.key())

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Edge) and self.key() == other.key()

    def __str__(self) -> str:
        return f"{self.src}-[{self.rel}]->{self.dst}"

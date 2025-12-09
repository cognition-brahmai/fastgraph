"""
Edge dataclass and operations for FastGraph

This module contains the Edge dataclass and edge-related utilities.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

from ..types import NodeId, EdgeAttrs
from ..exceptions import ValidationError


@dataclass
class Edge:
    """
    Edge dataclass representing a directed edge in the graph.
    
    This is a memory-efficient representation of an edge using a dataclass
    instead of a dictionary, providing better performance and type safety.
    """
    src: NodeId
    dst: NodeId
    rel: str
    attrs: EdgeAttrs = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize edge after dataclass creation."""
        # Ensure attrs is a dictionary
        if self.attrs is None:
            self.attrs = {}
        
        # Validate edge data
        self._validate()
    
    def _validate(self) -> None:
        """Validate edge data."""
        if not self.src:
            raise ValidationError("Edge source node ID cannot be empty", field="src", value=self.src)
        
        if not self.dst:
            raise ValidationError("Edge destination node ID cannot be empty", field="dst", value=self.dst)
        
        if not self.rel:
            raise ValidationError("Edge relation cannot be empty", field="rel", value=self.rel)
        
        if not isinstance(self.attrs, dict):
            raise ValidationError("Edge attributes must be a dictionary", field="attrs", value=self.attrs)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert edge to dictionary representation.
        
        Returns:
            Dictionary representation of the edge
        """
        result = {
            "src": self.src,
            "dst": self.dst,
            "rel": self.rel
        }
        result.update(self.attrs)
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Edge':
        """
        Create edge from dictionary representation.
        
        Args:
            data: Dictionary containing edge data
            
        Returns:
            Edge instance
            
        Example:
            Edge.from_dict({
                "src": "A",
                "dst": "B", 
                "rel": "friends",
                "since": 2021
            })
        """
        # Extract core fields
        src = data.pop("src", None)
        dst = data.pop("dst", None)
        rel = data.pop("rel", None)
        
        # Remaining fields become attributes
        attrs = data
        
        return cls(src=src, dst=dst, rel=rel, attrs=attrs)
    
    def copy(self, **changes) -> 'Edge':
        """
        Create a copy of the edge with optional changes.
        
        Args:
            **changes: Field values to change in the copy
            
        Returns:
            New Edge instance with changes applied
            
        Example:
            edge.copy(rel="colleagues")
        """
        # Create new dict from current edge
        data = self.to_dict()
        
        # Apply changes
        for key, value in changes.items():
            if key in ["src", "dst", "rel"]:
                data[key] = value
            else:
                data[key] = value
        
        return self.from_dict(data)
    
    def has_attribute(self, key: str) -> bool:
        """
        Check if edge has a specific attribute.
        
        Args:
            key: Attribute key to check
            
        Returns:
            True if attribute exists, False otherwise
        """
        return key in self.attrs
    
    def get_attribute(self, key: str, default: Any = None) -> Any:
        """
        Get edge attribute value.
        
        Args:
            key: Attribute key
            default: Default value if key doesn't exist
            
        Returns:
            Attribute value or default
        """
        return self.attrs.get(key, default)
    
    def set_attribute(self, key: str, value: Any) -> None:
        """
        Set edge attribute value.
        
        Args:
            key: Attribute key
            value: Attribute value
        """
        self.attrs[key] = value
    
    def remove_attribute(self, key: str) -> Any:
        """
        Remove edge attribute and return its value.
        
        Args:
            key: Attribute key to remove
            
        Returns:
            Removed attribute value or None if key didn't exist
        """
        return self.attrs.pop(key, None)
    
    def update_attributes(self, **attrs: Any) -> None:
        """
        Update multiple edge attributes.
        
        Args:
            **attrs: Attributes to update
        """
        self.attrs.update(attrs)
    
    def key(self) -> tuple:
        """
        Get the unique key for this edge.
        
        Returns:
            Tuple of (src, dst, rel) that uniquely identifies this edge
        """
        return (self.src, self.dst, self.rel)
    
    def reverse(self) -> 'Edge':
        """
        Create a reversed edge (swap src and dst).
        
        Returns:
            New Edge with src and dst swapped
        """
        return Edge(src=self.dst, dst=self.src, rel=self.rel, attrs=self.attrs.copy())
    
    def __str__(self) -> str:
        """String representation of edge."""
        attrs_str = f"[{', '.join(f'{k}={v}' for k, v in self.attrs.items())}]" if self.attrs else ""
        return f"{self.src}-[{self.rel}]->{self.dst}{attrs_str}"
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"Edge(src='{self.src}', dst='{self.dst}', rel='{self.rel}', attrs={self.attrs})"
    
    def __hash__(self) -> int:
        """Hash function for edge."""
        return hash(self.key())
    
    def __eq__(self, other) -> bool:
        """Equality comparison based on key."""
        if not isinstance(other, Edge):
            return False
        return self.key() == other.key()
    
    def __lt__(self, other) -> bool:
        """Less than comparison for sorting."""
        if not isinstance(other, Edge):
            return NotImplemented
        return self.key() < other.key()
    
    def __le__(self, other) -> bool:
        """Less than or equal comparison."""
        if not isinstance(other, Edge):
            return NotImplemented
        return self.key() <= other.key()
    
    def __gt__(self, other) -> bool:
        """Greater than comparison."""
        if not isinstance(other, Edge):
            return NotImplemented
        return self.key() > other.key()
    
    def __ge__(self, other) -> bool:
        """Greater than or equal comparison."""
        if not isinstance(other, Edge):
            return NotImplemented
        return self.key() >= other.key()
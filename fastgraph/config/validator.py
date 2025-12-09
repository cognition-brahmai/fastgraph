"""
Configuration validation for FastGraph

This module provides validation functionality for FastGraph configurations.
"""

import os
import re
from typing import Any, Dict, List, Union
from pathlib import Path

from ..exceptions import ConfigurationError, ValidationError


class ConfigValidator:
    """Validates FastGraph configuration according to schema rules."""
    
    def __init__(self, schema: Dict[str, Any] = None):
        """
        Initialize the validator.
        
        Args:
            schema: Configuration schema to use for validation
        """
        self.schema = schema or {}
    
    def validate(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a configuration dictionary.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Validated configuration (with type conversions applied)
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not isinstance(config, dict):
            raise ConfigurationError("Configuration must be a dictionary")
        
        validated = {}
        
        # Validate each section
        for section_name, section_schema in self.schema.items():
            if section_schema.get("required", False):
                if section_name not in config:
                    raise ConfigurationError(
                        f"Required configuration section '{section_name}' is missing",
                        config_key=section_name
                    )
            
            if section_name in config:
                validated[section_name] = self._validate_section(
                    config[section_name], 
                    section_schema,
                    section_name
                )
            elif section_schema.get("required", False):
                # Add required section with defaults
                validated[section_name] = self._get_section_defaults(section_schema)
        
        # Add any non-required sections that have defaults
        for section_name, section_schema in self.schema.items():
            if section_name not in validated and "default" in section_schema:
                validated[section_name] = section_schema["default"]
        
        return validated
    
    def _validate_section(self, section: Any, schema: Dict[str, Any], section_name: str) -> Any:
        """
        Validate a configuration section.
        
        Args:
            section: Section value to validate
            schema: Section schema
            section_name: Name of the section
            
        Returns:
            Validated section value
            
        Raises:
            ValidationError: If section is invalid
        """
        # Check type
        expected_type = schema.get("type")
        if expected_type:
            if expected_type == "dict" and not isinstance(section, dict):
                raise ValidationError(
                    f"Section '{section_name}' must be a dictionary",
                    field=section_name,
                    value=section
                )
            elif expected_type == "array" and not isinstance(section, list):
                raise ValidationError(
                    f"Section '{section_name}' must be a list",
                    field=section_name,
                    value=section
                )
        
        if isinstance(section, dict):
            validated_section = {}
            
            # Validate properties
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                if prop_name in section:
                    validated_section[prop_name] = self._validate_property(
                        section[prop_name],
                        prop_schema,
                        f"{section_name}.{prop_name}"
                    )
                elif "default" in prop_schema:
                    validated_section[prop_name] = prop_schema["default"]
                elif prop_schema.get("required", False):
                    raise ValidationError(
                        f"Required property '{prop_name}' is missing from section '{section_name}'",
                        field=f"{section_name}.{prop_name}",
                        value=None
                    )
            
            # Check for unknown properties
            unknown_props = set(section.keys()) - set(properties.keys())
            if unknown_props:
                # Allow unknown properties but warn about them
                for prop in unknown_props:
                    validated_section[prop] = section[prop]
            
            return validated_section
        
        elif isinstance(section, list):
            return self._validate_array(section, schema, section_name)
        
        else:
            return self._validate_value(section, schema, section_name)
    
    def _validate_property(self, value: Any, schema: Dict[str, Any], field_path: str) -> Any:
        """
        Validate a property value.
        
        Args:
            value: Value to validate
            schema: Property schema
            field_path: Full field path for error reporting
            
        Returns:
            Validated value (with type conversion if needed)
            
        Raises:
            ValidationError: If value is invalid
        """
        # Type validation and conversion
        value = self._validate_type_conversion(value, schema, field_path)
        
        # Enum validation
        if "enum" in schema:
            if value not in schema["enum"]:
                raise ValidationError(
                    f"Value '{value}' for '{field_path}' must be one of: {schema['enum']}",
                    field=field_path,
                    value=value
                )
        
        # Range validation
        if isinstance(value, (int, float)):
            if "min" in schema and value < schema["min"]:
                raise ValidationError(
                    f"Value '{value}' for '{field_path}' must be >= {schema['min']}",
                    field=field_path,
                    value=value
                )
            if "max" in schema and value > schema["max"]:
                raise ValidationError(
                    f"Value '{value}' for '{field_path}' must be <= {schema['max']}",
                    field=field_path,
                    value=value
                )
        
        # String validation
        if isinstance(value, str):
            if "min_length" in schema and len(value) < schema["min_length"]:
                raise ValidationError(
                    f"String length for '{field_path}' must be >= {schema['min_length']}",
                    field=field_path,
                    value=value
                )
            if "max_length" in schema and len(value) > schema["max_length"]:
                raise ValidationError(
                    f"String length for '{field_path}' must be <= {schema['max_length']}",
                    field=field_path,
                    value=value
                )
        
        # Pattern validation
        if "pattern" in schema and isinstance(value, str):
            if not re.match(schema["pattern"], value):
                raise ValidationError(
                    f"Value '{value}' for '{field_path}' does not match pattern: {schema['pattern']}",
                    field=field_path,
                    value=value
                )
        
        # Path validation
        if schema.get("validate_path", False) and isinstance(value, str):
            self._validate_path(value, field_path)
        
        return value
    
    def _validate_type_conversion(self, value: Any, schema: Dict[str, Any], field_path: str) -> Any:
        """
        Validate and convert type if needed.
        
        Args:
            value: Value to validate/convert
            schema: Property schema
            field_path: Field path for error reporting
            
        Returns:
            Converted value
            
        Raises:
            ValidationError: If type conversion fails
        """
        expected_type = schema.get("type")
        
        if expected_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes", "on"):
                    return True
                elif value.lower() in ("false", "0", "no", "off"):
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
            
            raise ValidationError(
                f"Cannot convert '{value}' to boolean for '{field_path}'",
                field=field_path,
                value=value
            )
        
        elif expected_type == "integer":
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            if isinstance(value, float) and value.is_integer():
                return int(value)
            
            raise ValidationError(
                f"Cannot convert '{value}' to integer for '{field_path}'",
                field=field_path,
                value=value
            )
        
        elif expected_type == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                raise ValidationError(
                    f"Cannot convert '{value}' to float for '{field_path}'",
                    field=field_path,
                    value=value
                )
        
        elif expected_type == "string":
            return str(value)
        
        return value
    
    def _validate_array(self, array: List[Any], schema: Dict[str, Any], field_path: str) -> List[Any]:
        """
        Validate an array.
        
        Args:
            array: Array to validate
            schema: Array schema
            field_path: Field path for error reporting
            
        Returns:
            Validated array
            
        Raises:
            ValidationError: If array is invalid
        """
        if "min_items" in schema and len(array) < schema["min_items"]:
            raise ValidationError(
                f"Array '{field_path}' must have at least {schema['min_items']} items",
                field=field_path,
                value=array
            )
        
        if "max_items" in schema and len(array) > schema["max_items"]:
            raise ValidationError(
                f"Array '{field_path}' must have at most {schema['max_items']} items",
                field=field_path,
                value=array
            )
        
        # Validate array items
        items_schema = schema.get("items", {})
        if items_schema:
            validated_array = []
            for i, item in enumerate(array):
                validated_item = self._validate_property(
                    item,
                    items_schema,
                    f"{field_path}[{i}]"
                )
                validated_array.append(validated_item)
            return validated_array
        
        return array
    
    def _validate_value(self, value: Any, schema: Dict[str, Any], field_path: str) -> Any:
        """
        Validate a simple value.
        
        Args:
            value: Value to validate
            schema: Value schema
            field_path: Field path for error reporting
            
        Returns:
            Validated value
        """
        return self._validate_property(value, schema, field_path)
    
    def _get_section_defaults(self, schema: Dict[str, Any]) -> Any:
        """
        Get default values for a section.
        
        Args:
            schema: Section schema
            
        Returns:
            Default section value
        """
        if "default" in schema:
            return schema["default"]
        
        if schema.get("type") == "dict":
            defaults = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                if "default" in prop_schema:
                    defaults[prop_name] = prop_schema["default"]
            return defaults
        
        return None
    
    def _validate_path(self, path: str, field_path: str) -> None:
        """
        Validate a file system path.
        
        Args:
            path: Path to validate
            field_path: Field path for error reporting
            
        Raises:
            ValidationError: If path is invalid
        """
        try:
            path_obj = Path(path).expanduser()
            
            # Check if parent directory exists or can be created
            if path_obj.parent != path_obj.parent.parent:  # Not root
                if not path_obj.parent.exists():
                    # Try to create parent directory to check if it's possible
                    try:
                        path_obj.parent.mkdir(parents=True, exist_ok=True)
                    except OSError as e:
                        raise ValidationError(
                            f"Cannot create parent directory for path '{path}': {e}",
                            field=field_path,
                            value=path
                        )
        except Exception as e:
            if not isinstance(e, ValidationError):
                raise ValidationError(
                    f"Invalid path '{path}': {e}",
                    field=field_path,
                    value=path
                )
            raise
"""
CLI utility functions for FastGraph

This module contains helper functions for CLI operations including
output formatting, progress bars, logging, and error handling.
"""

import os
import sys
import json
import yaml
import logging
import time
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from contextlib import contextmanager

import click
from ..exceptions import FastGraphError, CLIError


# Color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Setup logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    """
    # Create logger
    logger = logging.getLogger('fastgraph')
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def format_output(output_format: str, data: Any, title: Optional[str] = None) -> None:
    """
    Format and display output data.
    
    Args:
        output_format: Output format (table, json, yaml, plain)
        data: Data to display
        title: Optional title for output
    """
    if title:
        click.echo(f"\n{Colors.BOLD}{title}{Colors.ENDC}")
        click.echo("=" * len(title))
    
    if output_format == 'json':
        click.echo(json.dumps(data, indent=2, default=str))
    
    elif output_format == 'yaml':
        click.echo(yaml.dump(data, default_flow_style=False))
    
    elif output_format == 'table':
        _format_as_table(data)
    
    else:  # plain
        click.echo(str(data))


def _format_as_table(data: Any, indent: int = 0) -> None:
    """
    Format data as a table.
    
    Args:
        data: Data to format
        indent: Indentation level
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                click.echo(f"{'  ' * indent}{Colors.CYAN}{key}{Colors.ENDC}:")
                _format_as_table(value, indent + 1)
            else:
                click.echo(f"{'  ' * indent}{Colors.CYAN}{key}{Colors.ENDC}: {value}")
    
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                click.echo(f"{'  ' * indent}{Colors.GREEN}[{i}]{Colors.ENDC}:")
                _format_as_table(item, indent + 1)
            else:
                click.echo(f"{'  ' * indent}{Colors.GREEN}[{i}]{Colors.ENDC}: {item}")
    
    else:
        click.echo(f"{'  ' * indent}{data}")


def confirm_action(message: str, default: bool = False) -> bool:
    """
    Ask for user confirmation.
    
    Args:
        message: Confirmation message
        default: Default response if user just presses Enter
        
    Returns:
        True if user confirms, False otherwise
    """
    suffix = " [Y/n]" if default else " [y/N]"
    
    try:
        response = click.prompt(f"{message}{suffix}", 
                              type=bool, 
                              default=default, 
                              show_default=True)
        return response
    except click.Abort:
        raise CLIError("Operation cancelled by user")


@contextmanager
def progress_bar(description: str = "Processing"):
    """
    Simple progress bar context manager.
    
    Args:
        description: Progress description
    """
    start_time = time.time()
    
    # Simple spinning animation
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    spinner_idx = 0
    
    try:
        yield ProgressContext(description, spinner, spinner_idx, start_time)
    finally:
        # Clear progress line
        if sys.stdout.isatty():
            click.echo("\r" + " " * 80 + "\r", nl=False)


class ProgressContext:
    """Progress context manager."""
    
    def __init__(self, description: str, spinner: List[str], 
                 spinner_idx: int, start_time: float):
        self.description = description
        self.spinner = spinner
        self.spinner_idx = spinner_idx
        self.start_time = start_time
        self.last_update = 0
        self.progress = 0
    
    def update(self, progress: int, description: Optional[str] = None):
        """Update progress."""
        self.progress = progress
        if description:
            self.description = description
        
        if not sys.stdout.isatty():
            return
        
        # Only update every 100ms to avoid flickering
        current_time = time.time()
        if current_time - self.last_update < 0.1:
            return
        
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner)
        elapsed = current_time - self.start_time
        
        # Build progress bar
        bar_length = 30
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        # Status line
        status = f"\r{self.spinner[self.spinner_idx]} {self.description}: {bar} {progress}% ({elapsed:.1f}s)"
        click.echo(status, nl=False)
        
        self.last_update = current_time
    
    def finish(self):
        """Finish progress."""
        if sys.stdout.isatty():
            elapsed = time.time() - self.start_time
            click.echo(f"\r✓ {self.description}: Complete ({elapsed:.1f}s)")


def handle_error(error: Exception, ctx: Optional[Any] = None) -> None:
    """
    Handle and display errors appropriately.
    
    Args:
        error: Exception to handle
        ctx: Click context (optional)
    """
    if isinstance(error, FastGraphError):
        click.echo(f"{Colors.FAIL}Error: {error.message}{Colors.ENDC}", err=True)
        
        if error.details:
            for key, value in error.details.items():
                click.echo(f"  {key}: {value}", err=True)
    
    elif isinstance(error, KeyboardInterrupt):
        click.echo(f"{Colors.WARNING}Operation cancelled by user{Colors.ENDC}", err=True)
    
    else:
        click.echo(f"{Colors.FAIL}Unexpected error: {str(error)}{Colors.ENDC}", err=True)
    
    # Debug information if verbose mode
    if ctx and ctx.obj.get('verbose'):
        import traceback
        click.echo(f"\n{Colors.FAIL}Traceback:{Colors.ENDC}", err=True)
        traceback.print_exc()


def validate_file_path(path: Union[str, Path], 
                      must_exist: bool = True, 
                      file_type: Optional[str] = None) -> Path:
    """
    Validate file path for CLI operations.
    
    Args:
        path: File path to validate
        must_exist: Whether file must exist
        file_type: Expected file type (optional)
        
    Returns:
        Validated Path object
        
    Raises:
        CLIError: If validation fails
    """
    path_obj = Path(path)
    
    if must_exist and not path_obj.exists():
        raise CLIError(f"File does not exist: {path}")
    
    if not must_exist and path_obj.exists():
        if not confirm_action(f"File {path} already exists. Overwrite?"):
            raise CLIError("Operation cancelled")
    
    if file_type and path_obj.suffix.lower().lstrip('.') != file_type:
        raise CLIError(f"Expected {file_type} file, got: {path_obj.suffix}")
    
    return path_obj


def parse_key_value_pairs(pairs: List[str]) -> Dict[str, Any]:
    """
    Parse key=value pairs from command line.
    
    Args:
        pairs: List of "key=value" strings
        
    Returns:
        Dictionary of parsed values
        
    Raises:
        CLIError: If parsing fails
    """
    result = {}
    
    for pair in pairs:
        if '=' not in pair:
            raise CLIError(f"Invalid key-value pair: {pair}. Use key=value format")
        
        key, value = pair.split('=', 1)
        
        # Try to parse as JSON for complex values
        try:
            parsed_value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_value = value
        
        result[key] = parsed_value
    
    return result


def merge_configs(config1: Dict[str, Any], config2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two configuration dictionaries.
    
    Args:
        config1: Base configuration
        config2: Override configuration
        
    Returns:
        Merged configuration
    """
    result = config1.copy()
    
    for key, value in config2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


def format_size(bytes_size: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 1:
        return f"{seconds*1000:.0f} ms"
    elif seconds < 60:
        return f"{seconds:.1f} s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} min"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} h"


def detect_file_format(file_path: Path) -> str:
    """
    Detect file format from file extension and content.
    
    Args:
        file_path: Path to file
        
    Returns:
        File format string
        
    Raises:
        CLIError: If format cannot be detected
    """
    # Try extension first
    ext = file_path.suffix.lower().lstrip('.')
    
    format_map = {
        'json': 'json',
        'yaml': 'yaml',
        'yml': 'yaml',
        'csv': 'csv',
        'msgpack': 'msgpack',
        'pickle': 'pickle'
    }
    
    if ext in format_map:
        return format_map[ext]
    
    # Try to detect from content
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
            
            if header.startswith(b'{'):
                return 'json'
            elif header.startswith(b'%YAML'):
                return 'yaml'
            elif header.startswith(b'\x89PNG'):
                raise CLIError("PNG files are not supported")
            else:
                return 'msgpack'  # Default fallback
    
    except Exception:
        raise CLIError(f"Cannot detect file format for {file_path}")


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Ensure directory exists for file path.
    
    Args:
        path: File or directory path
        
    Returns:
        Path to directory
    """
    path_obj = Path(path)
    
    if path_obj.suffix:  # It's a file path
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        return path_obj.parent
    else:  # It's a directory path
        path_obj.mkdir(parents=True, exist_ok=True)
        return path_obj


def safe_filename(filename: str) -> str:
    """
    Create a safe filename from input string.
    
    Args:
        filename: Original filename
        
    Returns:
        Safe filename
    """
    import re
    
    # Replace problematic characters
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove control characters
    safe_name = re.sub(r'[\x00-\x1f\x7f]', '', safe_name)
    
    # Limit length
    if len(safe_name) > 255:
        name, ext = Path(safe_name).stem, Path(safe_name).suffix
        safe_name = name[:255-len(ext)] + ext
    
    return safe_name


def get_temp_file(prefix: str = 'fastgraph', suffix: str = '.tmp') -> Path:
    """
    Get a temporary file path.
    
    Args:
        prefix: File prefix
        suffix: File suffix
        
    Returns:
        Path to temporary file
    """
    import tempfile
    
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)  # Close file descriptor
    
    return Path(path)


def cleanup_temp_files(prefix: str = 'fastgraph') -> None:
    """
    Clean up temporary files.
    
    Args:
        prefix: File prefix to match
    """
    import tempfile
    import glob
    
    temp_dir = Path(tempfile.gettempdir())
    pattern = f"{prefix}*.tmp"
    
    for temp_file in temp_dir.glob(pattern):
        try:
            temp_file.unlink()
        except Exception:
            pass  # Ignore cleanup errors
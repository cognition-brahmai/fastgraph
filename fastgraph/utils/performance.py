"""
Performance monitoring utilities for FastGraph

This module provides performance monitoring, profiling, and
benchmarking capabilities for FastGraph operations.
"""

import time
import contextlib
import threading
import statistics
from typing import Any, Dict, List, Optional, Callable, Union
from functools import wraps
from dataclasses import dataclass, field
from collections import defaultdict, deque

from ..exceptions import FastGraphError


@dataclass
class PerformanceMetric:
    """Single performance metric."""
    operation: str
    duration: float
    timestamp: float
    thread_id: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceStats:
    """Performance statistics summary."""
    operation: str
    count: int
    total_duration: float
    avg_duration: float
    min_duration: float
    max_duration: float
    median_duration: float
    std_deviation: float
    last_duration: float


class PerformanceMonitor:
    """
    Monitors and tracks performance metrics for FastGraph operations.
    
    Provides timing, profiling, and statistical analysis of
    graph operations for performance optimization.
    """
    
    def __init__(self, max_metrics: int = 10000):
        """
        Initialize performance monitor.
        
        Args:
            max_metrics: Maximum number of metrics to store
        """
        self.max_metrics = max_metrics
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_metrics))
        self._current_operations: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._enabled = True
    
    def enable(self) -> None:
        """Enable performance monitoring."""
        with self._lock:
            self._enabled = True
    
    def disable(self) -> None:
        """Disable performance monitoring."""
        with self._lock:
            self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if monitoring is enabled."""
        return self._enabled
    
    def start_operation(self, operation: str, **metadata) -> str:
        """
        Start timing an operation.
        
        Args:
            operation: Operation name
            **metadata: Additional metadata
            
        Returns:
            Operation ID for later tracking
        """
        if not self._enabled:
            return ""
        
        operation_id = f"{operation}_{threading.get_ident()}_{time.time()}"
        
        with self._lock:
            self._current_operations[operation_id] = {
                "start_time": time.time(),
                "operation": operation,
                "metadata": metadata
            }
        
        return operation_id
    
    def end_operation(self, operation_id: str, **metadata) -> Optional[float]:
        """
        End timing an operation.
        
        Args:
            operation_id: Operation ID from start_operation
            **metadata: Additional metadata
            
        Returns:
            Operation duration in seconds
        """
        if not self._enabled or not operation_id:
            return None
        
        with self._lock:
            if operation_id not in self._current_operations:
                return None
            
            start_info = self._current_operations.pop(operation_id)
            duration = time.time() - start_info["start_time"]
            
            # Merge metadata
            merged_metadata = start_info["metadata"].copy()
            merged_metadata.update(metadata)
            
            # Store metric
            metric = PerformanceMetric(
                operation=start_info["operation"],
                duration=duration,
                timestamp=start_info["start_time"],
                thread_id=threading.get_ident(),
                metadata=merged_metadata
            )
            
            self._metrics[metric.operation].append(metric)
            
            return duration
    
    def record_metric(self, operation: str, duration: float, **metadata) -> None:
        """
        Record a performance metric directly.
        
        Args:
            operation: Operation name
            duration: Duration in seconds
            **metadata: Additional metadata
        """
        if not self._enabled:
            return
        
        metric = PerformanceMetric(
            operation=operation,
            duration=duration,
            timestamp=time.time(),
            thread_id=threading.get_ident(),
            metadata=metadata
        )
        
        with self._lock:
            self._metrics[operation].append(metric)
    
    def get_stats(self, operation: Optional[str] = None) -> Union[PerformanceStats, Dict[str, PerformanceStats]]:
        """
        Get performance statistics.
        
        Args:
            operation: Specific operation to get stats for, or None for all
            
        Returns:
            PerformanceStats or dict of stats
        """
        with self._lock:
            if operation:
                return self._calculate_stats(operation)
            else:
                return {op: self._calculate_stats(op) for op in self._metrics.keys()}
    
    def _calculate_stats(self, operation: str) -> PerformanceStats:
        """Calculate statistics for an operation."""
        metrics = list(self._metrics[operation])
        
        if not metrics:
            return PerformanceStats(
                operation=operation,
                count=0, total_duration=0, avg_duration=0,
                min_duration=0, max_duration=0, median_duration=0,
                std_deviation=0, last_duration=0
            )
        
        durations = [m.duration for m in metrics]
        
        return PerformanceStats(
            operation=operation,
            count=len(metrics),
            total_duration=sum(durations),
            avg_duration=statistics.mean(durations),
            min_duration=min(durations),
            max_duration=max(durations),
            median_duration=statistics.median(durations),
            std_deviation=statistics.stdev(durations) if len(durations) > 1 else 0,
            last_duration=durations[-1]
        )
    
    def get_recent_metrics(self, operation: str, count: int = 100) -> List[PerformanceMetric]:
        """
        Get recent metrics for an operation.
        
        Args:
            operation: Operation name
            count: Number of recent metrics
            
        Returns:
            List of recent metrics
        """
        with self._lock:
            metrics = list(self._metrics[operation])
            return metrics[-count:] if metrics else []
    
    def clear_metrics(self, operation: Optional[str] = None) -> None:
        """
        Clear performance metrics.
        
        Args:
            operation: Specific operation to clear, or None for all
        """
        with self._lock:
            if operation:
                self._metrics[operation].clear()
            else:
                self._metrics.clear()
            self._current_operations.clear()
    
    def get_slow_operations(self, threshold: float = 1.0) -> List[PerformanceMetric]:
        """
        Get operations slower than threshold.
        
        Args:
            threshold: Threshold in seconds
            
        Returns:
            List of slow operations
        """
        slow_ops = []
        
        with self._lock:
            for metrics in self._metrics.values():
                slow_ops.extend([m for m in metrics if m.duration > threshold])
        
        return sorted(slow_ops, key=lambda m: m.duration, reverse=True)
    
    def export_metrics(self, format: str = "dict") -> Any:
        """
        Export metrics in various formats.
        
        Args:
            format: Export format (dict, json, csv)
            
        Returns:
            Exported metrics
        """
        import json
        
        with self._lock:
            data = {}
            for op, metrics in self._metrics.items():
                data[op] = [
                    {
                        "duration": m.duration,
                        "timestamp": m.timestamp,
                        "thread_id": m.thread_id,
                        "metadata": m.metadata
                    }
                    for m in metrics
                ]
        
        if format == "json":
            return json.dumps(data, indent=2)
        elif format == "dict":
            return data
        else:
            raise ValueError(f"Unsupported format: {format}")


# Decorators for performance monitoring
def performance_monitor(operation: Optional[str] = None, include_args: bool = False):
    """
    Decorator for performance monitoring.
    
    Args:
        operation: Operation name (auto-detected if None)
        include_args: Whether to include function arguments in metadata
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation or f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            monitor = get_global_performance_monitor()
            
            # Start timing
            operation_id = monitor.start_operation(op_name)
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # End timing
                metadata = {}
                if include_args:
                    metadata["args_count"] = len(args)
                    metadata["kwargs_count"] = len(kwargs)
                
                monitor.end_operation(operation_id, **metadata)
                return result
                
            except Exception as e:
                # End timing with error metadata
                monitor.end_operation(operation_id, error=str(e))
                raise
        
        return wrapper
    return decorator


def timed(operation: Optional[str] = None):
    """
    Simple timing decorator.
    
    Args:
        operation: Operation name
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation or f"{func.__name__}"
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                monitor = get_global_performance_monitor()
                monitor.record_metric(op_name, duration)
        
        return wrapper
    return decorator


@contextlib.contextmanager
def performance_context(operation: str, **metadata):
    """
    Context manager for performance monitoring.
    
    Args:
        operation: Operation name
        **metadata: Additional metadata
    """
    monitor = get_global_performance_monitor()
    operation_id = monitor.start_operation(operation, **metadata)
    
    try:
        yield
    finally:
        monitor.end_operation(operation_id)


class BenchmarkRunner:
    """Utility for running performance benchmarks."""
    
    def __init__(self):
        """Initialize benchmark runner."""
        self.results: List[Dict[str, Any]] = []
    
    def run_benchmark(self, func: Callable, iterations: int = 100, 
                     warmup_iterations: int = 10, **func_kwargs) -> Dict[str, Any]:
        """
        Run a benchmark function.
        
        Args:
            func: Function to benchmark
            iterations: Number of iterations
            warmup_iterations: Number of warmup iterations
            **func_kwargs: Function arguments
            
        Returns:
            Benchmark results
        """
        # Warmup
        for _ in range(warmup_iterations):
            func(**func_kwargs)
        
        # Benchmark
        durations = []
        for _ in range(iterations):
            start_time = time.time()
            func(**func_kwargs)
            durations.append(time.time() - start_time)
        
        results = {
            "function": func.__name__,
            "iterations": iterations,
            "total_time": sum(durations),
            "avg_time": statistics.mean(durations),
            "min_time": min(durations),
            "max_time": max(durations),
            "median_time": statistics.median(durations),
            "std_dev": statistics.stdev(durations) if len(durations) > 1 else 0,
            "throughput": iterations / sum(durations)
        }
        
        self.results.append(results)
        return results
    
    def compare_functions(self, funcs: List[Callable], iterations: int = 100,
                         **func_kwargs) -> Dict[str, Dict[str, Any]]:
        """
        Compare multiple functions.
        
        Args:
            funcs: List of functions to compare
            iterations: Number of iterations
            **func_kwargs: Function arguments
            
        Returns:
            Comparison results
        """
        results = {}
        
        for func in funcs:
            results[func.__name__] = self.run_benchmark(func, iterations, **func_kwargs)
        
        return results
    
    def get_speedup(self, baseline: str, target: str) -> float:
        """
        Calculate speedup between two benchmarks.
        
        Args:
            baseline: Baseline function name
            target: Target function name
            
        Returns:
            Speedup factor
        """
        baseline_result = next((r for r in self.results if r["function"] == baseline), None)
        target_result = next((r for r in self.results if r["function"] == target), None)
        
        if baseline_result and target_result:
            return baseline_result["avg_time"] / target_result["avg_time"]
        
        return 0.0


# Global performance monitor instance
_global_performance_monitor: Optional[PerformanceMonitor] = None


def get_global_performance_monitor() -> PerformanceMonitor:
    """
    Get global performance monitor.
    
    Returns:
        PerformanceMonitor instance
    """
    global _global_performance_monitor
    if _global_performance_monitor is None:
        _global_performance_monitor = PerformanceMonitor()
    return _global_performance_monitor


def set_global_performance_monitor(monitor: PerformanceMonitor) -> None:
    """
    Set global performance monitor.
    
    Args:
        monitor: PerformanceMonitor instance
    """
    global _global_performance_monitor
    _global_performance_monitor = monitor


def profile_memory(operation: Callable, **kwargs) -> Dict[str, Any]:
    """
    Profile memory usage of an operation.
    
    Args:
        operation: Operation to profile
        **kwargs: Operation arguments
        
    Returns:
        Memory profiling results
    """
    from .memory import get_global_memory_utils
    
    memory_utils = get_global_memory_utils()
    
    # Take baseline
    baseline = memory_utils.memory_snapshot("baseline")
    
    # Run operation
    start_time = time.time()
    result = operation(**kwargs)
    duration = time.time() - start_time
    
    # Take after snapshot
    after = memory_utils.memory_snapshot("after")
    
    # Calculate increase
    increase = memory_utils.get_memory_increase(0, 1)
    
    return {
        "result": result,
        "duration": duration,
        "memory_baseline": baseline["memory_usage"],
        "memory_after": after["memory_usage"],
        "memory_increase": increase
    }


def performance_report() -> str:
    """
    Generate a performance report.
    
    Returns:
        Formatted performance report
    """
    monitor = get_global_performance_monitor()
    stats = monitor.get_stats()
    
    report_lines = ["FastGraph Performance Report", "=" * 30]
    
    for operation, stat in stats.items():
        report_lines.append(f"\n{operation}:")
        report_lines.append(f"  Count: {stat.count}")
        report_lines.append(f"  Total: {stat.total_duration:.3f}s")
        report_lines.append(f"  Average: {stat.avg_duration:.3f}s")
        report_lines.append(f"  Min: {stat.min_duration:.3f}s")
        report_lines.append(f"  Max: {stat.max_duration:.3f}s")
        report_lines.append(f"  Median: {stat.median_duration:.3f}s")
        report_lines.append(f"  Std Dev: {stat.std_deviation:.3f}s")
    
    # Slow operations
    slow_ops = monitor.get_slow_operations(threshold=0.1)
    if slow_ops:
        report_lines.append(f"\nSlow Operations (>0.1s):")
        for op in slow_ops[:10]:  # Top 10
            report_lines.append(f"  {op.operation}: {op.duration:.3f}s")
    
    return "\n".join(report_lines)
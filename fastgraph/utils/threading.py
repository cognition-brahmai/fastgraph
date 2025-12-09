"""
Thread safety utilities for FastGraph

This module provides thread safety utilities and locks for concurrent
graph operations.
"""

import threading
import time
from typing import Any, Dict, Optional, Callable
from contextlib import contextmanager
from ..exceptions import ConcurrencyError


class ThreadSafetyManager:
    """
    Manages thread safety for FastGraph operations.
    
    Provides various locking mechanisms and thread coordination
    utilities for safe concurrent graph operations.
    """
    
    def __init__(self):
        """Initialize thread safety manager."""
        self._locks: Dict[str, threading.RLock] = {}
        self._lock_stats: Dict[str, Dict[str, Any]] = {}
        self._main_lock = threading.RLock()
        
    def get_lock(self, name: str) -> threading.RLock:
        """
        Get or create a named lock.
        
        Args:
            name: Lock name
            
        Returns:
            RLock instance
        """
        with self._main_lock:
            if name not in self._locks:
                self._locks[name] = threading.RLock()
                self._lock_stats[name] = {
                    "acquisitions": 0,
                    "contentions": 0,
                    "total_wait_time": 0.0
                }
            return self._locks[name]
    
    def with_lock(self, name: str):
        """
        Context manager for named lock.
        
        Args:
            name: Lock name
            
        Returns:
            Context manager
        """
        return LockContext(self.get_lock(name), self._lock_stats.get(name))
    
    def execute_locked(self, name: str, func: Callable, *args, **kwargs):
        """
        Execute function with lock.
        
        Args:
            name: Lock name
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        with self.with_lock(name):
            return func(*args, **kwargs)
    
    def try_lock(self, name: str, timeout: float = 0.0) -> bool:
        """
        Try to acquire lock without blocking.
        
        Args:
            name: Lock name
            timeout: Timeout in seconds
            
        Returns:
            True if lock acquired, False otherwise
        """
        lock = self.get_lock(name)
        acquired = lock.acquire(timeout=timeout)
        
        if acquired:
            lock.release()
        
        return acquired
    
    def get_lock_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get lock statistics.
        
        Returns:
            Dictionary of lock statistics
        """
        return self._lock_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset lock statistics."""
        for stats in self._lock_stats.values():
            stats.update({
                "acquisitions": 0,
                "contentions": 0,
                "total_wait_time": 0.0
            })


class LockContext:
    """Context manager for lock with statistics."""
    
    def __init__(self, lock: threading.RLock, stats: Optional[Dict[str, Any]]):
        """
        Initialize lock context.
        
        Args:
            lock: Lock to manage
            stats: Statistics dictionary
        """
        self.lock = lock
        self.stats = stats or {}
        self.start_time = None
    
    def __enter__(self):
        """Acquire lock."""
        if self.stats:
            self.start_time = time.time()
        
        # Check if lock is already held (contention)
        if self.lock.locked():
            if self.stats:
                self.stats["contentions"] += 1
        
        self.lock.acquire()
        
        if self.stats:
            self.stats["acquisitions"] += 1
            wait_time = time.time() - self.start_time
            self.stats["total_wait_time"] += wait_time
        
        return self.lock
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release lock."""
        self.lock.release()


# Thread-local storage for graph instances
_thread_local = threading.local()


def get_thread_id() -> int:
    """
    Get current thread ID.
    
    Returns:
        Thread ID
    """
    return threading.get_ident()


def get_current_thread_name() -> str:
    """
    Get current thread name.
    
    Returns:
        Thread name
    """
    return threading.current_thread().name


def is_thread_alive(thread_name: str) -> bool:
    """
    Check if thread is alive.
    
    Args:
        thread_name: Thread name
        
    Returns:
        True if thread is alive
    """
    for thread in threading.enumerate():
        if thread.name == thread_name:
            return thread.is_alive()
    return False


def run_in_thread(func: Callable, *args, **kwargs) -> threading.Thread:
    """
    Run function in a new thread.
    
    Args:
        func: Function to run
        *args: Function arguments
        **kwargs: Function keyword arguments
        
    Returns:
        Thread object
    """
    def thread_wrapper():
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log error in thread
            thread_name = threading.current_thread().name
            print(f"Error in thread {thread_name}: {e}")
    
    thread = threading.Thread(target=thread_wrapper)
    thread.start()
    return thread


def run_in_daemon_thread(func: Callable, *args, **kwargs) -> threading.Thread:
    """
    Run function in a daemon thread.
    
    Args:
        func: Function to run
        *args: Function arguments
        **kwargs: Function keyword arguments
        
    Returns:
        Thread object
    """
    thread = run_in_thread(func, *args, **kwargs)
    thread.daemon = True
    return thread


@contextmanager
def timeout_context(seconds: float):
    """
    Context manager with timeout.
    
    Args:
        seconds: Timeout in seconds
        
    Raises:
        ConcurrencyError: If timeout is exceeded
    """
    def timeout_handler():
        raise ConcurrencyError(f"Operation timed out after {seconds} seconds")
    
    timer = threading.Timer(seconds, timeout_handler)
    timer.start()
    
    try:
        yield
    finally:
        timer.cancel()


class ReadWriteLock:
    """
    Simple read-write lock implementation.
    
    Allows multiple readers or a single writer.
    """
    
    def __init__(self):
        """Initialize read-write lock."""
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0
    
    def acquire_read(self):
        """Acquire read lock."""
        self._read_ready.acquire()
        try:
            self._readers += 1
        finally:
            self._read_ready.release()
    
    def release_read(self):
        """Release read lock."""
        self._read_ready.acquire()
        try:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notifyAll()
        finally:
            self._read_ready.release()
    
    def acquire_write(self):
        """Acquire write lock."""
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()
    
    def release_write(self):
        """Release write lock."""
        self._read_ready.release()
    
    @contextmanager
    def read_lock(self):
        """Context manager for read lock."""
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()
    
    @contextmanager
    def write_lock(self):
        """Context manager for write lock."""
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()


class ThreadPool:
    """
    Simple thread pool for parallel operations.
    """
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize thread pool.
        
        Args:
            max_workers: Maximum number of worker threads
        """
        self.max_workers = max_workers
        self._workers = []
        self._task_queue = queue.Queue()
        self._shutdown = False
        
        # Start worker threads
        for _ in range(max_workers):
            worker = threading.Thread(target=self._worker)
            worker.daemon = True
            worker.start()
            self._workers.append(worker)
    
    def _worker(self):
        """Worker thread function."""
        while not self._shutdown:
            try:
                func, args, kwargs = self._task_queue.get(timeout=1.0)
                try:
                    func(*args, **kwargs)
                finally:
                    self._task_queue.task_done()
            except queue.Empty:
                continue
    
    def submit(self, func: Callable, *args, **kwargs):
        """
        Submit task to thread pool.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        """
        self._task_queue.put((func, args, kwargs))
    
    def wait_completion(self):
        """Wait for all tasks to complete."""
        self._task_queue.join()
    
    def shutdown(self):
        """Shutdown thread pool."""
        self._shutdown = True
        for worker in self._workers:
            worker.join(timeout=1.0)


# Global thread safety manager instance
_global_thread_manager: Optional[ThreadSafetyManager] = None


def get_global_thread_manager() -> ThreadSafetyManager:
    """
    Get global thread safety manager.
    
    Returns:
        ThreadSafetyManager instance
    """
    global _global_thread_manager
    if _global_thread_manager is None:
        _global_thread_manager = ThreadSafetyManager()
    return _global_thread_manager


def set_global_thread_manager(manager: ThreadSafetyManager) -> None:
    """
    Set global thread safety manager.
    
    Args:
        manager: ThreadSafetyManager instance
    """
    global _global_thread_manager
    _global_thread_manager = manager


@contextmanager
def global_lock(name: str = "default"):
    """
    Context manager for global named lock.
    
    Args:
        name: Lock name
    """
    manager = get_global_thread_manager()
    with manager.with_lock(name):
        yield


# Import queue for ThreadPool
import queue
"""
Cache management utilities for FastGraph

This module provides caching functionality including LRU caches,
TTL-based caches, and cache management.
"""

import time
import threading
from typing import Any, Dict, Optional, Callable, Tuple
from functools import wraps, lru_cache
from collections import OrderedDict
from ..exceptions import CacheError


class CacheManager:
    """
    Manages caching for FastGraph operations.
    
    Provides multiple cache types and strategies for optimizing
    graph query performance.
    """
    
    def __init__(self):
        """Initialize cache manager."""
        self._caches: Dict[str, 'BaseCache'] = {}
        self._stats: Dict[str, Dict[str, int]] = {}
        self._lock = threading.RLock()
    
    def get_cache(self, name: str, cache_type: str = "lru", **kwargs) -> 'BaseCache':
        """
        Get or create a cache.
        
        Args:
            name: Cache name
            cache_type: Cache type (lru, ttl, simple)
            **kwargs: Cache-specific parameters
            
        Returns:
            Cache instance
        """
        with self._lock:
            if name not in self._caches:
                if cache_type == "lru":
                    size = kwargs.get("size", 128)
                    self._caches[name] = LRUCache(size)
                elif cache_type == "ttl":
                    size = kwargs.get("size", 128)
                    ttl = kwargs.get("ttl", 3600)
                    self._caches[name] = TTLCache(size, ttl)
                elif cache_type == "simple":
                    size = kwargs.get("size", 128)
                    self._caches[name] = SimpleCache(size)
                else:
                    raise CacheError(f"Unknown cache type: {cache_type}")
                
                self._stats[name] = {"hits": 0, "misses": 0, "evictions": 0}
            
            return self._caches[name]
    
    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary of cache statistics
        """
        with self._lock:
            stats = self._stats.copy()
            for name, cache in self._caches.items():
                stats[name].update(cache.get_stats())
            return stats
    
    def clear_cache(self, name: str) -> None:
        """
        Clear specific cache.
        
        Args:
            name: Cache name
        """
        with self._lock:
            if name in self._caches:
                self._caches[name].clear()
    
    def clear_all_caches(self) -> None:
        """Clear all caches."""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()
    
    def reset_stats(self) -> None:
        """Reset cache statistics."""
        with self._lock:
            for stats in self._stats.values():
                stats.update({"hits": 0, "misses": 0, "evictions": 0})


class BaseCache:
    """Base cache class."""
    
    def __init__(self):
        """Initialize base cache."""
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def get(self, key: Any) -> Optional[Any]:
        """Get value from cache."""
        with self._lock:
            value = self._get_impl(key)
            if value is not None:
                self._hits += 1
            else:
                self._misses += 1
            return value
    
    def put(self, key: Any, value: Any) -> None:
        """Put value in cache."""
        with self._lock:
            self._put_impl(key, value)
    
    def remove(self, key: Any) -> Optional[Any]:
        """Remove value from cache."""
        with self._lock:
            return self._remove_impl(key)
    
    def clear(self) -> None:
        """Clear cache."""
        with self._lock:
            self._clear_impl()
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions
        }
    
    # Abstract methods to be implemented by subclasses
    def _get_impl(self, key: Any) -> Optional[Any]:
        raise NotImplementedError
    
    def _put_impl(self, key: Any, value: Any) -> None:
        raise NotImplementedError
    
    def _remove_impl(self, key: Any) -> Optional[Any]:
        raise NotImplementedError
    
    def _clear_impl(self) -> None:
        raise NotImplementedError
    
    def __contains__(self, key: Any) -> bool:
        """Check if key exists in cache."""
        return self.get(key) is not None
    
    def __getitem__(self, key: Any) -> Any:
        """Get item using dictionary syntax."""
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value
    
    def __setitem__(self, key: Any, value: Any) -> None:
        """Set item using dictionary syntax."""
        self.put(key, value)


class LRUCache(BaseCache):
    """
    Least Recently Used (LRU) cache implementation.
    
    Evicts least recently used items when capacity is reached.
    """
    
    def __init__(self, max_size: int):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of items
        """
        super().__init__()
        self._max_size = max_size
        self._cache = OrderedDict()
    
    def _get_impl(self, key: Any) -> Optional[Any]:
        """Get value from LRU cache."""
        if key in self._cache:
            # Move to end (most recently used)
            value = self._cache.pop(key)
            self._cache[key] = value
            return value
        return None
    
    def _put_impl(self, key: Any, value: Any) -> None:
        """Put value in LRU cache."""
        if key in self._cache:
            # Update existing
            self._cache.pop(key)
        elif len(self._cache) >= self._max_size:
            # Evict least recently used
            evicted_key, evicted_value = self._cache.popitem(last=False)
            self._evictions += 1
        
        self._cache[key] = value
    
    def _remove_impl(self, key: Any) -> Optional[Any]:
        """Remove value from LRU cache."""
        return self._cache.pop(key, None)
    
    def _clear_impl(self) -> None:
        """Clear LRU cache."""
        self._cache.clear()
    
    def get_size(self) -> int:
        """Get current cache size."""
        return len(self._cache)
    
    def get_capacity(self) -> int:
        """Get cache capacity."""
        return self._max_size


class TTLCache(BaseCache):
    """
    Time-To-Live (TTL) cache implementation.
    
    Items expire after specified time period.
    """
    
    def __init__(self, max_size: int, ttl: int):
        """
        Initialize TTL cache.
        
        Args:
            max_size: Maximum number of items
            ttl: Time-to-live in seconds
        """
        super().__init__()
        self._max_size = max_size
        self._ttl = ttl
        self._cache: Dict[Any, Tuple[Any, float]] = {}
    
    def _get_impl(self, key: Any) -> Optional[Any]:
        """Get value from TTL cache."""
        current_time = time.time()
        
        if key in self._cache:
            value, expiry_time = self._cache[key]
            
            if expiry_time > current_time:
                return value
            else:
                # Expired item
                del self._cache[key]
                self._evictions += 1
        
        return None
    
    def _put_impl(self, key: Any, value: Any) -> None:
        """Put value in TTL cache."""
        current_time = time.time()
        expiry_time = current_time + self._ttl
        
        # Clean expired items if needed
        self._cleanup_expired()
        
        if key not in self._cache and len(self._cache) >= self._max_size:
            # Remove oldest item
            oldest_key = min(self._cache.keys(), 
                           key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
            self._evictions += 1
        
        self._cache[key] = (value, expiry_time)
    
    def _remove_impl(self, key: Any) -> Optional[Any]:
        """Remove value from TTL cache."""
        if key in self._cache:
            value, _ = self._cache.pop(key)
            return value
        return None
    
    def _clear_impl(self) -> None:
        """Clear TTL cache."""
        self._cache.clear()
    
    def _cleanup_expired(self) -> None:
        """Remove expired items."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry <= current_time
        ]
        
        for key in expired_keys:
            del self._cache[key]
            self._evictions += 1
    
    def get_size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


class SimpleCache(BaseCache):
    """
    Simple fixed-size cache implementation.
    
    Uses random replacement when capacity is reached.
    """
    
    def __init__(self, max_size: int):
        """
        Initialize simple cache.
        
        Args:
            max_size: Maximum number of items
        """
        super().__init__()
        self._max_size = max_size
        self._cache: Dict[Any, Any] = {}
    
    def _get_impl(self, key: Any) -> Optional[Any]:
        """Get value from simple cache."""
        return self._cache.get(key)
    
    def _put_impl(self, key: Any, value: Any) -> None:
        """Put value in simple cache."""
        if key not in self._cache and len(self._cache) >= self._max_size:
            # Remove a random item
            import random
            random_key = random.choice(list(self._cache.keys()))
            del self._cache[random_key]
            self._evictions += 1
        
        self._cache[key] = value
    
    def _remove_impl(self, key: Any) -> Optional[Any]:
        """Remove value from simple cache."""
        return self._cache.pop(key, None)
    
    def _clear_impl(self) -> None:
        """Clear simple cache."""
        self._cache.clear()
    
    def get_size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


# Decorators for easy caching
def cached(cache_name: str = "default", cache_type: str = "lru", **cache_kwargs):
    """
    Decorator for caching function results.
    
    Args:
        cache_name: Cache name
        cache_type: Cache type
        **cache_kwargs: Cache-specific arguments
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get cache manager
            cache_manager = get_global_cache_manager()
            cache = cache_manager.get_cache(cache_name, cache_type, **cache_kwargs)
            
            # Create cache key
            cache_key = (func.__name__, args, frozenset(kwargs.items()))
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute and cache result
            result = func(*args, **kwargs)
            cache.put(cache_key, result)
            
            return result
        
        return wrapper
    return decorator


def cached_result(ttl: Optional[int] = None, size: int = 128):
    """
    Decorator for caching results with TTL support.
    
    Args:
        ttl: Time-to-live in seconds
        size: Maximum cache size
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        if ttl:
            # Use TTL cache
            cache_key = f"{func.__name__}_ttl"
            return cached(cache_key, "ttl", ttl=ttl, size=size)(func)
        else:
            # Use LRU cache
            return lru_cache(maxsize=size)(func)
    
    return decorator


def timed_cache(ttl: int, size: int = 128):
    """
    Decorator for timed caching.
    
    Args:
        ttl: Time-to-live in seconds
        size: Maximum cache size
        
    Returns:
        Decorated function
    """
    return cached("timed", "ttl", ttl=ttl, size=size)


# Global cache manager instance
_global_cache_manager: Optional[CacheManager] = None


def get_global_cache_manager() -> CacheManager:
    """
    Get global cache manager.
    
    Returns:
        CacheManager instance
    """
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager


def set_global_cache_manager(manager: CacheManager) -> None:
    """
    Set global cache manager.
    
    Args:
        manager: CacheManager instance
    """
    global _global_cache_manager
    _global_cache_manager = manager


def clear_all_caches() -> None:
    """Clear all global caches."""
    get_global_cache_manager().clear_all_caches()


def get_cache_statistics() -> Dict[str, Dict[str, int]]:
    """
    Get statistics for all caches.
    
    Returns:
        Cache statistics
    """
    return get_global_cache_manager().get_stats()
"""AdaptCache core: a decorator that caches function results and adapts the
TTL to how often each specific call is actually reused.

v0.1 uses a transparent, explainable heuristic based on recent access
frequency -- not a trained ML model. That's an intentional, honest scope
for a first release. See README.md for the roadmap.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Any, Callable, Deque, Dict, List, Optional

from .backends import Backend, MemoryBackend, RedisBackend


class AdaptCache:
    def __init__(
        self,
        backend: str = "memory",
        redis_url: Optional[str] = None,
        adaptive_ttl: bool = True,
        default_ttl: int = 300,
        min_ttl: int = 5,
        max_ttl: int = 3600,
        history_size: int = 20,
    ) -> None:
        self._backend: Backend
        if backend == "memory":
            self._backend = MemoryBackend()
        elif backend == "redis":
            if not redis_url:
                raise ValueError("redis_url is required when backend='redis'")
            self._backend = RedisBackend(redis_url)
        else:
            raise ValueError(f"Unknown backend: {backend!r}")

        self.adaptive_ttl = adaptive_ttl
        self.default_ttl = default_ttl
        self.min_ttl = min_ttl
        self.max_ttl = max_ttl

        self._history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self._hits = 0
        self._misses = 0
        self._known_keys: Dict[str, str] = {}  # fingerprint -> cache_key

    # ---- public API --------------------------------------------------

    def intelligent(
        self, ttl: Optional[int] = None, tags: Optional[List[str]] = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator: cache the wrapped function's return value.

        Return values must be JSON-serializable (dicts, lists, primitives).
        `tags` lets you group cache entries (e.g. by the DB table they read
        from) so they can all be invalidated together via `invalidate_tag()`.
        """
        resolved_tags: List[str] = tags or []

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                fingerprint = self._fingerprint(func, args, kwargs)
                cache_key = f"adaptcache:{func.__module__}.{func.__qualname__}:{fingerprint}"
                self._known_keys[fingerprint] = cache_key

                cached = self._backend.get(cache_key)
                if cached is not None:
                    self._hits += 1
                    self._history[fingerprint].append(time.time())
                    return json.loads(cached)

                self._misses += 1
                result = func(*args, **kwargs)

                if self.adaptive_ttl:
                    resolved_ttl = self._adaptive_ttl(fingerprint)
                else:
                    resolved_ttl = ttl or self.default_ttl

                try:
                    self._backend.set(cache_key, json.dumps(result), resolved_ttl)
                except TypeError as exc:
                    raise TypeError(
                        f"{func.__qualname__} returned a non-JSON-serializable value; "
                        "adaptcache v0.1 only caches JSON-safe results."
                    ) from exc

                for tag in resolved_tags:
                    self._backend.tag_add(tag, cache_key)

                self._history[fingerprint].append(time.time())
                return result

            wrapper.invalidate = lambda *a, **kw: self.invalidate(func, *a, **kw)  # type: ignore[attr-defined]
            return wrapper

        return decorator

    def invalidate(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Manually evict one cached call, e.g. right after an UPDATE/DELETE."""
        fingerprint = self._fingerprint(func, args, kwargs)
        cache_key = self._known_keys.get(fingerprint)
        if cache_key:
            self._backend.delete(cache_key)

    def invalidate_tag(self, tag: str) -> None:
        """Evict every cache entry registered under `tag`, e.g. every
        function cached with `tags=["users"]`. Safe to call from multiple
        processes when backend="redis" (tag membership lives in Redis too).
        """
        for cache_key in self._backend.tag_members(tag):
            self._backend.delete(cache_key)
        self._backend.tag_clear(tag)

    def clear(self) -> None:
        """Wipe every cached entry and reset stats/history. A blunt
        instrument compared to invalidate()/invalidate_tag() -- prefer
        those for anything narrower than "start over".

        Raises NotImplementedError on the Redis backend (FLUSHDB is
        dangerous on a shared instance) rather than silently resetting
        Python-side stats while leaving stale data in Redis.
        """
        self._backend.clear()
        self._history.clear()
        self._known_keys.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total else 0.0,
            "tracked_keys": len(self._history),
        }

    # ---- internals -----------------------------------------------------

    @staticmethod
    def _fingerprint(func: Callable[..., Any], args: Any, kwargs: Any) -> str:
        sig = f"{func.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
        return hashlib.sha256(sig.encode()).hexdigest()[:16]

    def _adaptive_ttl(self, fingerprint: str) -> int:
        """Heuristic, not ML: a short average gap between accesses (hot key)
        pushes TTL up toward max_ttl; a long gap (cold key) pushes it down
        toward min_ttl. Anchored so that avg_gap == default_ttl leaves TTL
        roughly unchanged.
        """
        history = self._history[fingerprint]
        if len(history) < 2:
            return self.default_ttl

        gaps = [b - a for a, b in zip(history, list(history)[1:])]
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap <= 0:
            return self.max_ttl

        ttl = int((self.default_ttl ** 2) / avg_gap)
        return max(self.min_ttl, min(self.max_ttl, ttl))

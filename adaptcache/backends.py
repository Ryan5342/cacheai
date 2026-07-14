"""Cache storage backends for AdaptCache.

Two backends ship in v0.1:
- MemoryBackend: pure-Python dict, zero dependencies. Default backend,
  good for a single process, development, and tests.
- RedisBackend: thin wrapper around redis-py (`pip install adaptcache[redis]`).
"""

from __future__ import annotations

import time
from typing import Any, Optional, Protocol, Set


class Backend(Protocol):
    """Structural type every cache backend must satisfy. Not a base class
    to inherit from -- MemoryBackend and RedisBackend just happen to match
    it (duck typing), which is what lets AdaptCache treat them the same way
    and lets a third party write a custom backend without importing from
    this module at all.
    """

    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...
    def tag_add(self, tag: str, key: str) -> None: ...
    def tag_members(self, tag: str) -> Set[str]: ...
    def tag_clear(self, tag: str) -> None: ...


class MemoryBackend:
    """In-process dict backend. Not shared across processes/workers."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._tags: dict[str, Set[str]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at < time.time():
            # pop(key, None) instead of del: if another thread already
            # expired and removed this same key between our check above and
            # this line, del would raise KeyError. pop makes the removal
            # idempotent, closing that window regardless of how likely it
            # is to happen in practice under the GIL.
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
        self._tags.clear()

    def tag_add(self, tag: str, key: str) -> None:
        self._tags.setdefault(tag, set()).add(key)

    def tag_members(self, tag: str) -> Set[str]:
        return set(self._tags.get(tag, ()))

    def tag_clear(self, tag: str) -> None:
        self._tags.pop(tag, None)


class RedisBackend:
    """Wraps redis-py. Values are JSON strings (serialized in core.py)."""

    def __init__(self, redis_url: str) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "RedisBackend requires redis-py. Install with: pip install adaptcache[redis]"
            ) from exc
        self._client = redis.from_url(redis_url)

    def get(self, key: str) -> Optional[str]:
        value = self._client.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    def set(self, key: str, value: str, ttl: int) -> None:
        self._client.set(key, value, ex=ttl)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def clear(self) -> None:
        # Deliberately not implemented: FLUSHDB is dangerous on a shared
        # Redis instance. Delete keys individually if you need this.
        raise NotImplementedError("clear() is not supported for RedisBackend")

    def tag_add(self, tag: str, key: str) -> None:
        self._client.sadd(f"adaptcache:tagset:{tag}", key)

    def tag_members(self, tag: str) -> Set[str]:
        members = self._client.smembers(f"adaptcache:tagset:{tag}")
        return {m.decode() if isinstance(m, bytes) else m for m in members}

    def tag_clear(self, tag: str) -> None:
        self._client.delete(f"adaptcache:tagset:{tag}")

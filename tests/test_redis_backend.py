import sys

import pytest

redis = pytest.importorskip("redis")

from adaptcache import AdaptCache

REDIS_URL = "redis://localhost:6379"


def _redis_available() -> bool:
    try:
        redis.from_url(REDIS_URL).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="no local Redis server running on localhost:6379"
)


def test_redis_backend_hit_and_invalidate():
    cache = AdaptCache(
        backend="redis", redis_url=REDIS_URL, adaptive_ttl=False, default_ttl=5
    )
    calls = []

    @cache.intelligent()
    def get_value(x):
        calls.append(x)
        return {"value": x * 2}

    assert get_value(42) == {"value": 84}
    assert get_value(42) == {"value": 84}
    assert calls == [42]  # second call served from Redis, not re-executed

    get_value.invalidate(42)
    get_value(42)
    assert calls == [42, 42]


def test_redis_backend_invalidate_tag():
    # Two separate AdaptCache instances against the same Redis, simulating two
    # worker processes -- this is the scenario in-process-only tags would
    # break, since tag membership must live in Redis, not in either process.
    cache_a = AdaptCache(
        backend="redis", redis_url=REDIS_URL, adaptive_ttl=False, default_ttl=5
    )
    cache_b = AdaptCache(
        backend="redis", redis_url=REDIS_URL, adaptive_ttl=False, default_ttl=5
    )
    calls = []

    @cache_a.intelligent(tags=["users"])
    def get_value(x):
        calls.append(x)
        return {"value": x}

    get_value(1)
    get_value(1)
    assert calls == [1]  # cached

    cache_b.invalidate_tag("users")  # a different process/instance invalidates it

    get_value(1)
    assert calls == [1, 1]  # cache_a's entry was still invalidated


def test_clear_on_redis_backend_raises_not_implemented():
    # AdaptCache.clear() propagates this instead of silently resetting
    # Python-side stats while Redis still holds the stale data -- see the
    # docstring on AdaptCache.clear().
    cache = AdaptCache(backend="redis", redis_url=REDIS_URL)
    with pytest.raises(NotImplementedError):
        cache.clear()


def test_missing_redis_py_gives_a_helpful_import_error(monkeypatch):
    # Simulate `redis` not being installed (it's an optional extra) and
    # check the error tells you how to fix it, instead of a bare
    # ModuleNotFoundError.
    monkeypatch.setitem(sys.modules, "redis", None)
    with pytest.raises(ImportError, match=r"pip install adaptcache\[redis\]"):
        AdaptCache(backend="redis", redis_url=REDIS_URL)

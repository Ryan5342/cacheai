import time

import pytest

from adaptcache import AdaptCache


def test_cache_hit_and_miss():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=60)
    calls = []

    @cache.intelligent()
    def get_value(x):
        calls.append(x)
        return {"value": x * 2}

    assert get_value(5) == {"value": 10}
    assert get_value(5) == {"value": 10}
    assert calls == [5]  # second call served from cache, function not re-executed

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5


def test_different_args_are_different_cache_entries():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=60)

    @cache.intelligent()
    def get_value(x):
        return x * 2

    assert get_value(1) == 2
    assert get_value(2) == 4
    assert cache.stats()["misses"] == 2


def test_invalidate_forces_recompute():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=60)
    calls = []

    @cache.intelligent()
    def get_value(x):
        calls.append(x)
        return x

    get_value(1)
    get_value.invalidate(1)
    get_value(1)
    assert calls == [1, 1]


def test_expired_entry_is_recomputed():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=1)
    calls = []

    @cache.intelligent()
    def get_value(x):
        calls.append(x)
        return x

    get_value(1)
    time.sleep(1.2)
    get_value(1)
    assert calls == [1, 1]


def test_clear_wipes_cache_and_resets_stats():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=60)
    calls = []

    @cache.intelligent()
    def get_value(x):
        calls.append(x)
        return x

    get_value(1)
    get_value(1)
    assert cache.stats()["hits"] == 1

    cache.clear()
    assert cache.stats() == {"hits": 0, "misses": 0, "hit_rate": 0.0, "tracked_keys": 0}

    get_value(1)
    assert calls == [1, 1]  # recomputed: clear() actually wiped the entry
    # (miss, hit, clear, miss -- two real calls to get_value's body, not three)


def test_missing_redis_url_raises_value_error():
    with pytest.raises(ValueError, match="redis_url is required"):
        AdaptCache(backend="redis")


def test_unknown_backend_raises_value_error():
    with pytest.raises(ValueError, match="Unknown backend"):
        AdaptCache(backend="memcached")


def test_non_json_serializable_result_raises_helpful_typeerror():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=60)

    @cache.intelligent()
    def get_a_set():
        return {1, 2, 3}  # sets aren't JSON-serializable

    with pytest.raises(TypeError, match="JSON-safe"):
        get_a_set()


def test_adaptive_ttl_non_positive_gap_returns_max_ttl():
    # Defensive edge case: if two accesses land on the exact same
    # timestamp (or, in principle, a backwards clock adjustment), avg_gap
    # is <= 0. Treat that as "as hot as it gets" rather than dividing by
    # zero or returning something nonsensical.
    cache = AdaptCache(backend="memory", adaptive_ttl=True, default_ttl=60, min_ttl=5, max_ttl=1800)

    @cache.intelligent()
    def get_value(x):
        return x

    get_value(1)
    fingerprint = cache._fingerprint(get_value.__wrapped__, (1,), {})
    now = time.time()
    cache._history[fingerprint].clear()
    cache._history[fingerprint].extend([now, now])  # zero gap

    assert cache._adaptive_ttl(fingerprint) == cache.max_ttl


def test_adaptive_ttl_grows_for_frequently_accessed_key():
    cache = AdaptCache(backend="memory", adaptive_ttl=True, default_ttl=60, min_ttl=5, max_ttl=1800)

    @cache.intelligent()
    def get_value(x):
        return x

    get_value(1)
    fingerprint = cache._fingerprint(get_value.__wrapped__, (1,), {})
    now = time.time()
    cache._history[fingerprint].clear()
    cache._history[fingerprint].extend([now + i * 2 for i in range(10)])  # accessed every ~2s

    ttl = cache._adaptive_ttl(fingerprint)
    assert ttl > cache.default_ttl


def test_adaptive_ttl_shrinks_for_rarely_accessed_key():
    cache = AdaptCache(backend="memory", adaptive_ttl=True, default_ttl=60, min_ttl=5, max_ttl=1800)

    @cache.intelligent()
    def get_value(x):
        return x

    get_value(1)
    fingerprint = cache._fingerprint(get_value.__wrapped__, (1,), {})
    now = time.time()
    cache._history[fingerprint].clear()
    cache._history[fingerprint].extend([now, now + 7200])  # accessed ~2h apart

    ttl = cache._adaptive_ttl(fingerprint)
    assert ttl < cache.default_ttl

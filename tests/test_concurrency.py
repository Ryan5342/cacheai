"""Real concurrency checks for MemoryBackend, not mocked threading.

These are regression tests, not the original exploratory stress test --
that ran 300 trials of 50 threads each (and separately, 50 trials of 30
threads x 500 calls) with zero failures, which is documented in the
README's Thread safety section along with its honest limits. Keeping the
permanent suite fast: a handful of real threads is enough to catch an
actual regression without slowing down every CI run.
"""

import threading

from adaptcache import AdaptCache
from adaptcache.backends import MemoryBackend


def test_concurrent_get_on_expired_key_does_not_raise():
    # Many real threads all observe the same already-expired entry at
    # once. Before pop() replaced del(), this could raise KeyError if two
    # threads both passed the expiry check before either deleted it.
    backend = MemoryBackend()
    backend.set("k", "v", ttl=-1)  # expired the instant it's created

    n = 20
    barrier = threading.Barrier(n)
    errors = []

    def hit() -> None:
        barrier.wait()
        try:
            backend.get("k")
        except Exception as exc:  # pragma: no cover -- this is what we're checking for
            errors.append(exc)

    threads = [threading.Thread(target=hit) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


def test_concurrent_hits_and_misses_are_not_lost():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=300)

    @cache.intelligent()
    def get_value(x: int) -> int:
        return x * 2

    n_threads = 20
    calls_per_thread = 100
    barrier = threading.Barrier(n_threads)

    def hammer() -> None:
        barrier.wait()
        for _ in range(calls_per_thread):
            get_value(1)  # same key every time -- maximizes contention

    threads = [threading.Thread(target=hammer) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = cache.stats()
    assert stats["hits"] + stats["misses"] == n_threads * calls_per_thread

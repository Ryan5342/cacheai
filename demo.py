"""Illustrative demo: the TTL that AdaptCache's adaptive heuristic assigns to
a "hot" key (requested every ~2s) versus a "cold" key (requested every ~2h),
compared to one fixed static TTL.

This is a demonstration of the heuristic's behavior, not a performance
benchmark against a real Redis deployment -- no such benchmark has been
run yet, so no throughput/latency numbers are claimed here.

Run: python demo.py
"""

from adaptcache import AdaptCache


def main() -> None:
    cache = AdaptCache(
        backend="memory", adaptive_ttl=True, default_ttl=60, min_ttl=5, max_ttl=1800
    )

    @cache.intelligent()
    def fetch(key: str):
        return {"key": key}

    hot_fp = cache._fingerprint(fetch.__wrapped__, ("hot",), {})
    cold_fp = cache._fingerprint(fetch.__wrapped__, ("cold",), {})

    now = 1_000_000.0
    cache._history[hot_fp].extend([now + i * 2 for i in range(10)])  # every ~2s
    cache._history[cold_fp].extend([now + i * 7200 for i in range(3)])  # every ~2h

    hot_ttl = cache._adaptive_ttl(hot_fp)
    cold_ttl = cache._adaptive_ttl(cold_fp)

    print("Static TTL (fixed)      : 60s for every key, regardless of usage")
    print(f"Adaptive TTL - hot key  : {hot_ttl}s  (requested every ~2s)")
    print(f"Adaptive TTL - cold key : {cold_ttl}s  (requested every ~2h)")
    print()
    print("The hot key stays cached long enough to actually be reused;")
    print("the cold key expires fast instead of wasting cache space.")


if __name__ == "__main__":
    main()

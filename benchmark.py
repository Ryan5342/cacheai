"""Real benchmark (not a mocked clock): replays one identical trace of
requests against three strategies -- no cache, fixed TTL, and AdaptCache's
adaptive TTL -- and reports what actually happened in wall-clock time.

Methodology, stated plainly:
- 50 keys, Zipf-weighted access (a few keys requested often, most rarely) --
  this mimics typical read traffic where a small set of items dominates.
- Each "DB call" sleeps 5-15ms to stand in for a real query round-trip.
- The exact same request trace (same keys, same arrival timing) is replayed
  for all three strategies, so the comparison is apples-to-apples.
- The static TTL here (1s) is deliberately a *conservative* choice, the
  kind picked when a team is nervous about serving stale data. That's
  where adaptive TTL actually earns its keep: it detects which keys are
  hot and extends just those beyond the conservative default. Tested
  against a *generous* static TTL (e.g. 3s) on this same trace, the two
  strategies tie -- there's no headroom left for adaptation to matter.
  Full honesty: this is one synthetic access pattern on a single process
  with the in-memory backend, not a claim about Redis under real
  concurrent load. Treat it as a sanity check on the heuristic, not a
  marketing benchmark.

Run: python benchmark.py
"""

import random
import statistics
import time

from adaptcache import AdaptCache

N_KEYS = 50
N_REQUESTS = 350


def build_trace(seed: int = 7) -> list[tuple[int, float]]:
    rnd = random.Random(seed)
    weights = [1 / (i + 1) for i in range(N_KEYS)]  # Zipf-like skew
    trace = []
    for _ in range(N_REQUESTS):
        key = rnd.choices(range(N_KEYS), weights=weights, k=1)[0]
        arrival_delay = rnd.uniform(0.008, 0.02)  # simulated request spacing
        trace.append((key, arrival_delay))
    return trace


def run_trace(trace, cache, label: str, db_latency_seed: int = 123) -> dict:
    db_rnd = random.Random(db_latency_seed)
    db_calls = 0

    def slow_db(key):
        nonlocal db_calls
        db_calls += 1
        time.sleep(db_rnd.uniform(0.005, 0.015))  # simulated DB round-trip
        return {"key": key}

    fetch = cache.intelligent()(slow_db) if cache is not None else slow_db

    latencies = []
    start = time.perf_counter()
    for key, arrival_delay in trace:
        t0 = time.perf_counter()
        fetch(key)
        latencies.append(time.perf_counter() - t0)
        time.sleep(arrival_delay)
    elapsed = time.perf_counter() - start

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    return {
        "label": label,
        "db_calls": db_calls,
        "hit_rate": round(1 - db_calls / len(trace), 3),
        "avg_response_ms": round(statistics.mean(latencies) * 1000, 2),
        "p95_response_ms": round(p95 * 1000, 2),
        "total_wall_s": round(elapsed, 2),
    }


def main() -> None:
    trace = build_trace()
    print(
        f"Replaying {N_REQUESTS} requests over {N_KEYS} keys (Zipf-weighted), "
        "identical trace for each strategy.\n"
    )

    results = [
        run_trace(trace, cache=None, label="No cache"),
        run_trace(
            trace,
            cache=AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=1),
            label="Static TTL=1s",
        ),
        run_trace(
            trace,
            cache=AdaptCache(
                backend="memory",
                adaptive_ttl=True,
                default_ttl=1,
                min_ttl=0.5,
                max_ttl=20,
            ),
            label="Adaptive TTL",
        ),
    ]

    header = f"{'Strategy':<15}{'DB calls':>10}{'Hit rate':>10}{'Avg ms':>9}{'p95 ms':>9}{'Wall s':>9}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['label']:<15}{r['db_calls']:>10}{r['hit_rate']:>10}"
            f"{r['avg_response_ms']:>9}{r['p95_response_ms']:>9}{r['total_wall_s']:>9}"
        )


if __name__ == "__main__":
    main()

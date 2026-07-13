# AdaptCache

[![tests](https://github.com/Ryan5342/adaptcache/actions/workflows/tests.yml/badge.svg)](https://github.com/Ryan5342/adaptcache/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)

A caching decorator for Python functions that adapts each entry's TTL to
how often it's actually reused, instead of one fixed TTL for everything.

> **Status: v0.1, early and honest about it.** This release ships a
> simple, explainable heuristic (recent access frequency), not a trained
> ML model. See [Roadmap](#roadmap) for what's planned vs. what's real today.

## Why

A fixed `TTL=300` either wastes cache space on data nobody re-requests, or
expires popular data too soon. AdaptCache tracks how often each specific call
is reused and adjusts automatically: frequently-reused results get a
longer TTL (up to a cap you set), rarely-reused ones expire fast.

## Install

```bash
pip install adaptcache         # in-memory backend, zero dependencies
pip install adaptcache[redis]  # + Redis backend
```

(Not published to PyPI yet -- for now, install from source: `pip install -e .`.
The name `adaptcache` is confirmed free on PyPI, and the package builds and
passes `twine check` cleanly, so it's ready whenever that's worth doing.)

## Quick start

```python
from adaptcache import AdaptCache

cache = AdaptCache(backend="memory")  # or backend="redis", redis_url="redis://localhost:6379"

@cache.intelligent()
def get_user_profile(user_id: int):
    return db.query(f"SELECT * FROM users WHERE id={user_id}")

get_user_profile(123)  # miss: hits the DB
get_user_profile(123)  # hit: served from cache

get_user_profile.invalidate(123)  # force a fresh read, e.g. right after an UPDATE
print(cache.stats())  # {'hits': 1, 'misses': 1, 'hit_rate': 0.5, 'tracked_keys': 1}

cache.clear()  # wipe everything and reset stats. Raises NotImplementedError
               # on the Redis backend rather than silently leaving stale
               # data behind -- see invalidate_tag() for a scoped version.
```

Run `python demo.py` for a 10-second illustration of how the adaptive TTL
reacts differently to a "hot" key vs. a "cold" key. Run `python
benchmark.py` for real, measured numbers -- see [Benchmark](#benchmark).

## How the v0.1 heuristic works

For each cached call, AdaptCache keeps the last 20 access timestamps and
computes the average gap between them. TTL scales so that frequently
requested calls (short gap) trend toward `max_ttl`, and rarely requested
calls (long gap) trend toward `min_ttl`. It's a few lines of math, not a
model -- see `adaptcache/core.py::_adaptive_ttl`.

## What's cached

Return values must be JSON-serializable: dicts, lists, and primitives.
That covers the common case (API/DB-lookup functions). Arbitrary Python
objects aren't supported in v0.1.

## Tag-based invalidation

Group related cache entries with `tags`, then clear them all at once --
useful when several cached functions read from the same table:

```python
@cache.intelligent(tags=["users"])
def get_user(user_id: int):
    ...

cache.invalidate_tag("users")  # clears every entry tagged "users"
```

Tag membership is tracked in Redis (not just in-process), so this is safe
to call from a different worker/process than the one that populated the
cache -- see `tests/test_redis_backend.py::test_redis_backend_invalidate_tag`.

## Automatic invalidation for SQLAlchemy

If you use SQLAlchemy, `watch_sqlalchemy()` hooks your `Session` so that
any committed INSERT/UPDATE/DELETE automatically invalidates the matching
tag -- no manual `.invalidate()` calls needed:

```python
from adaptcache.ext.sqlalchemy import watch_sqlalchemy

watch_sqlalchemy(cache, Session)  # Session = your sessionmaker(...) class

@cache.intelligent(tags=["users"])
def get_user(user_id: int):
    ...
```

**Scope, honestly:** this only sees writes made through that `Session`
class. Raw SQL run outside the ORM, or writes from another service, aren't
detected -- general DB-agnostic auto-invalidation is still on the roadmap,
not implemented today. Requires `pip install adaptcache[sqlalchemy]`.

## Benchmark

`python benchmark.py` replays one identical trace of 350 requests (50 keys,
Zipf-weighted access, simulated 5-15ms DB latency) against three strategies.
Real run, real wall-clock time, seeded for reproducibility:

```
Strategy         DB calls  Hit rate   Avg ms   p95 ms   Wall s
--------------------------------------------------------------
No cache              350       0.0     9.89    14.57     8.39
Static TTL=1s         121     0.654     3.45    13.34     6.14
Adaptive TTL           97     0.723     2.73    12.86     5.88
```

Adaptive made **~20% fewer DB calls** than a static 1s TTL on this trace
(97 vs. 121), with lower average response latency as a result.

**The honest caveat:** that gap only shows up because 1s is a
*conservative* static TTL -- the kind picked when a team is nervous about
staleness. Re-run the same trace with a *generous* static TTL (e.g. 3s)
and the two strategies tie. There's no headroom left for adaptation to
improve on an already-generous fixed value. So the real pitch isn't
"always faster than static" -- it's "you don't have to guess the right
static TTL per endpoint; it finds a reasonable one automatically, which
matters most when you'd otherwise play it safe with a short one."

This is one synthetic pattern, single-process, in-memory backend -- not a
claim about Redis under concurrent production load.

## Full example: FastAPI + SQLAlchemy

`examples/fastapi_app.py` is a small, real, runnable service tying
everything together -- a cached read, a write through a watched
SQLAlchemy session, and the auto-invalidation firing with no manual
`.invalidate()` call:

```bash
pip install fastapi uvicorn sqlalchemy
uvicorn examples.fastapi_app:app --reload
```

```bash
curl http://localhost:8000/users              # [] -- miss
curl http://localhost:8000/users              # [] -- hit
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d '{"name": "Ana"}'
curl http://localhost:8000/users              # [{"id": 1, "name": "Ana"}] -- miss again, auto-invalidated
```

Covered by its own end-to-end test in `examples/test_fastapi_app.py`, and
by CI on every push (`.github/workflows/tests.yml`, Python 3.9-3.12, with
a real Redis service container).

## Roadmap

- [x] Tag-based invalidation, safe across processes with the Redis backend
- [x] Automatic invalidation for SQLAlchemy sessions
- [ ] Automatic invalidation for raw SQL / other ORMs (general case is
      genuinely harder -- no promises on this one yet)
- [ ] A learned model in place of the heuristic, once there's real usage
      data to justify it
- [ ] Go and Node.js SDKs
- [ ] A small dashboard for hit-rate / latency stats

Unchecked items don't exist yet -- this README won't claim otherwise.

## License

MIT

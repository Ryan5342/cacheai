# Changelog

## v0.1.0 (unreleased)

**Core**
- `@cache.intelligent()` decorator with memory and Redis backends.
- Adaptive TTL heuristic based on recent access frequency (not ML --
  see README for why, and for the benchmark showing when it actually helps).
- `cache.invalidate(func, *args)` for manual eviction.
- `cache.clear()` to wipe everything and reset stats (raises
  `NotImplementedError` on Redis rather than silently leaving stale data).
- `cache.stats()` for hits/misses/hit-rate.

**Concurrency**
- Stress-tested `MemoryBackend` under real threads (not mocks): 300 trials
  of concurrent access to an already-expired key, and 50 trials of
  concurrent hits on the same key checking for lost counter updates.
  Zero failures in either, under standard CPython. Fixed one real
  footgun found along the way regardless: `get()` used `del` on an
  expired key, which could raise `KeyError` if two threads both passed
  the expiry check before either deleted it -- switched to `pop(key, None)`
  to make it idempotent. See README's Thread safety section for the
  honest limits (this relies on the GIL, not explicit locking).

**Invalidation**
- Tag-based invalidation: `@cache.intelligent(tags=[...])` +
  `cache.invalidate_tag(...)`. Safe across processes on the Redis backend
  (tag membership is stored in Redis, not per-process memory).
- `adaptcache.ext.sqlalchemy.watch_sqlalchemy()`: automatic tag invalidation
  when a watched SQLAlchemy `Session` commits a write to a matching table.
  Scoped to that ORM session -- raw SQL or other services aren't detected.

**Validation**
- 23 tests (core, Redis, tags, SQLAlchemy integration, and a full FastAPI
  example) run in CI on Python 3.9-3.12 with a real Redis service container,
  with a 90% coverage floor enforced (currently at 100% on the package
  itself). Coverage work found real gaps: `clear()` existed on both
  backends but was never wired up to the public API until now; constructor
  validation, the non-JSON-serializable error path, and both
  optional-dependency ImportError messages were previously untested.
- `mypy --strict` is clean across the package (found and fixed 12 real
  issues in the process, including a backend interface that had no shared
  type, and two `set`-vs-`.set()`-method naming collisions).
- `ruff`, `black`, and `isort` all clean and enforced in CI. One real
  catch: `pytest.importorskip()` in two test files needs its import to
  come *after* the skip check, which trips a default lint rule -- silenced
  explicitly per-file, with the reasoning written down, instead of
  reordering code that's correct as written.
- Package builds cleanly (`python -m build`) and passes `twine check`;
  installed the built wheel into a throwaway venv and confirmed it
  actually imports and runs. Not published to PyPI yet, but ready to be.
- `benchmark.py`: a real (wall-clock, not mocked) benchmark comparing no
  cache / static TTL / adaptive TTL, with the honest result documented in
  the README -- adaptive wins when the static TTL is conservative, ties
  when it's already generous.
- `examples/fastapi_app.py`: a small runnable service demonstrating the
  full loop (cache a read, write through SQLAlchemy, watch it
  auto-invalidate) end to end.

**Not here yet**
- PyPI release
- A learned model in place of the heuristic
- Go/Node SDKs, a stats dashboard
- General (non-SQLAlchemy) automatic invalidation

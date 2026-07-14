import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient

from examples.fastapi_app import app, cache

client = TestClient(app)


def test_full_cycle_cache_hit_then_auto_invalidate_on_write():
    # First read: cache miss, empty list.
    r1 = client.get("/users")
    assert r1.status_code == 200
    assert r1.json() == []
    misses_after_first = cache.stats()["misses"]

    # Second read: should be a cache hit (misses unchanged).
    r2 = client.get("/users")
    assert r2.json() == []
    assert cache.stats()["misses"] == misses_after_first
    assert cache.stats()["hits"] >= 1

    # Write through the watched Session -- this commit should
    # auto-invalidate the "users" tag with no manual .invalidate() call.
    r3 = client.post("/users", json={"name": "Ana"})
    assert r3.status_code == 200
    assert r3.json()["name"] == "Ana"

    # Next read must be a fresh miss reflecting the new row.
    r4 = client.get("/users")
    assert r4.json() == [{"id": r3.json()["id"], "name": "Ana"}]
    assert cache.stats()["misses"] == misses_after_first + 1


def test_cache_stats_endpoint_reflects_real_state():
    r1 = client.get("/cache-stats")
    assert r1.status_code == 200
    body = r1.json()
    assert set(body.keys()) == {"hits", "misses", "hit_rate", "tracked_keys"}
    assert body["hits"] == cache.stats()["hits"]
    assert body["misses"] == cache.stats()["misses"]

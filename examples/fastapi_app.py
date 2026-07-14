"""A tiny, real, runnable example: a FastAPI service backed by SQLite that
shows AdaptCache's tag-based caching and automatic SQLAlchemy invalidation
working together end to end.

Run it:
    pip install fastapi uvicorn sqlalchemy
    uvicorn examples.fastapi_app:app --reload

Then, in another terminal:
    curl http://localhost:8000/users
    # -> [] (cache miss, "hits the DB")
    curl http://localhost:8000/users
    # -> [] (cache hit, served from cache -- try timing both with `time curl ...`)
    curl -X POST http://localhost:8000/users \
        -H "Content-Type: application/json" -d '{"name": "Ana"}'
    curl http://localhost:8000/users
    # -> [{"id": 1, "name": "Ana"}]  (miss again: the POST's commit
    #     auto-invalidated the "users" tag, no manual .invalidate() call)
    curl http://localhost:8000/cache-stats
"""

from __future__ import annotations

import time
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from adaptcache import AdaptCache
from adaptcache.ext.sqlalchemy import watch_sqlalchemy

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)


# StaticPool keeps ONE shared connection alive for the whole engine.
# Without it, an in-memory SQLite DB is private to whichever connection
# created it -- and FastAPI runs sync path functions in a thread pool, so a
# later request landing on a different thread would silently see an empty,
# table-less database.
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

cache = AdaptCache(
    backend="memory", adaptive_ttl=True, default_ttl=30, min_ttl=5, max_ttl=300
)
watch_sqlalchemy(
    cache, Session
)  # commits through this Session auto-invalidate tagged entries

app = FastAPI(title="adaptcache example")


class UserIn(BaseModel):
    name: str


@cache.intelligent(tags=["users"])
def _fetch_all_users() -> List[dict]:
    # Stands in for a real, slower query -- the point of caching is you
    # only pay this cost on a miss.
    time.sleep(0.05)
    session = Session()
    try:
        return [{"id": u.id, "name": u.name} for u in session.query(User).all()]
    finally:
        session.close()


@app.get("/users")
def list_users():
    return _fetch_all_users()


@app.post("/users")
def create_user(user: UserIn):
    session = Session()
    try:
        row = User(name=user.name)
        session.add(row)
        session.commit()  # this commit is what triggers auto-invalidation
        session.refresh(row)
        return {"id": row.id, "name": row.name}
    finally:
        session.close()


@app.get("/cache-stats")
def cache_stats():
    return cache.stats()

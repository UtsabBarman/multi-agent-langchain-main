from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engines: dict[str, Any] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}


def create_engine(connection_url: str, key: str = "default") -> Any:
    """Create async engine and session factory for the given URL. Cached by key."""
    if key in _engines:
        return _engines[key]
    engine = create_async_engine(
        connection_url,
        echo=False,
        pool_pre_ping=True,
    )
    _engines[key] = engine
    _session_factories[key] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    return engine


def get_engine(key: str = "default"):
    return _engines.get(key)


def get_session_factory(key: str = "default"):
    return _session_factories.get(key)


@asynccontextmanager
async def get_session(connection_url: str | None = None, key: str = "default") -> AsyncGenerator[AsyncSession, None]:
    if connection_url is not None:
        create_engine(connection_url, key=key)
    factory = _session_factories.get(key)
    if not factory:
        raise ValueError(f"No session factory for key {key}. Call create_engine first.")
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

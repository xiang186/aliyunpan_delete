"""
Database initialization and session management.

Provides:
  - Async SQLAlchemy engine backed by aiosqlite
  - AsyncSessionLocal: session factory for use in services
  - get_db(): FastAPI dependency that yields an AsyncSession
  - init_db(): startup coroutine that creates all tables and ensures the
               data directory exists
"""
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_async_url(url: str) -> str:
    """Convert a plain sqlite:/// URL to the aiosqlite variant."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _ensure_data_dir(url: str) -> None:
    """Create the parent directory for a SQLite file if it does not exist."""
    # Strip the driver prefix to get the file path
    # e.g. "sqlite:///./data/app.db" -> "./data/app.db"
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            db_path = url[len(prefix):]
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            return


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

_async_url = _make_async_url(settings.database_url)

engine = create_async_engine(
    _async_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Declarative base (imported by models.py)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables on startup, auto-creating the data directory first."""
    _ensure_data_dir(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request."""
    async with AsyncSessionLocal() as session:
        yield session

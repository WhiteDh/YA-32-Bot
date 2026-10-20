"""Async engine + session factory, and running Alembic migrations at startup."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite creates the file but not its folder (``./data`` on a fresh clone)."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        parsed = make_url(url)
        kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
        if parsed.get_backend_name() == "sqlite":
            _ensure_sqlite_dir(url)
        else:
            # The bot is used rarely: a tiny pool, recycled before Postgres idles it out.
            kwargs.update(pool_size=3, max_overflow=2, pool_recycle=1800)
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        if parsed.get_backend_name() == "sqlite":
            event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> AsyncSession:
        return self.sessionmaker()

    async def dispose(self) -> None:
        await self.engine.dispose()


def _sqlite_pragmas(dbapi_conn: object, _record: object) -> None:
    cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _upgrade(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["url_from_code"] = True
    cfg.attributes["skip_logging"] = True  # keep the bot's logging setup intact
    command.upgrade(cfg, "head")


async def migrate(url: str) -> None:
    """``alembic upgrade head`` in a worker thread (env.py runs its own event loop)."""
    logger.info("applying migrations")
    _ensure_sqlite_dir(url)  # migrations open the database before Database() would create the folder
    await asyncio.to_thread(_upgrade, url)

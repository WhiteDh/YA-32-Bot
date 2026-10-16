"""Tiny typed access to the ``kv`` table."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.db.models import KeyValue


async def kv_get(session: AsyncSession, key: str) -> dict[str, Any]:
    row = await session.get(KeyValue, key)
    return dict(row.value) if row else {}


async def kv_set(session: AsyncSession, key: str, value: dict[str, Any]) -> None:
    row = await session.get(KeyValue, key)
    if row is None:
        session.add(KeyValue(key=key, value=value))
    else:
        row.value = value
    await session.flush()

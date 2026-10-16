"""Edit journal with undo.

Every schedule edit records the inverse operations it needs: an insert is undone by a
delete, a delete by re-inserting the saved row, an update by restoring old values.
Rows are serialised to JSON-friendly dicts and rehydrated by column type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.db.models import AuditLog, Base, Holiday, Homework, Override, Subject, TemplateLesson

TABLES: dict[str, type[Base]] = {
    m.__tablename__: m for m in (Override, TemplateLesson, Homework, Holiday, Subject)
}  # fmt: skip


def row_to_dict(row: Base) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.key)
        if isinstance(value, date | datetime):
            value = value.isoformat()
        out[column.key] = value
    return out


def _hydrate(model: type[Base], data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    columns = {c.key: c for c in model.__table__.columns}
    for key, value in data.items():
        column = columns.get(key)
        if column is None:
            continue
        if value is not None and isinstance(column.type, DateTime):
            value = datetime.fromisoformat(value)
        elif value is not None and isinstance(column.type, Date):
            value = date.fromisoformat(value)
        out[key] = value
    return out


@dataclass
class Change:
    """Collects inverse operations while an edit runs; ``commit`` writes the journal row."""

    action: str
    summary: str = ""
    ops: list[dict[str, Any]] = field(default_factory=list)

    def inserted(self, row: Base) -> None:
        self.ops.append({"op": "insert", "table": row.__tablename__, "pk": _pk(row)})

    def deleted(self, row: Base) -> None:
        self.ops.append({"op": "delete", "table": row.__tablename__, "row": row_to_dict(row)})

    def updated(self, row: Base, before: dict[str, Any]) -> None:
        self.ops.append({"op": "update", "table": row.__tablename__, "pk": _pk(row), "before": before})


def _pk(row: Base) -> Any:
    return row.__mapper__.primary_key_from_instance(row)[0]


async def record(session: AsyncSession, user_id: int | None, change: Change) -> AuditLog:
    entry = AuditLog(user_id=user_id, action=change.action, summary=change.summary, payload={"ops": change.ops})
    session.add(entry)
    await session.flush()
    return entry


async def recent(session: AsyncSession, limit: int = 10) -> list[AuditLog]:
    rows = await session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return list(rows.all())


async def undo(session: AsyncSession, entry_id: int) -> AuditLog | None:
    """Apply the inverse operations of one journal entry, newest first. ``None`` if not undoable."""
    entry = await session.get(AuditLog, entry_id)
    if entry is None or entry.undone:
        return None
    for op in reversed(entry.payload.get("ops", [])):
        model = TABLES.get(op.get("table", ""))
        if model is None:
            continue
        if op["op"] == "insert":
            row = await session.get(model, op["pk"])
            if row is not None:
                await session.delete(row)
        elif op["op"] == "delete":
            session.add(model(**_hydrate(model, op["row"])))
        elif op["op"] == "update":
            row = await session.get(model, op["pk"])
            if row is not None:
                for key, value in _hydrate(model, op["before"]).items():
                    setattr(row, key, value)
        await session.flush()
    entry.undone = True
    await session.flush()
    return entry

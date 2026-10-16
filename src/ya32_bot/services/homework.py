"""Homework: create, list, personal "done" marks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.db.models import Homework, HomeworkDone
from ya32_bot.services import audit


@dataclass(frozen=True, slots=True)
class HomeworkItem:
    hw: Homework
    done: bool


async def create(
    session: AsyncSession,
    *,
    subject: str,
    due_date: date,
    slot: int | None,
    text: str,
    attachments: list[dict[str, Any]],
    author_id: int | None,
) -> Homework:
    row = Homework(
        subject=subject, due_date=due_date, slot=slot, text=text.strip(), attachments=attachments, author_id=author_id
    )
    session.add(row)
    await session.flush()
    change = audit.Change("homework_add", f"ДЗ: {subject} на {due_date:%d.%m}")
    change.inserted(row)
    await audit.record(session, author_id, change)
    return row


async def update_text(session: AsyncSession, row: Homework, text: str, user_id: int | None) -> None:
    before = audit.row_to_dict(row)
    row.text = text.strip()
    change = audit.Change("homework_edit", f"ДЗ змінено: {row.subject} на {row.due_date:%d.%m}")
    change.updated(row, before)
    await session.flush()
    await audit.record(session, user_id, change)


async def remove(session: AsyncSession, row: Homework, user_id: int | None) -> None:
    await session.execute(delete(HomeworkDone).where(HomeworkDone.homework_id == row.id))
    change = audit.Change("homework_delete", f"ДЗ видалено: {row.subject} на {row.due_date:%d.%m}")
    change.deleted(row)
    await session.delete(row)
    await session.flush()
    await audit.record(session, user_id, change)


async def upcoming(
    session: AsyncSession, user_id: int, today: date, *, include_done: bool = True
) -> list[HomeworkItem]:
    rows = (
        await session.scalars(
            select(Homework).where(Homework.due_date >= today).order_by(Homework.due_date, Homework.slot)
        )
    ).all()
    done = await done_ids(session, user_id, [r.id for r in rows])
    items = [HomeworkItem(r, r.id in done) for r in rows]
    return items if include_done else [i for i in items if not i.done]


async def for_subject(session: AsyncSession, subject: str, today: date, limit: int = 5) -> list[Homework]:
    rows = await session.scalars(
        select(Homework)
        .where(and_(Homework.subject == subject, Homework.due_date >= today))
        .order_by(Homework.due_date)
        .limit(limit)
    )
    return list(rows.all())


async def due_on(session: AsyncSession, day: date) -> list[Homework]:
    return list((await session.scalars(select(Homework).where(Homework.due_date == day).order_by(Homework.slot))).all())


async def done_ids(session: AsyncSession, user_id: int, homework_ids: list[int]) -> set[int]:
    if not homework_ids:
        return set()
    rows = await session.scalars(
        select(HomeworkDone.homework_id).where(
            HomeworkDone.user_id == user_id, HomeworkDone.homework_id.in_(homework_ids)
        )
    )
    return set(rows.all())


async def toggle_done(session: AsyncSession, user_id: int, homework_id: int) -> bool:
    """Flip the mark; returns the new state."""
    row = await session.get(HomeworkDone, (user_id, homework_id))
    if row is not None:
        await session.delete(row)
        await session.flush()
        return False
    session.add(HomeworkDone(user_id=user_id, homework_id=homework_id))
    await session.flush()
    return True


async def done_count(session: AsyncSession, homework_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(HomeworkDone).where(HomeworkDone.homework_id == homework_id)
        )
        or 0
    )

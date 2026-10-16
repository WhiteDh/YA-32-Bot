from dataclasses import replace
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import NOW, kpi_payload, kpi_schedule
from ya32_bot.db.models import TemplateLesson
from ya32_bot.services import audit, schedule, semester, sync
from ya32_bot.services.sources.kpi import parse_lessons


async def _count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(TemplateLesson)) or 0)


def test_kpi_parser_reads_the_real_response():
    lessons, warnings = parse_lessons(kpi_payload())
    assert warnings == []
    assert len(lessons) == 34
    tuesday = [x for x in lessons if x.weekday == 1 and x.week == 1]  # KPI spells Tuesday "Вв"
    assert {x.slot for x in tuesday} == {2, 3, 4}
    invest = next(x for x in lessons if x.week == 1 and x.weekday == 0 and x.slot == 1)
    assert invest.kind == "lec" and invest.dates[0] == date(2026, 9, 14)
    practice = next(x for x in lessons if x.week == 1 and x.weekday == 2 and x.slot == 2)
    assert practice.room == "17-214" and practice.room_url == "https://kpi.ua/k-17" and practice.dates == ()


def test_fingerprint_is_order_independent():
    a = kpi_schedule()
    b = replace(a, lessons=tuple(reversed(a.lessons)))
    assert sync.fingerprint(a) == sync.fingerprint(b)


async def test_append_imports_everything_and_sets_week(session: AsyncSession):
    result = await sync.apply(session, kpi_schedule(), sync.SyncMode.APPEND, user_id=None, today=NOW.date(), now=NOW)
    assert result.added == 34 and result.week_set == 2
    assert (await semester.get_anchor(session, NOW.date())).week_of(NOW.date()) == 2
    assert (await sync.diff(session, kpi_schedule())).empty


async def test_update_keeps_manual_edits_and_follows_kpi(session: AsyncSession):
    await sync.apply(session, kpi_schedule(), sync.SyncMode.APPEND, user_id=None, today=NOW.date(), now=NOW)
    rows = (await session.scalars(select(TemplateLesson).order_by(TemplateLesson.id))).all()
    manual, kpi_row = rows[0], rows[1]
    await schedule.template_update(session, manual, {"teacher": "Наш викладач"}, None)
    kpi_row.teacher = "Хтось інший"
    stale = TemplateLesson(week=1, weekday=5, slot=1, subject="Зник", kind="lec", dates=[], source="kpi")
    session.add(stale)
    await session.flush()

    diff = await sync.diff(session, kpi_schedule())
    assert [c.row_id for c in diff.changed] == [kpi_row.id]
    assert [r.subject for r in diff.removed] == ["Зник"]

    result = await sync.apply(session, kpi_schedule(), sync.SyncMode.UPDATE, user_id=None, today=NOW.date(), now=NOW)
    assert (result.changed, result.removed) == (1, 1)
    await session.refresh(manual)
    assert manual.teacher == "Наш викладач" and manual.source == "manual"


async def test_reload_replaces_and_is_undoable(session: AsyncSession):
    await sync.apply(session, kpi_schedule(), sync.SyncMode.APPEND, user_id=None, today=NOW.date(), now=NOW)
    await schedule.template_add(session, 1, 5, 3, schedule.LessonFields(subject="Суботник"), None)
    assert await _count(session) == 35

    result = await sync.apply(session, kpi_schedule(), sync.SyncMode.RELOAD, user_id=None, today=NOW.date(), now=NOW)
    assert await _count(session) == 34 and result.journal_id is not None

    await audit.undo(session, result.journal_id)
    assert await _count(session) == 35
    assert await session.scalar(select(TemplateLesson).where(TemplateLesson.subject == "Суботник")) is not None

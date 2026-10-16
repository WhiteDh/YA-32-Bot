from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import NOW
from ya32_bot.bot.context import AppContext
from ya32_bot.db.models import Role, TemplateLesson
from ya32_bot.services import audit, homework, schedule, semester, users

MON = NOW.date()  # 5 Oct 2026, week 2


async def _day(session: AsyncSession, when: date):
    return (await schedule.day(session, when, today=MON)).day


async def test_seeded_monday_matches_kpi(seeded: AppContext):
    async with seeded.db.session() as session:
        day = await _day(session, MON)
    assert [(x.slot, x.subject) for x in day.lessons] == [
        (1, "Інвестиційний аналіз"),
        (2, "Інвестиційний аналіз"),
        (3, "Аналітика та реінжиніринг бізнес-процесів"),
        (4, "Аналітика та реінжиніринг бізнес-процесів"),
    ]
    assert day.week == 2


async def test_lecture_with_dates_disappears_after_its_last_date(seeded: AppContext):
    async with seeded.db.session() as session:
        late = await _day(session, date(2026, 11, 30))  # week 2 Monday, lecture dates ended 02.11
    assert [x.slot for x in late.lessons] == [2, 4]


async def test_cancel_put_move_restore_and_undo(seeded: AppContext):
    async with seeded.db.session() as session:
        await schedule.cancel(session, MON, 1, None, note="хворіє")
        assert (await _day(session, MON)).lessons[0].cancelled

        entry = await schedule.put(session, MON, 1, schedule.LessonFields(subject="Заміна"), None)
        first = (await _day(session, MON)).lessons[0]
        assert first.subject == "Заміна" and not first.cancelled

        await audit.undo(session, entry)
        assert (await _day(session, MON)).lessons[0].cancelled

        await schedule.restore(session, MON, 1, None)
        assert not (await _day(session, MON)).lessons[0].changed

        lesson = (await _day(session, MON)).lessons[2]
        await schedule.move(session, lesson, MON + timedelta(days=1), 1, None)
        assert (await _day(session, MON)).lessons[2].cancelled
        tuesday = await _day(session, MON + timedelta(days=1))
        assert tuesday.lessons[0].slot == 1 and tuesday.lessons[0].subject == lesson.subject


async def test_template_edit_marks_row_manual_and_undo_restores(seeded: AppContext):
    async with seeded.db.session() as session:
        row = await session.get(TemplateLesson, 1)
        assert row is not None and row.source == "kpi"
        await schedule.template_update(session, row, {"teacher": "Новий"}, None)
        assert row.source == "manual"
        entry = (await audit.recent(session, 1))[0]
        await audit.undo(session, entry.id)
        await session.refresh(row)
        assert row.source == "kpi" and row.teacher != "Новий"
        assert await audit.undo(session, entry.id) is None  # twice is a no-op


async def test_holiday_blanks_the_day(seeded: AppContext):
    async with seeded.db.session() as session:
        await semester.add_holiday(session, MON, MON, "Свято")
        day = await _day(session, MON)
    assert day.holiday == "Свято" and not day.lessons


async def test_homework_flow(seeded: AppContext):
    async with seeded.db.session() as session:
        await users.touch(session, 1, "A", None, [])
        hw = await homework.create(
            session, subject="Економічна аналітика", due_date=MON + timedelta(days=1), slot=4, text="№1-3",
            attachments=[], author_id=1,
        )  # fmt: skip
        items = await homework.upcoming(session, 1, MON)
        assert [i.done for i in items] == [False]
        assert await homework.toggle_done(session, 1, hw.id) is True
        assert await homework.upcoming(session, 1, MON, include_done=False) == []
        assert await homework.done_count(session, hw.id) == 1
        bundle = await schedule.day(session, MON + timedelta(days=1), today=MON)
        assert bundle.homework["Економічна аналітика"][0].text == "№1-3"
        await homework.remove(session, hw, 1)
        assert await homework.upcoming(session, 1, MON) == []


async def test_owner_from_env_and_invites_never_demote(session: AsyncSession):
    owner, created = await users.touch(session, 10, "Owner", None, [10])
    assert created and owner.role_enum is Role.OWNER
    student, _ = await users.touch(session, 20, "Stud", None, [10])
    invite = await users.create_invite(session, Role.EDITOR, owner.id)
    assert await users.redeem_invite(session, invite.code, student) is Role.EDITOR
    assert student.role_enum is Role.EDITOR
    assert await users.redeem_invite(session, invite.code, student) is None  # single use

    admin_invite = await users.create_invite(session, Role.STUDENT, owner.id)
    await users.redeem_invite(session, admin_invite.code, owner)
    assert owner.role_enum is Role.OWNER

    expired = await users.create_invite(session, Role.ADMIN, owner.id)
    later = datetime.now(UTC) + timedelta(days=8)
    assert await users.redeem_invite(session, expired.code, student, now=later) is None

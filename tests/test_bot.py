"""End-to-end: real dispatcher, real handlers, SQLite, a fake Telegram that records calls."""

from __future__ import annotations

from datetime import datetime
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Chat, InlineQuery, Message, Update
from aiogram.types import User as TgUser

from tests.conftest import NOW, OWNER_ID, STUDENT_ID, FakeSession
from ya32_bot.app import build_dispatcher
from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Adm, DayCb, HwCb, SetCb, d2i
from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import Override, Role, User
from ya32_bot.services import homework, users

_ids = count(1)


def _user(uid: int) -> TgUser:
    return TgUser(id=uid, is_bot=False, first_name=f"U{uid}")


def msg(uid: int, text: str) -> Update:
    return Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids), date=datetime(2026, 10, 5), chat=Chat(id=uid, type="private"),
            from_user=_user(uid), text=text,
        ),
    )  # fmt: skip


def cb(uid: int, data: str) -> Update:
    message = Message(message_id=500, date=datetime(2026, 10, 5), chat=Chat(id=uid, type="private"), text="old")
    return Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(
            id=str(next(_ids)), from_user=_user(uid), chat_instance="x", data=data, message=message
        ),
    )


@pytest.fixture
def dp(seeded: AppContext) -> Dispatcher:
    ui.RICH.enabled = True
    return build_dispatcher(seeded)


async def feed(dp: Dispatcher, bot: Bot, update: Update) -> None:
    await dp.feed_update(bot, update)


async def test_quick_tap_after_a_message_is_not_throttled(dp, bot, fake_session: FakeSession):
    await feed(dp, bot, msg(STUDENT_ID, "/today"))
    await feed(dp, bot, cb(STUDENT_ID, DayCb(d=d2i(NOW.date())).pack()))
    assert fake_session.of("EditMessageText")


async def _role(ctx: AppContext, uid: int, role: Role) -> None:
    async with ctx.db.session() as session:
        await users.touch(session, uid, "x", None, [])
        await users.set_role(session, uid, role)
        await session.commit()


async def test_start_makes_env_owner_and_shows_menu(dp, bot, fake_session: FakeSession, seeded: AppContext):
    await feed(dp, bot, msg(OWNER_ID, "/start"))
    async with seeded.db.session() as session:
        owner = await session.get(User, OWNER_ID)
    assert owner is not None and owner.role_enum is Role.OWNER
    assert any("Вітаю" in t for t in fake_session.texts())
    assert fake_session.of("SendRichMessage"), "menu goes out as a rich message"
    assert fake_session.of("SetMyCommands"), "admin commands published for the new owner"


async def test_today_button_renders_schedule(dp, bot, fake_session: FakeSession):
    await feed(dp, bot, msg(STUDENT_ID, "📅 Сьогодні"))
    html = fake_session.texts()[-1]
    assert "Інвестиційний аналіз" in html and "2-й тиждень" in html


async def test_rich_refusal_falls_back_to_classic_html(dp, bot, fake_session: FakeSession):
    fake_session.refuse.add("SendRichMessage")
    await feed(dp, bot, msg(STUDENT_ID, "/today"))
    assert fake_session.of("SendMessage") and not ui.RICH.enabled
    ui.RICH.enabled = True


async def test_typed_date_and_day_arrows(dp, bot, fake_session: FakeSession):
    await feed(dp, bot, msg(STUDENT_ID, "07.10"))
    assert "Середа" in fake_session.texts()[-1]
    await feed(dp, bot, cb(STUDENT_ID, DayCb(d=d2i(NOW.date()), step=1).pack()))
    assert fake_session.of("EditMessageText")


async def test_settings_toggle_persists(dp, bot, seeded: AppContext):
    await feed(dp, bot, cb(STUDENT_ID, SetCb(a="tog", k="show_room", v="view").pack()))
    async with seeded.db.session() as session:
        student = await session.get(User, STUDENT_ID)
    assert student is not None and Prefs.load(student.prefs).show_room is True


async def test_student_cannot_use_admin_buttons(dp, bot, fake_session: FakeSession, seeded: AppContext):
    await feed(dp, bot, cb(STUDENT_ID, Adm(a="cancel", d=d2i(NOW.date()), s=1).pack()))
    answers = fake_session.of("AnswerCallbackQuery")
    assert answers and "Недостатньо прав" in (answers[-1].text or "")  # type: ignore[attr-defined]
    async with seeded.db.session() as session:
        assert await session.get(Override, 1) is None


async def test_admin_cancels_a_pair(dp, bot, seeded: AppContext):
    await _role(seeded, OWNER_ID, Role.ADMIN)
    await feed(dp, bot, cb(OWNER_ID, Adm(a="cancel", d=d2i(NOW.date()), s=1).pack()))
    async with seeded.db.session() as session:
        override = await session.get(Override, 1)
    assert override is not None and override.action == "cancel"


async def test_admin_renames_a_pair_through_text_input(dp, bot, seeded: AppContext):
    await _role(seeded, OWNER_ID, Role.ADMIN)
    await feed(dp, bot, cb(OWNER_ID, Adm(a="field", d=d2i(NOW.date()), s=2, v="subject").pack()))
    await feed(dp, bot, msg(OWNER_ID, "Консультація"))
    async with seeded.db.session() as session:
        override = await session.get(Override, 1)
    assert override is not None and override.subject == "Консультація"


async def test_navigation_button_abandons_pending_input(dp, bot, seeded: AppContext):
    await _role(seeded, OWNER_ID, Role.ADMIN)
    await feed(dp, bot, cb(OWNER_ID, Adm(a="field", d=d2i(NOW.date()), s=2, v="subject").pack()))
    await feed(dp, bot, msg(OWNER_ID, "📅 Сьогодні"))
    async with seeded.db.session() as session:
        assert await session.get(Override, 1) is None


async def test_editor_adds_homework(dp, bot, seeded: AppContext, fake_session: FakeSession):
    await _role(seeded, OWNER_ID, Role.EDITOR)
    await feed(dp, bot, cb(OWNER_ID, HwCb(a="pick", d=d2i(NOW.date()), s=2).pack()))
    await feed(dp, bot, msg(OWNER_ID, "Задачі 1–5"))
    await feed(dp, bot, cb(OWNER_ID, "hw_save"))
    async with seeded.db.session() as session:
        items = await homework.upcoming(session, OWNER_ID, NOW.date())
    assert [i.hw.text for i in items] == ["Задачі 1–5"]


async def test_kpi_sync_from_the_bot(dp, bot, seeded: AppContext, fake_session: FakeSession):
    await _role(seeded, OWNER_ID, Role.ADMIN)
    await feed(dp, bot, cb(OWNER_ID, Adm(a="sychk").pack()))
    assert any("Усе збігається" in t for t in fake_session.texts())


async def test_inline_query_offers_today(dp, bot, fake_session: FakeSession):
    update = Update(
        update_id=next(_ids), inline_query=InlineQuery(id="q", from_user=_user(STUDENT_ID), query="", offset="")
    )
    await feed(dp, bot, update)
    answer = fake_session.of("AnswerInlineQuery")[-1]
    titles = [r.title for r in answer.results]  # type: ignore[attr-defined]
    assert "📅 Сьогодні" in titles and "🗓 Цей тиждень" in titles


async def test_easter_egg_secrets(dp, bot, fake_session: FakeSession):
    await feed(dp, bot, msg(STUDENT_ID, "/42"))
    await feed(dp, bot, msg(STUDENT_ID, "/secrets"))
    assert "Знайдено пасхалок: <b>2 з" in fake_session.texts()[-1]


async def test_inline_users_are_not_registered(dp, bot, seeded: AppContext):
    update = Update(update_id=next(_ids), inline_query=InlineQuery(id="q2", from_user=_user(777), query="", offset=""))
    await feed(dp, bot, update)
    async with seeded.db.session() as session:
        assert await session.get(User, 777) is None

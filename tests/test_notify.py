from datetime import datetime

from aiogram import Bot

from tests.conftest import FakeSession
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.notify import Notifier
from ya32_bot.bot.render.doc import Doc
from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import User
from ya32_bot.services import users


async def _people(ctx: AppContext, *prefs: Prefs) -> None:
    async with ctx.db.session() as session:
        for i, p in enumerate(prefs, start=1):
            user, _ = await users.touch(session, i, f"U{i}", None, [])
            users.save_prefs(user, p)
        await session.commit()


async def test_morning_digest_once_and_only_for_subscribers(seeded: AppContext, bot: Bot, fake_session: FakeSession):
    await _people(seeded, Prefs(morning_time="07:30", remind_before=0), Prefs(morning_digest=False, remind_before=0))
    notifier = Notifier(bot, seeded)
    await notifier.tick(datetime(2026, 10, 5, 7, 30))
    await notifier.tick(datetime(2026, 10, 5, 7, 30))
    sent = fake_session.of("SendRichMessage")
    assert [m.chat_id for m in sent] == [1]  # type: ignore[attr-defined]
    assert "Доброго ранку" in sent[0].rich_message.html  # type: ignore[attr-defined]


async def test_reminder_before_pair_and_quiet_hours_are_silent(seeded: AppContext, bot: Bot, fake_session: FakeSession):
    await _people(seeded, Prefs(morning_digest=False, remind_before=10, quiet_from="08:00", quiet_to="09:00"))
    notifier = Notifier(bot, seeded)
    seeded.clock.now = datetime(2026, 10, 5, 8, 20)  # type: ignore[union-attr]
    await notifier.tick(datetime(2026, 10, 5, 8, 20))
    sent = fake_session.of("SendRichMessage")
    assert len(sent) == 1 and "1 пара" in sent[0].rich_message.html  # type: ignore[attr-defined]
    assert sent[0].disable_notification is True  # type: ignore[attr-defined]


async def test_blocked_user_is_marked(seeded: AppContext, bot: Bot, fake_session: FakeSession):
    await _people(seeded, Prefs())
    fake_session.forbid.add("SendRichMessage")
    notifier = Notifier(bot, seeded)
    async with seeded.db.session() as session:
        user = await session.get(User, 1)
    assert user is not None
    assert await notifier.deliver(user, Doc().h("x")) is False
    async with seeded.db.session() as session:
        refreshed = await session.get(User, 1)
    assert refreshed is not None and refreshed.blocked

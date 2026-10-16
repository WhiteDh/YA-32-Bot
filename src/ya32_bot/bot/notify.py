"""The bot speaking first: digests, reminders, change and homework announcements.

* Delivery honours quiet hours (sent silently) and marks users who blocked the bot.
* Schedule changes are **debounced**: an admin usually edits several things in a row,
  so the group gets one «🔔 Зміна в розкладі» per day, ``CHANGE_DELAY`` after the last edit.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import DayCb, HwCb, LessonCb, Nav, d2i
from ya32_bot.bot.keyboards.common import btn, kb, url_btn
from ya32_bot.bot.render import schedule as render_schedule
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.render.homework import countdown
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import human_day, plural
from ya32_bot.db.models import Homework, Role, User
from ya32_bot.services import homework, schedule, users

logger = logging.getLogger(__name__)

CHANGE_DELAY = 90.0  # seconds of quiet after the last edit before announcing
CHANGE_HORIZON = 7  # only changes within the next week are worth a ping
SEND_PAUSE = 0.05  # ~20 messages/s, well under Telegram's limits


class Notifier:
    def __init__(self, bot: Bot, ctx: AppContext) -> None:
        self.bot = bot
        self.ctx = ctx
        self._pending: dict[date, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._sent: set[tuple[int, str]] = set()  # dedup for reminders/digests: (user, key)
        self._sent_day: date | None = None

    # ── plumbing ───────────────────────────────────────────────────────────

    def _spawn(self, coro: object) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro)  # type: ignore[arg-type]
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def deliver(
        self, user: User, doc: Doc, markup: InlineKeyboardMarkup | None = None, *, prefs: Prefs | None = None
    ) -> bool:
        prefs = prefs or users.prefs_of(user)
        silent = prefs.is_quiet(self.ctx.now().time())
        for attempt in range(2):
            try:
                await ui.send(self.bot, user.id, doc, markup, rich=prefs.rich, silent=silent)
                return True
            except TelegramRetryAfter as exc:
                if attempt:
                    return False
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramForbiddenError:
                await self._mark_blocked(user.id)
                return False
            except TelegramBadRequest:
                logger.warning("delivery to %s failed", user.id, exc_info=True)
                return False
        return False

    async def _mark_blocked(self, user_id: int) -> None:
        async with self.ctx.db.session() as session:
            row = await session.get(User, user_id)
            if row is not None:
                row.blocked = True
                await session.commit()

    async def broadcast(
        self,
        build: Callable[[User, Prefs], tuple[Doc, InlineKeyboardMarkup | None] | None],
        *,
        exclude: int | None = None,
    ) -> int:
        async with self.ctx.db.session() as session:
            people = await users.all_users(session)
        sent = 0
        for person in people:
            if person.id == exclude:
                continue
            prefs = users.prefs_of(person)
            built = build(person, prefs)
            if built is None:
                continue
            if await self.deliver(person, *built, prefs=prefs):
                sent += 1
            await asyncio.sleep(SEND_PAUSE)
        return sent

    # ── announcements ──────────────────────────────────────────────────────

    def schedule_changed(self, when: date, *, exclude: int | None = None) -> None:
        today = self.ctx.today()
        if not today <= when <= today + timedelta(days=CHANGE_HORIZON):
            return
        old = self._pending.pop(when, None)
        if old is not None:
            old.cancel()
        task = asyncio.create_task(self._announce_change(when, exclude))
        self._pending[when] = task

    async def _announce_change(self, when: date, exclude: int | None) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(CHANGE_DELAY)
            self._pending.pop(when, None)
            async with self.ctx.db.session() as session:
                bundle = await schedule.day(session, when, today=self.ctx.today())

            def build(_user: User, prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup] | None:
                if not prefs.notify_changes:
                    return None
                doc = Doc().h("🔔 Зміна в розкладі")
                doc.extend(render_schedule.day_doc(bundle, prefs, today=self.ctx.today(), title=human_day(when)))
                return doc, kb([btn("📅 Відкрити день", DayCb(d=d2i(when)))])

            count = await self.broadcast(build, exclude=exclude)
            logger.info("change on %s announced to %d user(s)", when, count)

    def homework_added(self, homework_id: int, *, exclude: int | None = None) -> None:
        self._spawn(self._announce_homework(homework_id, exclude))

    async def _announce_homework(self, homework_id: int, exclude: int | None) -> None:
        async with self.ctx.db.session() as session:
            hw = await session.get(Homework, homework_id)
        if hw is None:
            return
        today = self.ctx.today()

        def build(_user: User, prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup] | None:
            if not prefs.notify_homework:
                return None
            text = hw.text if len(hw.text) <= 300 else hw.text[:299] + "…"
            doc = (
                Doc()
                .h("📚 Нова домашка")
                .quote(
                    f"<b>{esc(hw.subject)}</b> · до {hw.due_date:%d.%m} ({countdown(hw.due_date, today)})",
                    esc(text) if text else "<i>див. вкладення</i>",
                )
            )
            return doc, kb([btn("📖 Відкрити", HwCb(a="open", id=hw.id), "success")])

        await self.broadcast(build, exclude=exclude)

    async def announce(self, text: str, *, author: User) -> int:
        def build(_user: User, _prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
            doc = Doc().h("📣 Оголошення").p(esc(text)).p(f"<i>— {esc(author.first_name)}</i>")
            return doc, kb([btn("🏠 Меню", Nav(to="menu"))])

        return await self.broadcast(build)

    async def to_admins(self, doc: Doc, markup: InlineKeyboardMarkup | None = None) -> None:
        async with self.ctx.db.session() as session:
            admins = await users.by_role(session, Role.ADMIN)
        for admin in admins:
            await self.deliver(admin, doc, markup)

    # ── the minute tick: digests, deadlines, reminders ─────────────────────

    def _once(self, user_id: int, key: str, today: date) -> bool:
        if self._sent_day != today:
            self._sent.clear()
            self._sent_day = today
        if (user_id, key) in self._sent:
            return False
        self._sent.add((user_id, key))
        return True

    async def tick(self, now: datetime | None = None) -> None:
        now = now or self.ctx.now()
        today = now.date()
        hhmm = f"{now:%H:%M}"
        async with self.ctx.db.session() as session:
            people = await users.all_users(session)
            if not people:
                return
            today_bundle = await schedule.day(session, today, today=today)
            tomorrow_bundle = await schedule.day(session, today + timedelta(days=1), today=today)
            due_tomorrow = await homework.due_on(session, today + timedelta(days=1))
            done_by_user = {
                p.id: await homework.done_ids(session, p.id, [h.id for h in due_tomorrow]) for p in people
            } if due_tomorrow else {}  # fmt: skip

        for person in people:
            prefs = users.prefs_of(person)
            try:
                await self._tick_user(
                    person, prefs, now, hhmm, today_bundle, tomorrow_bundle, due_tomorrow, done_by_user
                )
            except Exception:  # one user must never stop the others
                logger.exception("tick failed for %s", person.id)

    async def _tick_user(
        self, person: User, prefs: Prefs, now: datetime, hhmm: str, today_bundle: schedule.DayBundle,
        tomorrow_bundle: schedule.DayBundle, due_tomorrow: list[Homework], done_by_user: dict[int, set[int]],
    ) -> None:  # fmt: skip
        today = now.date()
        morning = prefs.morning_digest and hhmm == prefs.morning_time and today_bundle.day.active
        if morning and self._once(person.id, "morning", today):
            doc = render_schedule.day_doc(today_bundle, prefs, today=today, title="☀️ Доброго ранку! Сьогодні:")
            await self.deliver(
                person, doc, kb([btn("⏱ Зараз", Nav(to="now")), btn("🗓 Тиждень", Nav(to="week"))]), prefs=prefs
            )

        pending = [h for h in due_tomorrow if h.id not in done_by_user.get(person.id, set())]
        if hhmm == prefs.evening_time:
            if prefs.evening_digest and tomorrow_bundle.day.active and self._once(person.id, "evening", today):
                doc = render_schedule.day_doc(tomorrow_bundle, prefs, today=today, title="🌙 Завтра:")
                if prefs.notify_deadlines and pending:
                    doc.h("🔥 Здати завтра", 3).quote(*(f"▫️ <b>{esc(h.subject)}</b>" for h in pending))
                await self.deliver(person, doc, kb([btn("📚 Домашка", HwCb(a="list", s=1))]), prefs=prefs)
            elif prefs.notify_deadlines and pending and self._once(person.id, "deadline", today):
                n = len(pending)
                doc = (
                    Doc()
                    .h("🔥 Дедлайни на завтра")
                    .p(f"Не зроблено: {n} {plural(n, 'завдання', 'завдання', 'завдань')}")
                )
                doc.quote(*(f"▫️ <b>{esc(h.subject)}</b>" for h in pending))
                await self.deliver(person, doc, kb([btn("📚 Відкрити", HwCb(a="list", s=1), "success")]), prefs=prefs)

        if prefs.remind_before:
            for lesson in today_bundle.day.active:
                at = lesson.starts_at() - timedelta(minutes=prefs.remind_before)
                if f"{at:%H:%M}" == hhmm and self._once(person.id, f"remind:{lesson.slot}", today):
                    name = render_schedule.subject_name(lesson.subject, today_bundle.subjects, prefs)
                    lines = [f"<b>{esc(name)}</b> · {esc(lesson.kind.label.lower())}", f"🕐 {lesson.time.label}"]
                    if prefs.show_room and lesson.room:
                        lines.append(f"🚪 {esc(lesson.room)}")
                    doc = Doc().h(f"⏰ За {prefs.remind_before} хв — {lesson.slot} пара").quote(*lines)
                    extra = today_bundle.subjects.get(lesson.subject)
                    rows = [[btn("📖 Картка пари", LessonCb(d=d2i(today), s=lesson.slot))]]
                    if extra and extra.link:
                        rows.insert(0, [url_btn("🔗 Приєднатися", extra.link)])
                    await self.deliver(person, doc, kb(*rows), prefs=prefs)

    async def close(self) -> None:
        for task in [*self._pending.values(), *self._tasks]:
            task.cancel()
        self._pending.clear()

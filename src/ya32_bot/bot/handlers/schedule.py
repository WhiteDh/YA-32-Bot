"""Viewing the schedule: today, tomorrow, any day, weeks, «зараз», lesson cards."""

from __future__ import annotations

import re
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import easter, ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import CalCb, DayCb, LessonCb, Nav, WeekCb, i2d
from ya32_bot.bot.keyboards.common import BTN_NOW, BTN_TODAY, BTN_TOMORROW, BTN_WEEK, btn, calendar
from ya32_bot.bot.render.doc import Doc
from ya32_bot.bot.screens import day_screen, lesson_screen, now_screen, week_screen
from ya32_bot.core.calendar import monday_of
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.slots import SLOTS
from ya32_bot.core.timetable import first_start
from ya32_bot.db.models import User
from ya32_bot.services import schedule, semester

router = Router(name="schedule")

DATE_RE = re.compile(r"^\s*(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\s*$")


def parse_date(text: str, today: date) -> date | None:
    """``12.10``, ``12.10.2026``, ``12/10/26``; without a year — the nearest such date."""
    match = DATE_RE.match(text or "")
    if not match:
        return None
    day, month, year = int(match[1]), int(match[2]), match[3]
    try:
        if year:
            full = int(year) + (2000 if len(year) == 2 else 0)
            return date(full, month, day)
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    if (today - candidate).days > 180:
        candidate = candidate.replace(year=today.year + 1)
    return candidate


async def _show_day(
    event: Message | CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, when: date
) -> None:
    doc, markup = await day_screen(session, ctx, user, prefs, when)
    await ui.show(event, doc, markup, rich=prefs.rich)
    if prefs.easter_eggs:
        await _day_eggs(event, session, ctx, user, prefs, when)


async def _day_eggs(
    event: Message | CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, when: date
) -> None:
    bot = event.bot
    chat_id = event.from_user.id if event.from_user else None
    if bot is None or chat_id is None:
        return
    now = ctx.now()
    today = now.date()
    sem = await semester.get_semester(session)
    if when == today and sem.end == today and easter.once_per_day(user, "sem_end", today):
        easter.found(user, "semester_end")
        doc = Doc().h("🎊 Останній день семестру!").p("Ще трохи — і канікули. Ви молодці, ЯА-32! 💙💛")
        await ui.send(bot, chat_id, doc, rich=prefs.rich, effect_id=easter.CONFETTI)
    if 1 <= now.hour < 5 and when in (today, today + timedelta(days=1)):
        lessons = (await schedule.day(session, today, today=today)).day.active
        start = first_start(list(lessons))
        if start is not None and start <= SLOTS[2].start and easter.once_per_day(user, "night", today):
            easter.found(user, "sleep")
            await bot.send_message(chat_id, f"🌙 Пара о {start:%H:%M}. Спати. 😴")


# ── Today / tomorrow / any day ─────────────────────────────────────────────


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def msg_today(message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs) -> None:
    await _show_day(message, session, ctx, user, prefs, ctx.today())


@router.message(Command("tomorrow"))
@router.message(F.text == BTN_TOMORROW)
async def msg_tomorrow(message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs) -> None:
    await _show_day(message, session, ctx, user, prefs, ctx.today() + timedelta(days=1))


@router.message(Command("day"))
async def msg_day(
    message: Message, command: CommandObject, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    today = ctx.today()
    when = parse_date(command.args or "", today)
    if when is None:
        await message.answer("📆 Обери день:", reply_markup=calendar("view", today.year, today.month, today=today))
        return
    await _show_day(message, session, ctx, user, prefs, when)


@router.message(F.text.regexp(DATE_RE))
async def msg_date_text(message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs) -> None:
    when = parse_date(message.text or "", ctx.today())
    if when is None:
        await message.answer("🤔 Такої дати немає.")
        return
    await _show_day(message, session, ctx, user, prefs, when)


@router.callback_query(Nav.filter(F.to.in_({"today", "tomorrow"})))
async def cb_today(
    callback: CallbackQuery, callback_data: Nav, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    when = ctx.today() + timedelta(days=1 if callback_data.to == "tomorrow" else 0)
    easter.reset_streak(user)
    await _show_day(callback, session, ctx, user, prefs, when)


@router.callback_query(DayCb.filter())
async def cb_day(
    callback: CallbackQuery, callback_data: DayCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs,
    bot: Bot,
) -> None:  # fmt: skip
    if callback_data.step == 1 and prefs.easter_eggs and easter.next_tap(user, ctx.now()):
        doc = (
            Doc()
            .h("🏆 Ачівка: ЯА-32 forever")
            .p(
                f"Ти натиснув «наступний» {easter.NEXT_STREAK_GOAL} рази поспіль.",
                "Майбутнє не зміниться, але ти старався. 💪",
            )
        )
        await ui.send(bot, callback.from_user.id, doc, rich=prefs.rich, effect_id=easter.CONFETTI)
    elif callback_data.step != 1:
        easter.reset_streak(user)
    await _show_day(callback, session, ctx, user, prefs, i2d(callback_data.d))


@router.callback_query(CalCb.filter(F.p == "view"))
async def cb_calendar(
    callback: CallbackQuery, callback_data: CalCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    if callback_data.d:
        when = date(callback_data.y, callback_data.m, callback_data.d)
        await _show_day(callback, session, ctx, user, prefs, when)
        return
    doc = Doc().h("📆 Обери день").p("<i>• — є пари, ·N· — сьогодні</i>")
    marks = await _lesson_marks(session, ctx, callback_data.y, callback_data.m)
    markup = calendar("view", callback_data.y, callback_data.m, today=ctx.today(), marks=marks)
    markup.inline_keyboard.append([btn("🏠 Меню", Nav(to="menu"))])
    await ui.show(callback, doc, markup, rich=prefs.rich)


async def _lesson_marks(session: AsyncSession, ctx: AppContext, year: int, month: int) -> set[date]:
    start = date(year, month, 1)
    end = (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)
    bundles = await schedule.days(session, start, end, today=ctx.today())
    return {b.day.date for b in bundles if b.day.active}


# ── Weeks ──────────────────────────────────────────────────────────────────


@router.message(Command("week"))
@router.message(F.text == BTN_WEEK)
async def msg_week(message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    doc, markup = await week_screen(session, ctx, prefs, ctx.today())
    await ui.show(message, doc, markup, rich=prefs.rich)


@router.message(Command("nextweek"))
async def msg_next_week(message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    doc, markup = await week_screen(session, ctx, prefs, ctx.today() + timedelta(days=7))
    await ui.show(message, doc, markup, rich=prefs.rich)


@router.callback_query(Nav.filter(F.to.in_({"week", "nextweek"})))
async def cb_week_nav(
    callback: CallbackQuery, callback_data: Nav, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    shift = 7 if callback_data.to == "nextweek" else 0
    doc, markup = await week_screen(session, ctx, prefs, ctx.today() + timedelta(days=shift))
    await ui.show(callback, doc, markup, rich=prefs.rich)


@router.callback_query(WeekCb.filter())
async def cb_week(
    callback: CallbackQuery, callback_data: WeekCb, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    doc, markup = await week_screen(session, ctx, prefs, monday_of(i2d(callback_data.d)))
    await ui.show(callback, doc, markup, rich=prefs.rich)


# ── Now / lesson card ──────────────────────────────────────────────────────


@router.message(Command("now"))
@router.message(F.text == BTN_NOW)
async def msg_now(message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    doc, markup = await now_screen(session, ctx, prefs)
    await ui.show(message, doc, markup, rich=prefs.rich)


@router.callback_query(Nav.filter(F.to == "now"))
async def cb_now(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    doc, markup = await now_screen(session, ctx, prefs)
    await ui.show(callback, doc, markup, rich=prefs.rich)


@router.callback_query(LessonCb.filter())
async def cb_lesson(
    callback: CallbackQuery, callback_data: LessonCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    screen = await lesson_screen(session, ctx, user, prefs, i2d(callback_data.d), callback_data.s)
    if screen is None:
        await ui.toast(callback, "Цієї пари вже немає 🤷")
        return
    await ui.show(callback, *screen, rich=prefs.rich)

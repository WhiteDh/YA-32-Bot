"""Screens = document + keyboard, built from the database for one user.

Handlers, notifications and inline mode all reuse these, so a day looks the same
whichever way it reaches the user.
"""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Adm, CalCb, DayCb, LessonCb, Nav, WeekCb, d2i
from ya32_bot.bot.keyboards.common import btn, kb, url_btn
from ya32_bot.bot.render import schedule as render
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.core.calendar import monday_of
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import WEEKDAYS_SHORT, human_day
from ya32_bot.core.timetable import is_break, now_status
from ya32_bot.db.models import Role, User
from ya32_bot.services import homework, schedule

Screen = tuple[Doc, InlineKeyboardMarkup]


def main_menu(user: User, ctx: AppContext) -> Screen:
    today = ctx.today()
    doc = Doc().h(f"Привіт, {esc(user.first_name or 'друже')}! 👋")
    doc.p(f"<i>{esc(human_day(today))}</i>", "Що подивимось?")
    rows: list[list[InlineKeyboardButton]] = [
        [btn("📅 Сьогодні", Nav(to="today")), btn("➡️ Завтра", Nav(to="tomorrow"))],
        [btn("🗓 Цей тиждень", Nav(to="week")), btn("⏭ Наступний", Nav(to="nextweek"))],
        [btn("⏱ Зараз", Nav(to="now")), btn("📆 Календар", CalCb(p="view", y=today.year, m=today.month))],
        [btn("⚙️ Налаштування", Nav(to="settings"))],
    ]
    if user.role_enum.at_least(Role.ADMIN):
        rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


async def day_screen(
    session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, when: date, *, title: str | None = None
) -> Screen:
    today = ctx.today()
    bundle = await schedule.day(session, when, today=today)
    if title is None:
        if when == today:
            title = "Сьогодні"
        elif when == today + timedelta(days=1):
            title = "Завтра"
        elif when == today - timedelta(days=1):
            title = "Вчора"
    doc = render.day_doc(bundle, prefs, today=today, now=ctx.now(), title=title)

    rows: list[list[InlineKeyboardButton]] = []
    prev_day, next_day = when - timedelta(days=1), when + timedelta(days=1)
    rows.append(
        [
            btn(f"◀️ {WEEKDAYS_SHORT[prev_day.weekday()]}", DayCb(d=d2i(prev_day), step=-1)),
            btn("📆", CalCb(p="view", y=when.year, m=when.month)),
            btn(f"{WEEKDAYS_SHORT[next_day.weekday()]} ▶️", DayCb(d=d2i(next_day), step=1)),
        ]
    )
    bottom = [btn("🗓 Тиждень", WeekCb(d=d2i(monday_of(when)))), btn("🏠 Меню", Nav(to="menu"))]
    if when != today:
        bottom.insert(0, btn("↩️ Сьогодні", Nav(to="today")))
    rows.append(bottom)
    if user.role_enum.at_least(Role.ADMIN):
        rows.append([btn("✏️ Редагувати", Adm(a="day", d=d2i(when)))])
    return doc, kb(*rows)


async def week_screen(session: AsyncSession, ctx: AppContext, prefs: Prefs, any_day: date) -> Screen:
    today = ctx.today()
    monday = monday_of(any_day)
    bundles = await schedule.week(session, monday, today=today)
    doc = render.week_doc(bundles, prefs, today=today)
    day_buttons = [
        btn(WEEKDAYS_SHORT[b.day.date.weekday()], DayCb(d=d2i(b.day.date)))
        for b in bundles
        if b.day.lessons or b.day.date.weekday() < 5 or prefs.show_weekends
    ]
    nav = [
        btn("◀️ Попередній", WeekCb(d=d2i(monday - timedelta(days=7)))),
        btn("Наступний ▶️", WeekCb(d=d2i(monday + timedelta(days=7)))),
    ]
    extra = [btn("📤 У календар", Nav(to="ics")), btn("🏠 Меню", Nav(to="menu"))]
    if monday != monday_of(today):
        extra.insert(0, btn("↩️ Цей тиждень", Nav(to="week")))
    return doc, kb(day_buttons, nav, extra)


async def now_screen(session: AsyncSession, ctx: AppContext, prefs: Prefs) -> Screen:
    now = ctx.now()
    lessons = await schedule.upcoming_lessons(session, now.date(), horizon=14)
    status = now_status(now, lessons)
    breaking = is_break(now, [x for x in lessons if x.date == now.date()])
    subjects = await schedule.subjects(session)
    doc = render.now_doc(status, prefs, subjects, now=now, break_left=breaking)
    rows = [[btn("🔄 Оновити", Nav(to="now")), btn("📅 Сьогодні", Nav(to="today"))]]
    focus = status.current or status.next
    if focus is not None:
        rows.insert(0, [btn("📖 Картка пари", LessonCb(d=d2i(focus.date), s=focus.slot))])
    rows.append([btn("🏠 Меню", Nav(to="menu"))])
    return doc, kb(*rows)


async def lesson_screen(
    session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, when: date, slot: int
) -> Screen | None:
    bundle = await schedule.day(session, when, today=ctx.today())
    lesson = next((x for x in bundle.day.lessons if x.slot == slot), None)
    if lesson is None:
        return None
    hw = await homework.for_subject(session, lesson.subject, ctx.today())
    doc = render.lesson_doc(lesson, bundle, prefs, hw, now=ctx.now())
    rows: list[list[InlineKeyboardButton]] = []
    links: list[InlineKeyboardButton] = []
    link = render.lesson_link(lesson, bundle.subjects)
    if link:
        links.append(url_btn("🔗 Приєднатися", link))
    if prefs.show_room and lesson.room_url:
        links.append(url_btn("🗺 Корпус", lesson.room_url))
    if links:
        rows.append(links)
    if user.role_enum.at_least(Role.ADMIN):
        rows.append([btn("✏️ Змінити", Adm(a="slot", d=d2i(when), s=slot))])
    rows.append([btn("← До дня", DayCb(d=d2i(when))), btn("🏠 Меню", Nav(to="menu"))])
    return doc, kb(*rows)

"""Semester bounds, week parity and holidays."""

from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Adm, CalCb, d2i, i2d
from ya32_bot.bot.keyboards.common import btn, calendar, kb
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.states import HolidayTitle
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import human_date
from ya32_bot.db.models import Holiday as HolidayRow
from ya32_bot.services import semester

router = Router(name="admin_semester")


def _holiday_line(h: HolidayRow) -> str:
    span = f"{h.start:%d.%m}–{h.end:%d.%m}" if h.end != h.start else f"{h.start:%d.%m}"
    return f"{span} · {esc(h.title)}"


async def semester_screen(session: AsyncSession, ctx: AppContext) -> tuple[Doc, InlineKeyboardMarkup]:
    today = ctx.today()
    sem = await semester.get_semester(session)
    anchor = await semester.get_anchor(session, today)
    week = anchor.week_of(today)
    doc = Doc().h("🗓 Семестр і канікули")
    left = sem.days_left(today)
    doc.quote(
        f"▶️ Початок: <b>{human_date(sem.start) if sem.start else 'не задано'}</b>",
        f"⏹ Кінець: <b>{human_date(sem.end) if sem.end else 'не задано'}</b>"
        + (f" · ще {left} дн." if left is not None else ""),
        f"🔢 Зараз: <b>{week}-й тиждень</b>",
    )
    holidays = await semester.list_holidays(session)
    if holidays:
        doc.h("🎉 Вихідні й канікули", 3).quote(*(_holiday_line(h) for h in holidays))
    rows: list[list[InlineKeyboardButton]] = [
        [
            btn("▶️ Початок", CalCb(p="sem_s", y=today.year, m=today.month)),
            btn("⏹ Кінець", CalCb(p="sem_e", y=today.year, m=today.month)),
        ],
        [btn(f"🔁 Зробити цей тиждень {2 if week == 1 else 1}-м", Adm(a="semflip"))],
        [btn("➕ Вихідний / канікули", CalCb(p="hol_s", y=today.year, m=today.month), "success")],
    ]
    rows.extend([btn(f"🗑 {h.start:%d.%m} {h.title[:24]}", Adm(a="holdel", id=h.id))] for h in holidays)
    rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


@router.callback_query(Adm.filter(F.a == "sem"))
async def cb_semester(
    callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs, state: FSMContext
) -> None:
    await state.clear()
    await ui.show(callback, *await semester_screen(session, ctx), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "semflip"))
async def cb_flip(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    today = ctx.today()
    current = (await semester.get_anchor(session, today)).week_of(today)
    await semester.set_anchor(session, today, 2 if current == 1 else 1)
    await ui.toast(callback, f"🔢 Тепер цей тиждень — {2 if current == 1 else 1}-й")
    await ui.show(callback, *await semester_screen(session, ctx), rich=prefs.rich)


@router.callback_query(CalCb.filter(F.p.in_({"sem_s", "sem_e", "hol_s", "hol_e"})))
async def cb_calendar(
    callback: CallbackQuery,
    callback_data: CalCb,
    session: AsyncSession,
    ctx: AppContext,
    prefs: Prefs,
    state: FSMContext,
) -> None:
    p = callback_data.p
    titles = {
        "sem_s": "▶️ Початок семестру",
        "sem_e": "⏹ Кінець семестру",
        "hol_s": "🎉 Перший вихідний день",
        "hol_e": "🎉 Останній вихідний день",
    }
    if not callback_data.d:
        markup = calendar(p, callback_data.y, callback_data.m, today=ctx.today(), x=callback_data.x)
        markup.inline_keyboard.append([btn("← Семестр", Adm(a="sem"))])
        await ui.show(callback, Doc().h(titles[p]), markup, rich=prefs.rich)
        return
    picked = date(callback_data.y, callback_data.m, callback_data.d)
    if p == "sem_s":
        await semester.set_semester_bounds(session, start=picked)
    elif p == "sem_e":
        await semester.set_semester_bounds(session, end=picked)
    elif p == "hol_s":
        markup = calendar("hol_e", picked.year, picked.month, today=ctx.today(), x=d2i(picked))
        markup.inline_keyboard.append(
            [btn("Лише один день", CalCb(p="hol_e", y=picked.year, m=picked.month, d=picked.day, x=d2i(picked)))]
        )
        await ui.show(callback, Doc().h(titles["hol_e"]).p(f"Початок: {picked:%d.%m}"), markup, rich=prefs.rich)
        return
    else:
        start = i2d(callback_data.x) if callback_data.x else picked
        await state.set_state(HolidayTitle.title)
        await state.update_data(start=start.isoformat(), end=picked.isoformat())
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"🎉 {start:%d.%m}–{picked:%d.%m}. Як назвемо? (наприклад «Зимові канікули»)\n«-» — просто «Вихідний»."
            )
        return
    await ui.toast(callback, f"📅 {picked:%d.%m.%Y}")
    await ui.show(callback, *await semester_screen(session, ctx), rich=prefs.rich)


@router.message(HolidayTitle.title, F.text)
async def holiday_title(
    message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs, state: FSMContext
) -> None:
    data = await state.get_data()
    await state.clear()
    title = (message.text or "").strip()
    await semester.add_holiday(
        session,
        date.fromisoformat(data["start"]),
        date.fromisoformat(data["end"]),
        "" if title in {"-", "—"} else title,
    )
    await ui.show(message, *await semester_screen(session, ctx), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "holdel"))
async def cb_holiday_delete(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    await semester.delete_holiday(session, callback_data.id)
    await ui.toast(callback, "🗑 Видалено")
    await ui.show(callback, *await semester_screen(session, ctx), rich=prefs.rich)

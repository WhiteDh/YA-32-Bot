"""/search — a subject's next pairs and homework; /ics — the schedule as a calendar file."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import HwCb, LessonCb, Nav, d2i
from ya32_bot.bot.keyboards.common import btn, kb
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import WEEKDAYS_SHORT
from ya32_bot.services import export

router = Router(name="search")


def results_screen(hits: list[export.SearchHit], query: str) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h(f"🔎 {esc(query)}")
    rows: list[list[InlineKeyboardButton]] = []
    for hit in hits:
        lines = [f"<b>{esc(hit.subject)}</b>"]
        if hit.upcoming:
            lines += [
                f"{WEEKDAYS_SHORT[x.date.weekday()]} {x.date:%d.%m} · {x.slot} пара · {x.time.start:%H:%M} · "
                f"{esc(x.kind.label.lower())}"
                for x in hit.upcoming
            ]
        else:
            lines.append("<i>найближчі 4 тижні пар немає</i>")
        lines += [f"📚 до {h.due_date:%d.%m}: {esc(h.text[:60]) or 'вкладення'}" for h in hit.homework]
        doc.quote(*lines)
        if hit.upcoming:
            first = hit.upcoming[0]
            rows.append([btn(f"📖 {hit.subject[:30]} · {first.date:%d.%m}", LessonCb(d=d2i(first.date), s=first.slot))])
        rows.extend([btn(f"📚 ДЗ до {h.due_date:%d.%m}", HwCb(a="open", id=h.id))] for h in hit.homework[:1])
    rows.append([btn("🏠 Меню", Nav(to="menu"))])
    return doc, kb(*rows)


@router.message(Command("search"))
async def cmd_search(
    message: Message, command: CommandObject, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    query = (command.args or "").strip()
    if len(query) < 3:
        await message.answer("🔎 Напиши хоча б 3 літери назви: <code>/search аналіз</code>", parse_mode="HTML")
        return
    hits = await export.search(session, query, ctx.today())
    if not hits:
        await message.answer("🔎 Такого предмета не знайшов.")
        return
    doc, markup = results_screen(hits, query)
    await ui.show(message, doc, markup, rich=prefs.rich)


async def _send_ics(message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    content = await export.ics_for_user(session, ctx.today(), ctx.settings.tz, now=ctx.now(), show_room=prefs.show_room)
    await message.answer_document(
        BufferedInputFile(content.encode(), filename="ya32-rozklad.ics"),
        caption=(
            f"📤 Розклад на {export.ICS_WEEKS} тижнів уперед.\n"
            "Відкрий файл — і пари з'являться в Google / Apple / Outlook календарі.\n"
            "Розклад змінився? Просто завантаж файл ще раз."
        ),
    )


@router.message(Command("ics"))
async def cmd_ics(message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    await _send_ics(message, session, ctx, prefs)


@router.callback_query(Nav.filter(F.to == "ics"))
async def cb_ics(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    await callback.answer("📤 Готую файл…")
    if isinstance(callback.message, Message):
        await _send_ics(callback.message, session, ctx, prefs)

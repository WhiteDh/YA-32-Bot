"""Last resort: unknown text, denied admin buttons, stale callbacks."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.handlers.search import results_screen
from ya32_bot.bot.keyboards.callbacks import Adm, HwCb
from ya32_bot.core.prefs import Prefs
from ya32_bot.services import export

router = Router(name="fallback")


@router.callback_query(Adm.filter())
@router.callback_query(HwCb.filter())
async def denied(callback: CallbackQuery) -> None:
    await ui.toast(callback, "⛔ Недостатньо прав", alert=True)


@router.callback_query()
async def stale(callback: CallbackQuery) -> None:
    await ui.toast(callback, "Ця кнопка застаріла — відкрий /menu")


@router.message()
async def unknown(message: Message, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    """Free text that names a subject becomes a search; anything else gets a hint."""
    query = (message.text or "").strip()
    hits = await export.search(session, query, ctx.today()) if 3 <= len(query) <= 60 else []
    if hits:
        await ui.show(message, *results_screen(hits, query), rich=prefs.rich)
        return
    await message.answer(
        "🤔 Не зрозумів. Спробуй /menu або /help — або просто напиши дату, наприклад <code>12.10</code>.",
        parse_mode="HTML",
    )

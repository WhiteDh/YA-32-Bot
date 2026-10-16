"""Inline mode: ``@bot`` in any chat → share today / tomorrow / a week / a date."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, LinkPreviewOptions
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot.context import AppContext
from ya32_bot.bot.handlers.schedule import parse_date
from ya32_bot.bot.render import schedule as render
from ya32_bot.bot.render.doc import Doc
from ya32_bot.core.calendar import monday_of
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import human_day
from ya32_bot.services import schedule

router = Router(name="inline")

SHARE_PREFS = Prefs(show_room=False, show_homework=False, show_links=False, show_notes=True)


def _article(key: str, title: str, description: str, doc: Doc) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=hashlib.sha1(f"{key}:{title}".encode(), usedforsecurity=False).hexdigest()[:32],
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=doc.classic(),
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        ),
    )


def _summary(lessons: int) -> str:
    return f"{lessons} пар" if lessons else "пар немає"


@router.inline_query()
async def inline(query: InlineQuery, session: AsyncSession, ctx: AppContext) -> None:
    today = ctx.today()
    text = (query.query or "").strip().lower()
    results: list[InlineQueryResultArticle] = []

    picked: date | None = parse_date(text, today)
    candidates: list[tuple[str, date]] = []
    if picked is not None:
        candidates.append((human_day(picked), picked))
    if not text or "сьог" in text or "today" in text:
        candidates.append(("Сьогодні", today))
    if not text or "завт" in text or "tomorrow" in text:
        candidates.append(("Завтра", today + timedelta(days=1)))

    for title, when in candidates:
        bundle = await schedule.day(session, when, today=today)
        doc = render.day_doc(bundle, SHARE_PREFS, today=today, title=f"ЯА-32 · {title}")
        results.append(
            _article(when.isoformat(), f"📅 {title}", f"{human_day(when)} · {_summary(len(bundle.day.active))}", doc)
        )

    if not text or "тиж" in text or "week" in text:
        for title, monday in (
            ("Цей тиждень", monday_of(today)),
            ("Наступний тиждень", monday_of(today) + timedelta(days=7)),
        ):
            bundles = await schedule.week(session, monday, today=today)
            doc = render.week_doc(bundles, SHARE_PREFS, today=today)
            total = sum(len(b.day.active) for b in bundles)
            results.append(_article(f"w{monday.isoformat()}", f"🗓 {title}", _summary(total), doc))

    await query.answer(results[:10], cache_time=60, is_personal=False)  # type: ignore[arg-type]

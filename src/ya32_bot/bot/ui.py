"""Sending and editing screens: Rich Message first, classic HTML as the fallback.

If Telegram refuses the rich form once (older API server, an unsupported tag), the
process stops trying it — every later screen goes straight to classic HTML.
"""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InputRichMessage,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
)

from ya32_bot.bot.render.doc import Doc

logger = logging.getLogger(__name__)

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | None
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


class _RichSwitch:
    enabled = True


RICH = _RichSwitch()


def _not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


async def send(
    bot: Bot,
    chat_id: int,
    doc: Doc,
    markup: Markup = None,
    *,
    rich: bool = True,
    silent: bool = False,
    effect_id: str | None = None,
) -> Message:
    if rich and RICH.enabled and not isinstance(markup, ReplyKeyboardMarkup):
        try:
            return await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=doc.rich()),
                reply_markup=markup,
                disable_notification=silent,
                message_effect_id=effect_id,
            )
        except TelegramBadRequest as exc:
            if "effect" in str(exc).lower():
                effect_id = None
            else:
                RICH.enabled = False
                logger.warning("rich message refused, switching to classic HTML: %s", exc)
    try:
        return await bot.send_message(
            chat_id,
            doc.classic(),
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_notification=silent,
            message_effect_id=effect_id,
            link_preview_options=NO_PREVIEW,
        )
    except TelegramBadRequest as exc:
        if effect_id is None or "effect" not in str(exc).lower():
            raise
        return await bot.send_message(
            chat_id, doc.classic(), parse_mode=ParseMode.HTML, reply_markup=markup,
            disable_notification=silent, link_preview_options=NO_PREVIEW,
        )  # fmt: skip


async def edit(message: Message, doc: Doc, markup: InlineKeyboardMarkup | None = None, *, rich: bool = True) -> None:
    """Edit in place; if the message cannot be edited, send a fresh one instead."""
    bot = message.bot
    if bot is None:
        return
    attempts: list[bool] = [True, False] if rich and RICH.enabled else [False, True]
    for as_rich in attempts:
        try:
            if as_rich:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    rich_message=InputRichMessage(html=doc.rich()),
                    reply_markup=markup,
                )
            else:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=doc.classic(),
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    link_preview_options=NO_PREVIEW,
                )
            return
        except TelegramBadRequest as exc:
            if _not_modified(exc):
                return
            logger.debug("edit as %s failed: %s", "rich" if as_rich else "classic", exc)
    with contextlib.suppress(TelegramBadRequest):
        await message.delete()
    await send(bot, message.chat.id, doc, markup, rich=rich)


async def show(
    event: Message | CallbackQuery, doc: Doc, markup: InlineKeyboardMarkup | None = None, *, rich: bool = True
) -> None:
    """A callback edits the screen it came from; a message gets a new screen."""
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            await edit(event.message, doc, markup, rich=rich)
        with contextlib.suppress(TelegramBadRequest):
            await event.answer()
        return
    if event.bot is not None:
        await send(event.bot, event.chat.id, doc, markup, rich=rich)


def clip(text: str, limit: int = 200) -> str:
    """Callback toasts are capped at 200 UTF-16 units."""
    if len(text.encode("utf-16-le")) // 2 <= limit:
        return text
    out = ""
    for char in text:
        if len((out + char).encode("utf-16-le")) // 2 > limit - 1:
            break
        out += char
    return out.rstrip() + "…"


async def toast(callback: CallbackQuery, text: str, *, alert: bool = False) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await callback.answer(clip(text), show_alert=alert)

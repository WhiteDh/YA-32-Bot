"""Homework: list, card, done marks; adding/editing for editors."""

from __future__ import annotations

import contextlib
from datetime import date
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaDocument, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.filters import HasRole
from ya32_bot.bot.keyboards.callbacks import CalCb, HwCb, LessonCb, Nav, d2i, i2d
from ya32_bot.bot.keyboards.common import BTN_HW, btn, calendar, grid, kb, reply_menu
from ya32_bot.bot.render import homework as render
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.states import HwAdd, HwEdit
from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import Homework, Role, User
from ya32_bot.services import homework, schedule

router = Router(name="homework")
editor = Router(name="homework_editor")
editor.message.filter(HasRole(Role.EDITOR))
editor.callback_query.filter(HasRole(Role.EDITOR))
router.include_router(editor)

MAX_LIST_BUTTONS = 24


# ── List and card (everyone) ───────────────────────────────────────────────


async def _list(
    event: Message | CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, hide_done: bool
) -> None:
    today = ctx.today()
    items = await homework.upcoming(session, user.id, today)
    doc = render.list_doc(items, today, hide_done=hide_done)
    shown = [i for i in items if not (hide_done and i.done)][:MAX_LIST_BUTTONS]
    buttons = [
        btn(f"{'✅' if i.done else '▫️'} {i.hw.subject[:18]} · {i.hw.due_date:%d.%m}", HwCb(a="open", id=i.hw.id))
        for i in shown
    ]
    rows = grid(buttons, 2)
    toggle = "👁 Показати зроблені" if hide_done else "🙈 Сховати зроблені"
    rows.append([btn(toggle, HwCb(a="list", s=0 if hide_done else 1))])
    if user.role_enum.at_least(Role.EDITOR):
        today_cal = HwCb(a="new")
        rows.append([btn("➕ Додати ДЗ", today_cal, "success")])
    rows.append([btn("🏠 Меню", Nav(to="menu"))])
    await ui.show(event, doc, kb(*rows), rich=prefs.rich)


@router.message(F.text == BTN_HW)
async def msg_old_keyboard(message: Message, user: User) -> None:
    """The bottom keyboard no longer has this button; a tap on an old copy swaps it for the new one."""
    await message.answer("⌨️ Кнопки оновлено.", reply_markup=reply_menu(user.role_enum))


@router.message(Command("hw"))
async def msg_list(message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs) -> None:
    await _list(message, session, ctx, user, prefs, hide_done=False)


@router.callback_query(HwCb.filter(F.a == "list"))
async def cb_list(
    callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    await _list(callback, session, ctx, user, prefs, hide_done=bool(callback_data.s))


async def _card(
    event: Message | CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, hw: Homework
) -> None:
    done = hw.id in await homework.done_ids(session, user.id, [hw.id])
    author = await session.get(User, hw.author_id) if hw.author_id else None
    doc = render.card_doc(
        hw, ctx.today(), done=done, done_total=await homework.done_count(session, hw.id),
        author=author.first_name if author else None,
    )  # fmt: skip
    rows = [
        [btn("↩️ Не зроблено" if done else "✅ Зроблено", HwCb(a="done", id=hw.id), None if done else "success")],
    ]
    if hw.attachments:
        rows.append([btn(f"📎 Вкладення ({len(hw.attachments)})", HwCb(a="files", id=hw.id))])
    if hw.slot:
        rows.append([btn("📖 Картка пари", LessonCb(d=d2i(hw.due_date), s=hw.slot))])
    if user.role_enum.at_least(Role.EDITOR):
        rows.append([btn("✏️ Текст", HwCb(a="edit", id=hw.id)), btn("🗑 Видалити", HwCb(a="del", id=hw.id), "danger")])
    rows.append([btn("← Домашка", HwCb(a="list")), btn("🏠 Меню", Nav(to="menu"))])
    await ui.show(event, doc, kb(*rows), rich=prefs.rich)


@router.callback_query(HwCb.filter(F.a == "open"))
async def cb_open(
    callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    hw = await session.get(Homework, callback_data.id)
    if hw is None:
        await ui.toast(callback, "Цю домашку вже видалили")
        return
    await _card(callback, session, ctx, user, prefs, hw)


@router.callback_query(HwCb.filter(F.a == "done"))
async def cb_done(
    callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    hw = await session.get(Homework, callback_data.id)
    if hw is None:
        await ui.toast(callback, "Цю домашку вже видалили")
        return
    state = await homework.toggle_done(session, user.id, hw.id)
    await _card(callback, session, ctx, user, prefs, hw)
    await ui.toast(callback, "✅ Зроблено! Так тримати" if state else "↩️ Повернув у список")


@router.callback_query(HwCb.filter(F.a == "files"))
async def cb_files(callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, bot: Bot) -> None:
    hw = await session.get(Homework, callback_data.id)
    if hw is None or not hw.attachments:
        await ui.toast(callback, "Вкладень немає")
        return
    await callback.answer()
    await send_attachments(bot, callback.from_user.id, hw)


async def send_attachments(bot: Bot, chat_id: int, hw: Homework) -> None:
    caption = f"📎 {hw.subject} · до {hw.due_date:%d.%m}"
    photos = [a for a in hw.attachments if a.get("type") == "photo"]
    docs = [a for a in hw.attachments if a.get("type") == "document"]
    rest = [a for a in hw.attachments if a.get("type") not in ("photo", "document")]
    for chunk in (photos[i : i + 10] for i in range(0, len(photos), 10)):
        if len(chunk) == 1:
            await bot.send_photo(chat_id, chunk[0]["file_id"], caption=caption)
        else:
            await bot.send_media_group(chat_id, [InputMediaPhoto(media=a["file_id"]) for a in chunk])
    for chunk in (docs[i : i + 10] for i in range(0, len(docs), 10)):
        if len(chunk) == 1:
            await bot.send_document(chat_id, chunk[0]["file_id"], caption=caption)
        else:
            await bot.send_media_group(chat_id, [InputMediaDocument(media=a["file_id"]) for a in chunk])
    for item in rest:
        kind, file_id = item.get("type"), item["file_id"]
        if kind == "video":
            await bot.send_video(chat_id, file_id)
        elif kind == "voice":
            await bot.send_voice(chat_id, file_id)
        elif kind == "audio":
            await bot.send_audio(chat_id, file_id)


# ── Adding (editors) ───────────────────────────────────────────────────────


@editor.callback_query(HwCb.filter(F.a == "new"))
async def cb_new(callback: CallbackQuery, ctx: AppContext, prefs: Prefs) -> None:
    today = ctx.today()
    doc = Doc().h("➕ Нова домашка").p("На який день задано? (день, коли її треба здати)")
    await ui.show(callback, doc, calendar("hw", today.year, today.month, today=today), rich=prefs.rich)


@editor.callback_query(CalCb.filter(F.p == "hw"))
async def cb_hw_calendar(
    callback: CallbackQuery, callback_data: CalCb, session: AsyncSession, ctx: AppContext, prefs: Prefs,
    state: FSMContext,
) -> None:  # fmt: skip
    today = ctx.today()
    if not callback_data.d:
        markup = calendar("hw", callback_data.y, callback_data.m, today=today, x=callback_data.x)
        await ui.show(callback, Doc().h("📅 Обери день"), markup, rich=prefs.rich)
        return
    picked = date(callback_data.y, callback_data.m, callback_data.d)
    if callback_data.x == 1 and await state.get_state() == HwAdd.collect.state:
        await state.update_data(due=picked.isoformat())
        await _redraw_draft(callback, state, prefs)
        return
    await _pick_lesson(callback, session, ctx, prefs, picked)


@editor.callback_query(HwCb.filter(F.a == "add"))
async def cb_add_for_day(
    callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    await _pick_lesson(callback, session, ctx, prefs, i2d(callback_data.d))


async def _pick_lesson(
    callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs, when: date
) -> None:
    bundle = await schedule.day(session, when, today=ctx.today())
    rows = [[btn(f"{x.slot}. {x.subject[:40]}", HwCb(a="pick", d=d2i(when), s=x.slot))] for x in bundle.day.active]
    names = await schedule.known_subject_names(session)
    doc = Doc().h(f"📚 ДЗ на {when:%d.%m}")
    if rows:
        doc.p("До якої пари?")
    else:
        doc.p("Цього дня пар немає — обери предмет:")
        rows = [[btn(n[:40], HwCb(a="subj", d=d2i(when), id=i))] for i, n in enumerate(names[:30])]
    rows.append([btn("✖️ Скасувати", HwCb(a="list"))])
    await ui.show(callback, doc, kb(*rows), rich=prefs.rich)


@editor.callback_query(HwCb.filter(F.a.in_({"pick", "subj"})))
async def cb_pick(
    callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, ctx: AppContext, prefs: Prefs,
    state: FSMContext,
) -> None:  # fmt: skip
    when = i2d(callback_data.d)
    if callback_data.a == "pick":
        bundle = await schedule.day(session, when, today=ctx.today())
        lesson = next((x for x in bundle.day.active if x.slot == callback_data.s), None)
        if lesson is None:
            await ui.toast(callback, "Цієї пари вже немає")
            return
        subject, slot = lesson.subject, lesson.slot
    else:
        names = await schedule.known_subject_names(session)
        if not 0 <= callback_data.id < len(names):
            await ui.toast(callback, "Предмет не знайдено")
            return
        subject, slot = names[callback_data.id], None
    await state.set_state(HwAdd.collect)
    await state.update_data(subject=subject, slot=slot, due=when.isoformat(), text="", attachments=[])
    await _redraw_draft(callback, state, prefs)


def _draft_kb() -> Any:
    return kb(
        [btn("✅ Зберегти", "hw_save", "success"), btn("📅 Інша дата", "hw_due")],
        [btn("✖️ Скасувати", "hw_cancel", "danger")],
    )


async def _redraw_draft(event: Message | CallbackQuery, state: FSMContext, prefs: Prefs) -> None:
    data = await state.get_data()
    doc = render.draft_doc(data["subject"], date.fromisoformat(data["due"]), data["text"], len(data["attachments"]))
    if isinstance(event, CallbackQuery):
        await ui.show(event, doc, _draft_kb(), rich=prefs.rich)
        if isinstance(event.message, Message):
            await state.update_data(draft_id=event.message.message_id)
        return
    bot = event.bot
    if bot is None:
        return
    old = data.get("draft_id")
    if old:
        with contextlib.suppress(TelegramBadRequest):
            await bot.delete_message(event.chat.id, old)
    sent = await ui.send(bot, event.chat.id, doc, _draft_kb(), rich=prefs.rich)
    await state.update_data(draft_id=sent.message_id)


@editor.message(HwAdd.collect)
async def collect(message: Message, state: FSMContext, prefs: Prefs) -> None:
    data = await state.get_data()
    text: str = data.get("text", "")
    attachments: list[dict[str, str]] = list(data.get("attachments", []))
    piece = message.text or message.caption or ""
    if piece:
        text = f"{text}\n{piece}".strip()
    if message.photo:
        attachments.append({"type": "photo", "file_id": message.photo[-1].file_id})
    elif message.document:
        attachments.append({"type": "document", "file_id": message.document.file_id})
    elif message.video:
        attachments.append({"type": "video", "file_id": message.video.file_id})
    elif message.voice:
        attachments.append({"type": "voice", "file_id": message.voice.file_id})
    elif message.audio:
        attachments.append({"type": "audio", "file_id": message.audio.file_id})
    elif not piece:
        await message.answer("🤔 Це я не збережу. Текст, фото, файли, відео чи голосові.")
        return
    await state.update_data(text=text[:3500], attachments=attachments[:20])
    await _redraw_draft(message, state, prefs)


@editor.callback_query(F.data == "hw_due", HwAdd.collect)
async def cb_due(callback: CallbackQuery, ctx: AppContext, prefs: Prefs) -> None:
    today = ctx.today()
    await ui.show(
        callback,
        Doc().h("📅 До якого дня?"),
        calendar("hw", today.year, today.month, today=today, x=1),
        rich=prefs.rich,
    )


@editor.callback_query(F.data == "hw_cancel")
async def cb_cancel(
    callback: CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, state: FSMContext
) -> None:
    await state.clear()
    await ui.toast(callback, "✖️ Скасовано")
    await _list(callback, session, ctx, user, prefs, hide_done=False)


@editor.callback_query(F.data == "hw_save", HwAdd.collect)
async def cb_save(
    callback: CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, state: FSMContext
) -> None:
    data = await state.get_data()
    if not data.get("text") and not data.get("attachments"):
        await ui.toast(callback, "Спершу надішли текст або файл 🙂", alert=True)
        return
    hw = await homework.create(
        session, subject=data["subject"], due_date=date.fromisoformat(data["due"]), slot=data.get("slot"),
        text=data.get("text", ""), attachments=data.get("attachments", []), author_id=user.id,
    )  # fmt: skip
    await state.clear()
    await ui.toast(callback, "✅ Збережено! Група отримає сповіщення.")
    await _card(callback, session, ctx, user, prefs, hw)
    if ctx.notifier is not None:
        await session.commit()
        ctx.notifier.homework_added(hw.id, exclude=user.id)


# ── Editing / deleting (editors) ───────────────────────────────────────────


@editor.callback_query(HwCb.filter(F.a == "edit"))
async def cb_edit(callback: CallbackQuery, callback_data: HwCb, state: FSMContext) -> None:
    await state.set_state(HwEdit.text)
    await state.update_data(hw_id=callback_data.id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("✏️ Надішли новий текст домашки (або /cancel).")


@editor.message(HwEdit.text, F.text)
async def edit_text(
    message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, state: FSMContext
) -> None:
    data = await state.get_data()
    await state.clear()
    hw = await session.get(Homework, data.get("hw_id", 0))
    if hw is None:
        await message.answer("Цю домашку вже видалили.")
        return
    await homework.update_text(session, hw, message.text or "", user.id)
    await _card(message, session, ctx, user, prefs, hw)


@editor.callback_query(HwCb.filter(F.a == "del"))
async def cb_delete(callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, prefs: Prefs) -> None:
    hw = await session.get(Homework, callback_data.id)
    if hw is None:
        await ui.toast(callback, "Вже видалено")
        return
    doc = Doc().h("🗑 Видалити домашку?").quote(f"<b>{esc(hw.subject)}</b> · до {hw.due_date:%d.%m}")
    markup = kb([btn("🗑 Так, видалити", HwCb(a="delok", id=hw.id), "danger"), btn("← Ні", HwCb(a="open", id=hw.id))])
    await ui.show(callback, doc, markup, rich=prefs.rich)


@editor.callback_query(HwCb.filter(F.a == "delok"))
async def cb_delete_ok(
    callback: CallbackQuery, callback_data: HwCb, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    hw = await session.get(Homework, callback_data.id)
    if hw is not None:
        await homework.remove(session, hw, user.id)
    await ui.toast(callback, "🗑 Видалено. Можна повернути в адмінці → Журнал.")
    await _list(callback, session, ctx, user, prefs, hide_done=False)

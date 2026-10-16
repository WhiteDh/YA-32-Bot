"""Per-subject extras: short name, emoji, link (Meet/Zoom/Classroom), note."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.handlers.admin.common import clean_value
from ya32_bot.bot.keyboards.callbacks import Adm
from ya32_bot.bot.keyboards.common import btn, kb
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.states import SubjectEdit
from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import Subject
from ya32_bot.services import schedule

router = Router(name="admin_subjects")

SUBJECT_FIELDS = {
    "short": ("✂️ Коротка назва", 64),
    "emoji": ("😀 Емодзі", 16),
    "link": ("🔗 Посилання на пару", 512),
    "note": ("ℹ️ Примітка", 1000),
}


async def subjects_screen(session: AsyncSession) -> tuple[Doc, InlineKeyboardMarkup]:
    names = await schedule.known_subject_names(session)
    extras = await schedule.subjects(session)
    doc = (
        Doc()
        .h("📘 Предмети")
        .p(
            "Коротка назва, емодзі й посилання (Meet / Zoom / Classroom) — для кожного предмета.",
            "<i>Це не зникає при синхронізації з КПІ.</i>",
        )
    )
    rows = []
    for name in names[:40]:
        extra = extras.get(name)
        marks = (" 🔗" if extra and extra.link else "") + (f" {extra.emoji}" if extra and extra.emoji else "")
        subject = await schedule.subject_get_or_create(session, name)
        rows.append([btn(f"{name[:40]}{marks}", Adm(a="subjo", id=subject.id))])
    if not names:
        doc.quote("<i>Поки немає жодного предмета — синхронізуйся з КПІ або додай пари.</i>")
    rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


def subject_screen(subject: Subject) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = (
        Doc()
        .h(f"📘 {esc(subject.name)}")
        .quote(
            f"✂️ Коротко: <b>{esc(subject.short or '—')}</b>",
            f"😀 Емодзі: {esc(subject.emoji or '—')}",
            f"🔗 Посилання: {esc(subject.link or '—')}",
            f"ℹ️ Примітка: {esc(subject.note or '—')}",
        )
    )
    rows = [[btn(label, Adm(a="subjf", id=subject.id, v=key))] for key, (label, _limit) in SUBJECT_FIELDS.items()]
    rows.append([btn("← Предмети", Adm(a="subj"))])
    return doc, kb(*rows)


@router.callback_query(Adm.filter(F.a == "subj"))
async def cb_list(callback: CallbackQuery, session: AsyncSession, prefs: Prefs, state: FSMContext) -> None:
    await state.clear()
    await ui.show(callback, *await subjects_screen(session), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "subjo"))
async def cb_open(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    subject = await session.get(Subject, callback_data.id)
    if subject is None:
        await ui.toast(callback, "Предмет не знайдено")
        return
    await ui.show(callback, *subject_screen(subject), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "subjf"))
async def cb_field(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    if callback_data.v not in SUBJECT_FIELDS:
        await ui.toast(callback, "Невідоме поле")
        return
    await state.set_state(SubjectEdit.value)
    await state.update_data(id=callback_data.id, field=callback_data.v)
    await callback.answer()
    if isinstance(callback.message, Message):
        label = SUBJECT_FIELDS[callback_data.v][0]
        await callback.message.answer(f"{label}: надішли значення.\n«-» — очистити, /cancel — скасувати.")


@router.message(SubjectEdit.value, F.text)
async def field_value(message: Message, session: AsyncSession, prefs: Prefs, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    subject = await session.get(Subject, int(data.get("id", 0)))
    field = str(data.get("field", ""))
    if subject is None or field not in SUBJECT_FIELDS:
        await message.answer("Предмет не знайдено.")
        return
    value = clean_value(message.text or "", SUBJECT_FIELDS[field][1])
    if field == "link" and value and not value.startswith(("http://", "https://", "tg://")):
        await message.answer("🔗 Посилання має починатися з http:// або https://")
        return
    setattr(subject, field, value)
    await session.flush()
    await ui.show(message, *subject_screen(subject), rich=prefs.rich)

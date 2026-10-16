"""Editing the two-week template: what happens every week 1 / week 2."""

from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.handlers.admin.common import FIELD_LABELS, clean_value, kind_row
from ya32_bot.bot.keyboards.callbacks import Adm
from ya32_bot.bot.keyboards.common import btn, grid, kb
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.states import EditField
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.slots import MAX_SLOT, SLOTS
from ya32_bot.core.texts_uk import WEEKDAYS, WEEKDAYS_SHORT
from ya32_bot.core.timetable import LessonKind
from ya32_bot.db.models import TemplateLesson, User
from ya32_bot.services import schedule, semester
from ya32_bot.services.schedule import LessonFields

router = Router(name="admin_template")

WEEKDAYS_IN_TEMPLATE = 6  # Mon–Sat


async def weeks_screen(session: AsyncSession, ctx: AppContext) -> tuple[Doc, InlineKeyboardMarkup]:
    anchor = await semester.get_anchor(session, ctx.today())
    current = anchor.week_of(ctx.today())
    doc = (
        Doc()
        .h("🗂 Шаблон тижня")
        .p(
            "Тут те, що повторюється щотижня. Разові зміни — в «✏️ Редагувати день».",
            f"<i>Зараз {current}-й тиждень.</i>",
        )
    )
    rows = [[btn(f"{'👉 ' if w == current else ''}{w}-й тиждень", Adm(a="tplw", s=w), "primary") for w in (1, 2)]]
    rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


async def week_days_screen(session: AsyncSession, week: int) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h(f"🗂 {week}-й тиждень").p("Обери день:")
    buttons = []
    for weekday in range(WEEKDAYS_IN_TEMPLATE):
        count = len(await schedule.template_rows(session, week, weekday))
        buttons.append(btn(f"{WEEKDAYS_SHORT[weekday]} · {count}", Adm(a="tpld", s=week, d=weekday)))
    rows = grid(buttons, 3)
    rows.append([btn("← Тижні", Adm(a="tpl"))])
    return doc, kb(*rows)


async def weekday_screen(session: AsyncSession, week: int, weekday: int) -> tuple[Doc, InlineKeyboardMarkup]:
    rows_db = await schedule.template_rows(session, week, weekday)
    doc = Doc().h(f"🗂 {WEEKDAYS[weekday]} · {week}-й тиждень")
    lines = []
    for row in rows_db:
        only = f" <i>(лише {len(row.dates)} дат)</i>" if row.dates else ""
        src = " ✋" if row.source == "manual" else ""
        lines.append(
            f"<b>{row.slot}</b> · {esc(row.subject)} · {esc(LessonKind.parse(row.kind).label.lower())}{only}{src}"
        )
    if lines:
        doc.quote(*lines)
    else:
        doc.quote("<i>Порожньо</i>")
    doc.p("<i>✋ — додано чи змінено вручну (синхронізація «Оновити» таке не чіпає).</i>")
    rows: list[list[InlineKeyboardButton]] = [
        [btn(f"{r.slot} · {r.subject[:36]}", Adm(a="tplr", id=r.id), "primary")] for r in rows_db
    ]
    rows.append([btn("➕ Додати пару", Adm(a="tpladd", s=week, d=weekday), "success")])
    rows.append([btn(f"← {week}-й тиждень", Adm(a="tplw", s=week))])
    return doc, kb(*rows)


def row_screen(row: TemplateLesson) -> tuple[Doc, InlineKeyboardMarkup]:
    kind = LessonKind.parse(row.kind)
    doc = Doc().h(f"{kind.emoji} {esc(row.subject)}")
    lines = [
        f"🗂 {row.week}-й тиждень · {WEEKDAYS[row.weekday]}",
        f"🕐 {row.slot} пара · {SLOTS[row.slot].label}",
        f"🏷 {esc(kind.label)}",
        f"👤 {esc(row.teacher or '—')}",
        f"🚪 {esc(row.room or '—')}",
        "✋ додано вручну" if row.source == "manual" else "🔄 з КПІ",
    ]
    if row.dates:
        shown = ", ".join(date.fromisoformat(str(x)).strftime("%d.%m") for x in row.dates[:12])
        lines.append(f"📅 лише: {shown}{'…' if len(row.dates) > 12 else ''}")
    else:
        lines.append("📅 щотижня")
    doc.quote(*lines)
    r = row.id
    rows: list[list[InlineKeyboardButton]] = [
        [btn("✏️ Назва", Adm(a="tplf", id=r, v="subject")), btn("🏷 Тип", Adm(a="tplkp", id=r))],
        [btn("👤 Викладач", Adm(a="tplf", id=r, v="teacher")), btn("🚪 Аудиторія", Adm(a="tplf", id=r, v="room"))],
        [btn("🕐 Інша пара", Adm(a="tplsp", id=r)), btn("🗑 Видалити", Adm(a="tpldel", id=r), "danger")],
    ]
    if row.dates:
        rows.append([btn("📅 Зробити щотижневою", Adm(a="tplev", id=r))])
    rows.append([btn("← До дня", Adm(a="tpld", s=row.week, d=row.weekday))])
    return doc, kb(*rows)


@router.callback_query(Adm.filter(F.a == "tpl"))
async def cb_weeks(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    await ui.show(callback, *await weeks_screen(session, ctx), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tplw"))
async def cb_week(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    await ui.show(callback, *await week_days_screen(session, callback_data.s), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tpld"))
async def cb_weekday(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs, state: FSMContext
) -> None:
    await state.clear()
    await ui.show(callback, *await weekday_screen(session, callback_data.s, callback_data.d), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tplr"))
async def cb_row(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    row = await session.get(TemplateLesson, callback_data.id)
    if row is None:
        await ui.toast(callback, "Цієї пари в шаблоні вже немає")
        return
    await ui.show(callback, *row_screen(row), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tplkp"))
async def cb_kind_pick(callback: CallbackQuery, callback_data: Adm, prefs: Prefs) -> None:
    markup = kb(kind_row("tplk", ref=callback_data.id), [btn("← Назад", Adm(a="tplr", id=callback_data.id))])
    await ui.show(callback, Doc().h("🏷 Тип заняття"), markup, rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tplk"))
async def cb_kind(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, user: User, prefs: Prefs) -> None:
    row = await session.get(TemplateLesson, callback_data.id)
    if row is None:
        await ui.toast(callback, "Пари вже немає")
        return
    await schedule.template_update(session, row, {"kind": LessonKind.parse(callback_data.v).value}, user.id)
    await ui.show(callback, *row_screen(row), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tplsp"))
async def cb_slot_pick(callback: CallbackQuery, callback_data: Adm, prefs: Prefs) -> None:
    buttons = [
        btn(f"{s} · {SLOTS[s].start:%H:%M}", Adm(a="tpls", id=callback_data.id, s=s)) for s in range(1, MAX_SLOT + 1)
    ]
    rows = grid(buttons, 4)
    rows.append([btn("← Назад", Adm(a="tplr", id=callback_data.id))])
    await ui.show(callback, Doc().h("🕐 На яку пару?"), kb(*rows), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tpls"))
async def cb_slot(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, user: User, prefs: Prefs) -> None:
    row = await session.get(TemplateLesson, callback_data.id)
    if row is None:
        await ui.toast(callback, "Пари вже немає")
        return
    await schedule.template_update(session, row, {"slot": callback_data.s}, user.id)
    await ui.show(callback, *row_screen(row), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tplev"))
async def cb_every_week(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, user: User, prefs: Prefs
) -> None:
    row = await session.get(TemplateLesson, callback_data.id)
    if row is None:
        await ui.toast(callback, "Пари вже немає")
        return
    await schedule.template_update(session, row, {"dates": []}, user.id)
    await ui.show(callback, *row_screen(row), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tpldel"))
async def cb_delete(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, user: User, prefs: Prefs
) -> None:
    row = await session.get(TemplateLesson, callback_data.id)
    if row is None:
        await ui.toast(callback, "Вже видалено")
        return
    week, weekday = row.week, row.weekday
    await schedule.template_delete(session, row, user.id)
    await ui.toast(callback, "🗑 Видалено. Повернути — Журнал правок.")
    await ui.show(callback, *await weekday_screen(session, week, weekday), rich=prefs.rich)


# ── Text fields ────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.a == "tplf"))
async def cb_field(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    if callback_data.v not in FIELD_LABELS:
        await ui.toast(callback, "Невідоме поле")
        return
    await state.set_state(EditField.value)
    await state.update_data(target="tpl", id=callback_data.id, field=callback_data.v)
    await callback.answer()
    if isinstance(callback.message, Message):
        hint = "" if callback_data.v == "subject" else "\n<i>«-» — очистити.</i>"
        await callback.message.answer(
            f"✏️ Надішли {FIELD_LABELS[callback_data.v]}.{hint}\n/cancel — скасувати", parse_mode="HTML"
        )


async def apply_template_field(
    message: Message, session: AsyncSession, user: User, prefs: Prefs, data: dict[str, object]
) -> None:
    field = str(data["field"])
    value = clean_value(message.text or "")
    if field == "new_subject":
        if value is None:
            await message.answer("Назва не може бути порожньою.")
            return
        week, weekday, slot = int(str(data["week"])), int(str(data["weekday"])), int(str(data["slot"]))
        added = await schedule.template_add(session, week, weekday, slot, LessonFields(subject=value), user.id)
        await ui.show(message, *row_screen(added), rich=prefs.rich)
        return
    row = await session.get(TemplateLesson, int(str(data["id"])))
    if row is None:
        await message.answer("Цієї пари в шаблоні вже немає.")
        return
    if field == "subject" and value is None:
        await message.answer("Назва не може бути порожньою.")
        return
    await schedule.template_update(session, row, {field: value}, user.id)
    await ui.show(message, *row_screen(row), rich=prefs.rich)


# ── Adding a template pair ─────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.a == "tpladd"))
async def cb_add(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    week, weekday = callback_data.s, callback_data.d
    taken = {r.slot for r in await schedule.template_rows(session, week, weekday)}
    buttons = [
        btn(f"{s} · {SLOTS[s].start:%H:%M}{' •' if s in taken else ''}", Adm(a="tpladds", s=week, d=weekday, id=s))
        for s in range(1, MAX_SLOT + 1)
    ]
    rows = grid(buttons, 4)
    rows.append([btn("← Назад", Adm(a="tpld", s=week, d=weekday))])
    doc = Doc().h(f"➕ {WEEKDAYS[weekday]} · {week}-й тиждень").p("На яку пару? <i>(• — вже зайнята)</i>")
    await ui.show(callback, doc, kb(*rows), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tpladds"))
async def cb_add_slot(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    names = await schedule.known_subject_names(session)
    week, weekday, slot = callback_data.s, callback_data.d, callback_data.id
    rows = [[btn(n[:48], Adm(a="tpladdn", s=week, d=weekday, id=slot, v=str(i)))] for i, n in enumerate(names[:40])]
    rows.append([btn("⌨️ Ввести назву", Adm(a="tpladdt", s=week, d=weekday, id=slot))])
    rows.append([btn("← Назад", Adm(a="tpladd", s=week, d=weekday))])
    await ui.show(callback, Doc().h("📘 Який предмет?"), kb(*rows), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tpladdn"))
async def cb_add_named(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, user: User, prefs: Prefs
) -> None:
    names = await schedule.known_subject_names(session)
    index = int(callback_data.v) if callback_data.v.isdigit() else -1
    if not 0 <= index < len(names):
        await ui.toast(callback, "Предмет не знайдено")
        return
    subject = names[index]
    teacher = next((t.teacher for t in await schedule.templates(session) if t.subject == subject), None)
    row = await schedule.template_add(
        session,
        callback_data.s,
        callback_data.d,
        callback_data.id,
        LessonFields(subject=subject, teacher=teacher),
        user.id,
    )
    await ui.toast(callback, "➕ Додано. Перевір тип заняття.")
    await ui.show(callback, *row_screen(row), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "tpladdt"))
async def cb_add_text(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(EditField.value)
    await state.update_data(
        target="tpl", field="new_subject", week=callback_data.s, weekday=callback_data.d, slot=callback_data.id
    )
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("⌨️ Надішли назву предмета (/cancel — скасувати).")

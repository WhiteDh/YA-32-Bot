"""Editing one concrete date: cancel, change, move, add a pair. Changes are announced (debounced)."""

from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.handlers.admin.common import FIELD_LABELS, clean_value, editor_prefs, kind_row
from ya32_bot.bot.keyboards.callbacks import Adm, CalCb, DayCb, d2i, i2d
from ya32_bot.bot.keyboards.common import btn, calendar, kb
from ya32_bot.bot.render import schedule as render
from ya32_bot.bot.render.doc import Doc
from ya32_bot.bot.states import EditField
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.slots import MAX_SLOT, SLOTS
from ya32_bot.core.texts_uk import WEEKDAYS_SHORT, human_day
from ya32_bot.core.timetable import Lesson, LessonKind
from ya32_bot.db.models import User
from ya32_bot.services import schedule
from ya32_bot.services.schedule import LessonFields

router = Router(name="admin_day")


def _changed(ctx: AppContext, when: date, user: User) -> None:
    if ctx.notifier is not None:
        ctx.notifier.schedule_changed(when, exclude=user.id)


async def day_editor(
    session: AsyncSession, ctx: AppContext, prefs: Prefs, when: date
) -> tuple[Doc, InlineKeyboardMarkup]:
    bundle = await schedule.day(session, when, today=ctx.today())
    doc = render.day_doc(bundle, editor_prefs(prefs), today=ctx.today(), title=f"✏️ {human_day(when)}")
    doc.p("<i>Обери пару, щоб змінити її, або вільний слот, щоб додати.</i>")
    by_slot = {x.slot: x for x in bundle.day.lessons}
    rows: list[list[InlineKeyboardButton]] = []
    for slot in range(1, MAX_SLOT + 1):
        lesson = by_slot.get(slot)
        if lesson is None:
            rows.append([btn(f"{slot} · {SLOTS[slot].start:%H:%M} · ➕ вільно", Adm(a="add", d=d2i(when), s=slot))])
        else:
            mark = " ❌" if lesson.cancelled else (" 🔄" if lesson.changed else "")
            rows.append([btn(f"{slot} · {lesson.subject[:34]}{mark}", Adm(a="slot", d=d2i(when), s=slot), "primary")])
    prev_day, next_day = date.fromordinal(when.toordinal() - 1), date.fromordinal(when.toordinal() + 1)
    rows.append(
        [
            btn(f"◀️ {WEEKDAYS_SHORT[prev_day.weekday()]}", Adm(a="day", d=d2i(prev_day))),
            btn("📆", CalCb(p="edit", y=when.year, m=when.month)),
            btn(f"{WEEKDAYS_SHORT[next_day.weekday()]} ▶️", Adm(a="day", d=d2i(next_day))),
        ]
    )
    rows.append([btn("👁 Як бачать студенти", DayCb(d=d2i(when))), btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


async def _lesson(session: AsyncSession, ctx: AppContext, when: date, slot: int) -> Lesson | None:
    bundle = await schedule.day(session, when, today=ctx.today())
    return next((x for x in bundle.day.lessons if x.slot == slot), None)


async def slot_editor(
    session: AsyncSession, ctx: AppContext, prefs: Prefs, when: date, slot: int
) -> tuple[Doc, InlineKeyboardMarkup] | None:
    bundle = await schedule.day(session, when, today=ctx.today())
    lesson = next((x for x in bundle.day.lessons if x.slot == slot), None)
    if lesson is None:
        return None
    doc = render.lesson_doc(lesson, bundle, editor_prefs(prefs), [], now=ctx.now())
    doc.p("<i>Зміни стосуються лише цієї дати. Шаблон тижня — окремо.</i>")
    d, s = d2i(when), slot
    rows: list[list[InlineKeyboardButton]] = [
        [btn("✏️ Назва", Adm(a="field", d=d, s=s, v="subject")), btn("🏷 Тип", Adm(a="kindpick", d=d, s=s))],
        [
            btn("👤 Викладач", Adm(a="field", d=d, s=s, v="teacher")),
            btn("🚪 Аудиторія", Adm(a="field", d=d, s=s, v="room")),
        ],
        [btn("📝 Примітка", Adm(a="field", d=d, s=s, v="note")), btn("🔁 Перенести", Adm(a="move", d=d, s=s))],
    ]
    if lesson.cancelled:
        rows.append([btn("✅ Відновити пару", Adm(a="restore", d=d, s=s), "success")])
    else:
        rows.append([btn("❌ Скасувати на цю дату", Adm(a="cancel", d=d, s=s), "danger")])
    if lesson.changed and not lesson.cancelled:
        rows.append([btn("♻️ Повернути як у шаблоні", Adm(a="restore", d=d, s=s))])
    if lesson.template_id is not None:
        rows.append([btn("🗂 Змінити в шаблоні", Adm(a="tplr", id=lesson.template_id))])
    rows.append([btn("← До дня", Adm(a="day", d=d))])
    return doc, kb(*rows)


# ── Navigation ─────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.a == "pickday"))
async def cb_pick_day(callback: CallbackQuery, ctx: AppContext, prefs: Prefs) -> None:
    today = ctx.today()
    markup = calendar("edit", today.year, today.month, today=today)
    markup.inline_keyboard.append([btn("🛠 Адмінка", Adm(a="menu"))])
    await ui.show(callback, Doc().h("✏️ Який день редагуємо?"), markup, rich=prefs.rich)


@router.callback_query(CalCb.filter(F.p == "edit"))
async def cb_edit_calendar(
    callback: CallbackQuery, callback_data: CalCb, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    if not callback_data.d:
        markup = calendar("edit", callback_data.y, callback_data.m, today=ctx.today())
        markup.inline_keyboard.append([btn("🛠 Адмінка", Adm(a="menu"))])
        await ui.show(callback, Doc().h("✏️ Який день редагуємо?"), markup, rich=prefs.rich)
        return
    when = date(callback_data.y, callback_data.m, callback_data.d)
    await ui.show(callback, *await day_editor(session, ctx, prefs, when), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "day"))
async def cb_day(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, prefs: Prefs,
    state: FSMContext,
) -> None:  # fmt: skip
    await state.clear()
    await ui.show(callback, *await day_editor(session, ctx, prefs, i2d(callback_data.d)), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "slot"))
async def cb_slot(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    screen = await slot_editor(session, ctx, prefs, i2d(callback_data.d), callback_data.s)
    if screen is None:
        await ui.show(callback, *await day_editor(session, ctx, prefs, i2d(callback_data.d)), rich=prefs.rich)
        return
    await ui.show(callback, *screen, rich=prefs.rich)


# ── Cancel / restore / kind ────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.a == "cancel"))
async def cb_cancel(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    when = i2d(callback_data.d)
    await schedule.cancel(session, when, callback_data.s, user.id)
    _changed(ctx, when, user)
    await ui.toast(callback, "❌ Скасовано. Група дізнається за хвилину-дві.")
    await ui.show(callback, *await day_editor(session, ctx, prefs, when), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "restore"))
async def cb_restore(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    when = i2d(callback_data.d)
    if await schedule.restore(session, when, callback_data.s, user.id) is None:
        await ui.toast(callback, "Тут і так усе як у шаблоні")
    else:
        _changed(ctx, when, user)
        await ui.toast(callback, "♻️ Повернуто як у шаблоні")
    await ui.show(callback, *await day_editor(session, ctx, prefs, when), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "kindpick"))
async def cb_kind_pick(callback: CallbackQuery, callback_data: Adm, prefs: Prefs) -> None:
    markup = kb(
        kind_row("kind", d=callback_data.d, s=callback_data.s),
        [btn("← Назад", Adm(a="slot", d=callback_data.d, s=callback_data.s))],
    )
    await ui.show(callback, Doc().h("🏷 Тип заняття"), markup, rich=prefs.rich)


def fields_of(lesson: Lesson, **changes: str | None) -> LessonFields:
    values: dict[str, str | None] = {
        "subject": lesson.subject,
        "kind": lesson.kind.value,
        "teacher": lesson.teacher,
        "room": lesson.room,
        "note": lesson.note,
    }
    values.update(changes)
    return LessonFields(**values)


@router.callback_query(Adm.filter(F.a == "kind"))
async def cb_kind(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    when = i2d(callback_data.d)
    lesson = await _lesson(session, ctx, when, callback_data.s)
    if lesson is None:
        await ui.toast(callback, "Пари вже немає")
        return
    await schedule.put(
        session, when, lesson.slot, fields_of(lesson, kind=LessonKind.parse(callback_data.v).value), user.id
    )
    _changed(ctx, when, user)
    screen = await slot_editor(session, ctx, prefs, when, lesson.slot)
    if screen:
        await ui.show(callback, *screen, rich=prefs.rich)


# ── Text fields (shared with the template editor through EditField) ───────


@router.callback_query(Adm.filter(F.a == "field"))
async def cb_field(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    field = callback_data.v
    if field not in FIELD_LABELS:
        await ui.toast(callback, "Невідоме поле")
        return
    await state.set_state(EditField.value)
    await state.update_data(target="day", d=callback_data.d, s=callback_data.s, field=field)
    await callback.answer()
    if isinstance(callback.message, Message):
        hint = "" if field == "subject" else "\n<i>«-» — очистити.</i>"
        await callback.message.answer(f"✏️ Надішли {FIELD_LABELS[field]}.{hint}\n/cancel — скасувати", parse_mode="HTML")


async def apply_day_field(
    message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, data: dict[str, object]
) -> None:
    when = i2d(int(str(data["d"])))
    slot = int(str(data["s"]))
    field = str(data["field"])
    value = clean_value(message.text or "")
    if field == "new_subject":
        if value is None:
            await message.answer("Назва не може бути порожньою.")
            return
        template = await _template_like(session, value)
        await schedule.put(session, when, slot, template, user.id)
    else:
        lesson = await _lesson(session, ctx, when, slot)
        if lesson is None:
            await message.answer("Цієї пари вже немає.")
            return
        if field == "subject" and value is None:
            await message.answer("Назва не може бути порожньою.")
            return
        await schedule.put(session, when, slot, fields_of(lesson, **{field: value}), user.id)
    _changed(ctx, when, user)
    screen = await slot_editor(session, ctx, prefs, when, slot)
    if screen:
        await ui.show(message, *screen, rich=prefs.rich)


# ── Add a pair to a free slot ──────────────────────────────────────────────


async def _template_like(session: AsyncSession, subject: str) -> LessonFields:
    """Prefill a new pair from how this subject usually appears in the template."""
    for tpl in await schedule.templates(session):
        if tpl.subject == subject:
            return LessonFields(subject=subject, kind=tpl.kind.value, teacher=tpl.teacher)
    return LessonFields(subject=subject)


@router.callback_query(Adm.filter(F.a == "add"))
async def cb_add(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    names = await schedule.known_subject_names(session)
    when = i2d(callback_data.d)
    doc = Doc().h(f"➕ {callback_data.s} пара · {when:%d.%m}").p("Який предмет?")
    rows = [
        [btn(name[:48], Adm(a="addsubj", d=callback_data.d, s=callback_data.s, id=i))]
        for i, name in enumerate(names[:40])
    ]
    rows.append([btn("⌨️ Ввести назву", Adm(a="addtext", d=callback_data.d, s=callback_data.s))])
    rows.append([btn("← До дня", Adm(a="day", d=callback_data.d))])
    await ui.show(callback, doc, kb(*rows), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "addsubj"))
async def cb_add_subject(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    names = await schedule.known_subject_names(session)
    if not 0 <= callback_data.id < len(names):
        await ui.toast(callback, "Предмет не знайдено")
        return
    when = i2d(callback_data.d)
    await schedule.put(session, when, callback_data.s, await _template_like(session, names[callback_data.id]), user.id)
    _changed(ctx, when, user)
    await ui.toast(callback, "➕ Додано. Перевір тип і викладача.")
    screen = await slot_editor(session, ctx, prefs, when, callback_data.s)
    if screen:
        await ui.show(callback, *screen, rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "addtext"))
async def cb_add_text(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(EditField.value)
    await state.update_data(target="day", d=callback_data.d, s=callback_data.s, field="new_subject")
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("⌨️ Надішли назву предмета (/cancel — скасувати).")


# ── Move ───────────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.a == "move"))
async def cb_move(callback: CallbackQuery, callback_data: Adm, ctx: AppContext, prefs: Prefs) -> None:
    when = i2d(callback_data.d)
    ref = callback_data.d * 10 + callback_data.s
    markup = calendar("move", when.year, when.month, today=ctx.today(), x=ref)
    markup.inline_keyboard.append([btn("← Назад", Adm(a="slot", d=callback_data.d, s=callback_data.s))])
    await ui.show(callback, Doc().h("🔁 Куди переносимо?").p("Обери день (можна той самий)."), markup, rich=prefs.rich)


@router.callback_query(CalCb.filter(F.p == "move"))
async def cb_move_calendar(
    callback: CallbackQuery, callback_data: CalCb, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    ref = callback_data.x
    if not callback_data.d:
        markup = calendar("move", callback_data.y, callback_data.m, today=ctx.today(), x=ref)
        await ui.show(callback, Doc().h("🔁 Куди переносимо?"), markup, rich=prefs.rich)
        return
    target = date(callback_data.y, callback_data.m, callback_data.d)
    bundle = await schedule.day(session, target, today=ctx.today())
    free = schedule.free_slots(bundle.day)
    source_d, source_s = divmod(ref, 10)
    if target == i2d(source_d):
        free.append(source_s)
    doc = Doc().h(f"🔁 {human_day(target)}").p("На яку пару?")
    rows = [
        [btn(f"{s} · {SLOTS[s].label}", Adm(a="moveto", d=d2i(target), s=s, id=ref))] for s in sorted(set(free))
        if not (target == i2d(source_d) and s == source_s)
    ]  # fmt: skip
    if not rows:
        doc.p("<i>Цього дня вільних пар немає.</i>")
    rows.append([btn("← Інший день", Adm(a="move", d=source_d, s=source_s))])
    await ui.show(callback, doc, kb(*rows), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "moveto"))
async def cb_move_to(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    source_d, source_s = divmod(callback_data.id, 10)
    source = i2d(source_d)
    lesson = await _lesson(session, ctx, source, source_s)
    if lesson is None or lesson.cancelled:
        await ui.toast(callback, "Цієї пари вже немає", alert=True)
        return
    target = i2d(callback_data.d)
    await schedule.move(session, lesson, target, callback_data.s, user.id)
    _changed(ctx, source, user)
    if target != source:
        _changed(ctx, target, user)
    await ui.toast(callback, f"🔁 Перенесено на {target:%d.%m}, {callback_data.s} пара")
    await ui.show(callback, *await day_editor(session, ctx, prefs, target), rich=prefs.rich)

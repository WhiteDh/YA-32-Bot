"""/settings — every toggle is one tap; presets for those who do not want to tune."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Nav, SetCb
from ya32_bot.bot.keyboards.common import BTN_SETTINGS, btn, grid, kb, reply_menu
from ya32_bot.bot.render.doc import Doc
from ya32_bot.bot.screens import day_screen
from ya32_bot.core.prefs import (
    NOTIFY_TOGGLES,
    OTHER_TOGGLES,
    PRESET_LABELS,
    PRESETS,
    REMIND_CHOICES,
    VIEW_TOGGLES,
    Prefs,
    PresetName,
    apply_preset,
)
from ya32_bot.db.models import User
from ya32_bot.services import users

router = Router(name="settings")

SECTIONS = {"view": VIEW_TOGGLES, "notify": NOTIFY_TOGGLES, "other": OTHER_TOGGLES}
TIME_KEYS = {
    "morning_time": "🌅 Ранковий розклад",
    "evening_time": "🌙 Вечірній розклад",
    "quiet_from": "🤫 Тихі години з",
    "quiet_to": "🤫 Тихі години до",
}


def _onoff(value: bool) -> str:
    return "✅" if value else "▫️"


def root_screen(prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h("⚙️ Налаштування")
    remind = f"за {prefs.remind_before} хв" if prefs.remind_before else "вимкнено"
    doc.quote(
        f"🌅 Ранковий розклад: <b>{prefs.morning_time if prefs.morning_digest else 'вимкнено'}</b>",
        f"🌙 Вечірній: <b>{prefs.evening_time if prefs.evening_digest else 'вимкнено'}</b>",
        f"⏰ Нагадування про пару: <b>{remind}</b>",
        f"🤫 Тихі години: <b>{f'{prefs.quiet_from}–{prefs.quiet_to}' if prefs.quiet_hours else 'вимкнено'}</b>",
    )
    doc.p("<i>Налаштуй вигляд розкладу під себе або обери готовий пресет.</i>")
    markup = kb(
        [
            btn("👁 Вигляд", SetCb(a="open", k="view"), "primary"),
            btn("🔔 Сповіщення", SetCb(a="open", k="notify"), "primary"),
        ],
        [btn("🎨 Пресети", SetCb(a="open", k="presets")), btn("🧩 Інше", SetCb(a="open", k="other"))],
        [btn("👀 Як виглядатиме сьогодні", SetCb(a="preview"))],
        [btn("🏠 Меню", Nav(to="menu"))],
    )
    return doc, markup


def section_screen(section: str, prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
    rows: list[list[InlineKeyboardButton]] = []
    if section == "presets":
        doc = (
            Doc()
            .h("🎨 Пресети")
            .quote(
                "🪶 <b>Мінімум</b> — тільки час і назви, коротко.",
                "⚖️ <b>Стандарт</b> — тип, викладач, домашка, посилання.",
                "🧾 <b>Все</b> — плюс аудиторії й вікна між парами.",
            )
        )
        doc.p("<i>Пресет змінює лише вигляд, сповіщення лишаються як були.</i>")
        rows.append([btn(label, SetCb(a="preset", v=name)) for name, label in PRESET_LABELS.items()])
    else:
        titles = {"view": "👁 Вигляд розкладу", "notify": "🔔 Сповіщення", "other": "🧩 Інше"}
        doc = Doc().h(titles.get(section, "⚙️"))
        toggles = SECTIONS.get(section, ())
        buttons = [
            btn(f"{_onoff(getattr(prefs, key))} {label}", SetCb(a="tog", k=key, v=section),
                "success" if getattr(prefs, key) else None)
            for key, label in toggles
        ]  # fmt: skip
        rows.extend(grid(buttons, 1 if section == "notify" else 2))
        if section == "notify":
            doc.p("<i>У тихі години сповіщення приходять без звуку.</i>")
            rows.append([btn(f"⏰ Нагадування: {prefs.remind_before or 'вимк.'} хв", SetCb(a="remind"))])
            rows.append(
                [btn(f"🌅 {prefs.morning_time}", SetCb(a="time", k="morning_time")),
                 btn(f"🌙 {prefs.evening_time}", SetCb(a="time", k="evening_time"))]
            )  # fmt: skip
            rows.append(
                [btn(f"🤫 з {prefs.quiet_from}", SetCb(a="time", k="quiet_from")),
                 btn(f"🤫 до {prefs.quiet_to}", SetCb(a="time", k="quiet_to"))]
            )  # fmt: skip
        elif section == "view":
            doc.p("<i>Натискай, щоб увімкнути чи вимкнути. ✅ — показується.</i>")
    rows.append([btn("← Налаштування", SetCb(a="open", k="root")), btn("🏠", Nav(to="menu"))])
    return doc, kb(*rows)


def time_screen(key: str, prefs: Prefs, hour: int | None) -> tuple[Doc, InlineKeyboardMarkup]:
    current = getattr(prefs, key)
    doc = Doc().h(TIME_KEYS.get(key, "🕐 Час")).p(f"Зараз: <b>{current}</b>")
    if hour is None:
        doc.p("Обери годину:")
        buttons = [btn(f"{h:02d}", SetCb(a="time", k=key, v=str(h))) for h in range(24)]
        rows = grid(buttons, 6)
    else:
        doc.p("Обери хвилини:")
        rows = [
            # ":" is the callback-data separator, so the time travels as "HHMM".
            [btn(f"{hour:02d}:{m:02d}", SetCb(a="timeset", k=key, v=f"{hour:02d}{m:02d}")) for m in (0, 15, 30, 45)]
        ]
        rows.append([btn("← Інша година", SetCb(a="time", k=key))])
    rows.append([btn("← Сповіщення", SetCb(a="open", k="notify"))])
    return doc, kb(*rows)


def remind_screen(prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h("⏰ Нагадування перед парою").p("За скільки хвилин нагадувати?")
    buttons = [
        btn(
            ("✅ " if prefs.remind_before == m else "") + (f"{m} хв" if m else "Вимкнути"),
            SetCb(a="remindset", v=str(m)),
        )
        for m in REMIND_CHOICES
    ]
    rows = grid(buttons, 3)
    rows.append([btn("← Сповіщення", SetCb(a="open", k="notify"))])
    return doc, kb(*rows)


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def msg_settings(message: Message, prefs: Prefs) -> None:
    await ui.show(message, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(Nav.filter(F.to == "settings"))
async def cb_settings(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "open"))
async def cb_open(callback: CallbackQuery, callback_data: SetCb, prefs: Prefs) -> None:
    screen = root_screen(prefs) if callback_data.k == "root" else section_screen(callback_data.k, prefs)
    await ui.show(callback, *screen, rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "tog"))
async def cb_toggle(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    key = callback_data.k
    if key not in Prefs.model_fields or not isinstance(getattr(prefs, key), bool):
        await ui.toast(callback, "Невідоме налаштування")
        return
    setattr(prefs, key, not getattr(prefs, key))
    users.save_prefs(user, prefs)
    await ui.show(callback, *section_screen(callback_data.v or "view", prefs), rich=prefs.rich)
    if key == "reply_keyboard" and isinstance(callback.message, Message):
        if prefs.reply_keyboard:
            await callback.message.answer("⌨️ Кнопки повернулись.", reply_markup=reply_menu(user.role_enum))
        else:
            await callback.message.answer("⌨️ Кнопки сховано. Меню — /menu", reply_markup=ReplyKeyboardRemove())


@router.callback_query(SetCb.filter(F.a == "preset"))
async def cb_preset(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    if callback_data.v not in PRESETS:
        await ui.toast(callback, "Невідомий пресет")
        return
    name: PresetName = callback_data.v
    updated = apply_preset(prefs, name)
    users.save_prefs(user, updated)
    await ui.toast(callback, f"Застосовано: {PRESET_LABELS[name]}")
    await ui.show(callback, *section_screen("view", updated), rich=updated.rich)


@router.callback_query(SetCb.filter(F.a == "time"))
async def cb_time(callback: CallbackQuery, callback_data: SetCb, prefs: Prefs) -> None:
    if callback_data.k not in TIME_KEYS:
        await ui.toast(callback, "Невідоме налаштування")
        return
    hour = int(callback_data.v) if callback_data.v.isdigit() else None
    await ui.show(callback, *time_screen(callback_data.k, prefs, hour), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "timeset"))
async def cb_time_set(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    if callback_data.k not in TIME_KEYS:
        await ui.toast(callback, "Невідоме налаштування")
        return
    raw = callback_data.v
    if len(raw) != 4 or not raw.isdigit() or int(raw[:2]) > 23 or int(raw[2:]) > 59:
        await ui.toast(callback, "Невірний час")
        return
    value = f"{raw[:2]}:{raw[2:]}"
    setattr(prefs, callback_data.k, value)
    if callback_data.k == "morning_time":
        prefs.morning_digest = True
    if callback_data.k == "evening_time":
        prefs.evening_digest = True
    users.save_prefs(user, prefs)
    await ui.toast(callback, f"🕐 {value}")
    await ui.show(callback, *section_screen("notify", prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "remind"))
async def cb_remind(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *remind_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "remindset"))
async def cb_remind_set(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    value = int(callback_data.v) if callback_data.v.isdigit() else 0
    prefs.remind_before = value if value in REMIND_CHOICES else 10
    users.save_prefs(user, prefs)
    await ui.toast(callback, f"⏰ За {value} хв до пари" if value else "⏰ Нагадування вимкнено")
    await ui.show(callback, *section_screen("notify", prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "preview"))
async def cb_preview(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs) -> None:
    doc, _ = await day_screen(session, ctx, user, prefs, ctx.today())
    markup = kb([btn("← Налаштування", SetCb(a="open", k="root")), btn("👁 Вигляд", SetCb(a="open", k="view"))])
    await ui.show(callback, doc, markup, rich=prefs.rich)

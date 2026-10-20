"""/settings — notifications only; the look of the schedule is the same for everyone."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ya32_bot.bot import ui
from ya32_bot.bot.keyboards.callbacks import Nav, SetCb
from ya32_bot.bot.keyboards.common import BTN_SETTINGS, btn, grid, kb
from ya32_bot.bot.render.doc import Doc
from ya32_bot.core.prefs import NOTIFY_TOGGLES, REMIND_CHOICES, Prefs
from ya32_bot.db.models import User
from ya32_bot.services import users

router = Router(name="settings")

TOGGLE_KEYS = {key for key, _ in NOTIFY_TOGGLES}
TIME_KEYS = {
    "morning_time": "🌅 Ранковий розклад",
    "evening_time": "🌙 Вечірній розклад",
    "quiet_from": "🤫 Тихі години з",
    "quiet_to": "🤫 Тихі години до",
}


def _onoff(value: bool) -> str:
    return "✅" if value else "▫️"


def root_screen(prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h("🔔 Сповіщення")
    doc.p("<i>Натисни, щоб увімкнути чи вимкнути. У тихі години сповіщення приходять без звуку.</i>")
    rows: list[list[InlineKeyboardButton]] = grid(
        (btn(f"{_onoff(getattr(prefs, key))} {label}", SetCb(a="tog", k=key)) for key, label in NOTIFY_TOGGLES), 1
    )
    rows.append([btn(f"⏰ Нагадування: {f'за {prefs.remind_before} хв' if prefs.remind_before else 'вимк.'}",
                     SetCb(a="remind"))])  # fmt: skip
    rows.append(
        [btn(f"🌅 {prefs.morning_time}", SetCb(a="time", k="morning_time")),
         btn(f"🌙 {prefs.evening_time}", SetCb(a="time", k="evening_time"))]
    )  # fmt: skip
    rows.append(
        [btn(f"🤫 з {prefs.quiet_from}", SetCb(a="time", k="quiet_from")),
         btn(f"🤫 до {prefs.quiet_to}", SetCb(a="time", k="quiet_to"))]
    )  # fmt: skip
    rows.append([btn("🏠 Меню", Nav(to="menu"))])
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
    rows.append([btn("← Назад", SetCb(a="open"))])
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
    rows.append([btn("← Назад", SetCb(a="open"))])
    return doc, kb(*rows)


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def msg_settings(message: Message, prefs: Prefs) -> None:
    await ui.show(message, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(Nav.filter(F.to == "settings"))
async def cb_settings(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "open"))
async def cb_open(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "tog"))
async def cb_toggle(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    key = callback_data.k
    if key not in TOGGLE_KEYS:
        await ui.toast(callback, "Невідоме налаштування")
        return
    setattr(prefs, key, not getattr(prefs, key))
    users.save_prefs(user, prefs)
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


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
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "remind"))
async def cb_remind(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *remind_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "remindset"))
async def cb_remind_set(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    value = int(callback_data.v) if callback_data.v.isdigit() else 0
    prefs.remind_before = value if value in REMIND_CHOICES else 10
    users.save_prefs(user, prefs)
    await ui.toast(callback, f"⏰ За {value} хв до пари" if value else "⏰ Нагадування вимкнено")
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)

"""Keyboard helpers shared by every screen."""

from __future__ import annotations

import calendar as pycal
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Literal

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from ya32_bot.bot.keyboards.callbacks import CalCb, Nav
from ya32_bot.core.texts_uk import MONTHS, WEEKDAYS_SHORT
from ya32_bot.db.models import Role

Style = Literal["primary", "success", "danger"] | None

# Reply-keyboard captions — handlers match on these exact strings.
BTN_TODAY = "📅 Сьогодні"
BTN_TOMORROW = "➡️ Завтра"
BTN_WEEK = "🗓 Тиждень"
BTN_NOW = "⏱ Зараз"
BTN_HW = "📚 Домашка"
BTN_SETTINGS = "⚙️ Налаштування"
BTN_ADMIN = "🛠 Адмінка"
REPLY_BUTTONS = {BTN_TODAY, BTN_TOMORROW, BTN_WEEK, BTN_NOW, BTN_HW, BTN_SETTINGS, BTN_ADMIN}


def btn(text: str, cb: CallbackData | str, style: Style = None) -> InlineKeyboardButton:
    data = cb if isinstance(cb, str) else cb.pack()
    return InlineKeyboardButton(text=text, callback_data=data, style=style)


def url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def kb(*rows: Sequence[InlineKeyboardButton] | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def grid(buttons: Iterable[InlineKeyboardButton], width: int) -> list[list[InlineKeyboardButton]]:
    out: list[list[InlineKeyboardButton]] = []
    for button in buttons:
        if not out or len(out[-1]) >= width:
            out.append([])
        out[-1].append(button)
    return out


def back(cb: CallbackData, text: str = "← Назад") -> list[InlineKeyboardButton]:
    return [btn(text, cb)]


def home_row() -> list[InlineKeyboardButton]:
    return [btn("🏠 Меню", Nav(to="menu"))]


def reply_menu(role: Role) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW)],
        [KeyboardButton(text=BTN_WEEK), KeyboardButton(text=BTN_NOW)],
        [KeyboardButton(text=BTN_HW), KeyboardButton(text=BTN_SETTINGS)],
    ]
    if role.at_least(Role.ADMIN):
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True, input_field_placeholder="ЯА-32")


def calendar(
    purpose: str, year: int, month: int, *, today: date, x: int = 0, marks: set[date] | None = None
) -> InlineKeyboardMarkup:
    """Month grid. Today is ``·5·``, days with lessons get a dot underneath via ``marks``."""
    marks = marks or set()
    rows: list[list[InlineKeyboardButton]] = []
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    rows.append(
        [
            btn("◀️", CalCb(p=purpose, y=prev_y, m=prev_m, x=x)),
            btn(f"{MONTHS[month - 1]} {year}", CalCb(p=purpose, y=today.year, m=today.month, x=x)),
            btn("▶️", CalCb(p=purpose, y=next_y, m=next_m, x=x)),
        ]
    )
    rows.append([btn(w, "noop") for w in WEEKDAYS_SHORT])
    for week in pycal.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(btn(" ", "noop"))
                continue
            current = date(year, month, day)
            label = f"·{day}·" if current == today else (f"{day}•" if current in marks else str(day))
            row.append(btn(label, CalCb(p=purpose, y=year, m=month, d=day, x=x)))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

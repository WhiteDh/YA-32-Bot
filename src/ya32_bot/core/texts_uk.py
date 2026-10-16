"""Ukrainian calendar words — no ``setlocale``: containers have no ``uk_UA`` locale."""

from __future__ import annotations

from datetime import date

WEEKDAYS = ("Понеділок", "Вівторок", "Середа", "Четвер", "Пʼятниця", "Субота", "Неділя")
WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд")
WEEKDAYS_ACC = ("понеділок", "вівторок", "середу", "четвер", "пʼятницю", "суботу", "неділю")
MONTHS = (
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
)  # fmt: skip
MONTHS_GEN = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)  # fmt: skip


def plural(n: int, one: str, few: str, many: str) -> str:
    """``plural(5, "пара", "пари", "пар")`` → ``"пар"``."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def human_date(day: date) -> str:
    """``5 жовтня``."""
    return f"{day.day} {MONTHS_GEN[day.month - 1]}"


def human_day(day: date) -> str:
    """``Понеділок, 5 жовтня``."""
    return f"{WEEKDAYS[day.weekday()]}, {human_date(day)}"


def human_minutes(minutes: int) -> str:
    """``95`` → ``1 год 35 хв``."""
    hours, mins = divmod(max(minutes, 0), 60)
    if hours and mins:
        return f"{hours} год {mins} хв"
    if hours:
        return f"{hours} год"
    return f"{mins} хв"

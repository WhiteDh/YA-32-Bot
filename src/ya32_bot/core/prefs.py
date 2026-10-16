"""Per-user preferences — what a person sees and when the bot speaks first.

Stored as one JSON column, so a new toggle needs a field here and nothing else:
old rows simply get the default. Unknown keys from the database are ignored.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PresetName = Literal["minimal", "standard", "full"]

REMIND_CHOICES = (0, 5, 10, 15, 30, 60)
TIME_CHOICES = tuple(f"{h:02d}:{m:02d}" for h in range(5, 24) for m in (0, 30))


class Prefs(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    # ── Вигляд ────────────────────────────────────────────────────────────
    show_time: bool = True
    show_kind: bool = True
    show_teacher: bool = True
    show_room: bool = False  # the group does not need rooms — off unless asked
    show_links: bool = True
    show_homework: bool = True
    show_notes: bool = True
    show_cancelled: bool = True
    show_gaps: bool = False  # "вікно" between pairs
    show_week_number: bool = True
    show_weekends: bool = False
    short_names: bool = False
    compact: bool = False
    emoji: bool = True
    rich: bool = True

    # ── Сповіщення ────────────────────────────────────────────────────────
    morning_digest: bool = True
    morning_time: str = "07:30"
    evening_digest: bool = False
    evening_time: str = "20:00"
    remind_before: int = Field(default=10, ge=0, le=180)
    notify_changes: bool = True
    notify_homework: bool = True
    notify_deadlines: bool = True
    quiet_hours: bool = True
    quiet_from: str = "23:00"
    quiet_to: str = "07:00"

    # ── Інше ──────────────────────────────────────────────────────────────
    reply_keyboard: bool = True
    easter_eggs: bool = True

    @classmethod
    def load(cls, raw: dict[str, Any] | None) -> Prefs:
        try:
            return cls.model_validate(raw or {})
        except ValueError:
            return cls()

    def dump(self) -> dict[str, Any]:
        return self.model_dump()

    def is_quiet(self, moment: time) -> bool:
        """Inside quiet hours notifications arrive silently (no sound), never dropped."""
        if not self.quiet_hours:
            return False
        start, end = parse_hhmm(self.quiet_from), parse_hhmm(self.quiet_to)
        if start <= end:
            return start <= moment < end
        return moment >= start or moment < end


VIEW_TOGGLES: tuple[tuple[str, str], ...] = (
    ("show_time", "🕐 Час пари"),
    ("show_kind", "📘 Тип (лекція/практика)"),
    ("show_teacher", "👤 Викладач"),
    ("show_room", "🚪 Аудиторія"),
    ("show_links", "🔗 Посилання"),
    ("show_homework", "📚 Домашка в розкладі"),
    ("show_notes", "📝 Примітки"),
    ("show_cancelled", "❌ Скасовані пари"),
    ("show_gaps", "🪟 Вікна між парами"),
    ("show_week_number", "🔢 Номер тижня"),
    ("show_weekends", "🛋 Порожні вихідні"),
    ("short_names", "✂️ Короткі назви"),
    ("compact", "📏 Компактно"),
    ("emoji", "😀 Емодзі"),
    ("rich", "✨ Новий вигляд"),
)

NOTIFY_TOGGLES: tuple[tuple[str, str], ...] = (
    ("morning_digest", "🌅 Ранковий розклад"),
    ("evening_digest", "🌙 Вечірній — на завтра"),
    ("notify_changes", "🔔 Зміни в розкладі"),
    ("notify_homework", "📚 Нова домашка"),
    ("notify_deadlines", "🔥 Дедлайни на завтра"),
    ("quiet_hours", "🤫 Тихі години (без звуку)"),
)

OTHER_TOGGLES: tuple[tuple[str, str], ...] = (
    ("reply_keyboard", "⌨️ Кнопки внизу екрана"),
    ("easter_eggs", "🥚 Пасхалки"),
)

PRESETS: dict[PresetName, dict[str, bool]] = {
    "minimal": {
        "show_time": True, "show_kind": False, "show_teacher": False, "show_room": False,
        "show_links": False, "show_homework": False, "show_notes": False, "show_cancelled": False,
        "show_gaps": False, "show_week_number": False, "short_names": True, "compact": True,
    },
    "standard": {
        "show_time": True, "show_kind": True, "show_teacher": True, "show_room": False,
        "show_links": True, "show_homework": True, "show_notes": True, "show_cancelled": True,
        "show_gaps": False, "show_week_number": True, "short_names": False, "compact": False,
    },
    "full": {
        "show_time": True, "show_kind": True, "show_teacher": True, "show_room": True,
        "show_links": True, "show_homework": True, "show_notes": True, "show_cancelled": True,
        "show_gaps": True, "show_week_number": True, "short_names": False, "compact": False,
    },
}  # fmt: skip
PRESET_LABELS: dict[PresetName, str] = {"minimal": "🪶 Мінімум", "standard": "⚖️ Стандарт", "full": "🧾 Все"}


def apply_preset(prefs: Prefs, name: PresetName) -> Prefs:
    return prefs.model_copy(update=PRESETS[name])


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))

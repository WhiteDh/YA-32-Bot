"""Shared bits of the admin panel."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ya32_bot.bot.keyboards.callbacks import Adm, Nav
from ya32_bot.bot.keyboards.common import btn, kb
from ya32_bot.bot.render.doc import Doc
from ya32_bot.core.prefs import Prefs, apply_preset
from ya32_bot.core.timetable import LessonKind
from ya32_bot.db.models import Role, User

FIELD_LABELS = {
    "subject": "назву предмета",
    "teacher": "викладача",
    "room": "аудиторію",
    "note": "примітку",
}
CLEAR_WORDS = {"-", "—", "нема", "немає", "очистити", "clear"}


def editor_prefs(prefs: Prefs) -> Prefs:
    """Admins edit with everything visible, whatever their personal view is."""
    full = apply_preset(prefs, "full")
    full.show_gaps = False
    return full


def kind_row(action: str, *, d: int = 0, s: int = 0, ref: int = 0) -> list[InlineKeyboardButton]:
    return [btn(f"{k.emoji} {k.label}", Adm(a=action, d=d, s=s, id=ref, v=k.value)) for k in LessonKind]


def clean_value(text: str, limit: int = 255) -> str | None:
    value = text.strip()
    if value.lower() in CLEAR_WORDS:
        return None
    return value[:limit] or None


def admin_menu(user: User) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h("🛠 Адмінка").p("Що редагуємо?")
    rows = [
        [btn("✏️ Редагувати день", Adm(a="pickday"), "primary"), btn("🗂 Шаблон тижня", Adm(a="tpl"), "primary")],
        [btn("🔄 Синхронізація КПІ", Adm(a="sync"), "success"), btn("🗓 Семестр і канікули", Adm(a="sem"))],
        [btn("📘 Предмети й посилання", Adm(a="subj")), btn("📜 Журнал правок", Adm(a="log"))],
        [btn("📣 Оголошення", Adm(a="bc")), btn("📊 Статистика", Adm(a="stats"))],
    ]
    if user.role_enum.at_least(Role.OWNER):
        rows.append([btn("👥 Люди й ролі", Adm(a="people"))])
    rows.append([btn("🏠 Меню", Nav(to="menu"))])
    return doc, kb(*rows)

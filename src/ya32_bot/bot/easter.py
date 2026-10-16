"""Easter eggs — small, harmless, switchable off in /settings.

State lives in ``User.fun`` (JSON): found eggs, the «наступний» tap streak, one-shot dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ya32_bot.db.models import User

CONFETTI = "5046509860389126442"  # 🎉 message effect (private chats only)

EGGS: dict[str, str] = {
    "avatar": "🌊 Чотири стихії",
    "coffee": "☕ Кавова перерва",
    "ya32": "🏆 ЯА-32 forever",
    "semester_end": "🎊 Кінець семестру",
    "sleep": "😴 Нічний сова",
    "answer42": "🌌 Відповідь на все",
    "secrets": "🔍 Шукач",
}

NEXT_STREAK_GOAL = 32
STREAK_WINDOW = timedelta(minutes=10)

AVATAR_FRAMES = (
    "🌊 Вода.",
    "🌊 Вода. 🪨 Земля.",
    "🌊 Вода. 🪨 Земля. 🔥 Вогонь.",
    "🌊 Вода. 🪨 Земля. 🔥 Вогонь. 🌪 Повітря.",
    "Колись чотири народи жили в мирі…",
    "Та все змінилося, коли почалася <b>сесія</b>. 📚🔥",
    "Лише <b>Аватар</b>, володар усіх чотирьох пар на день, міг її зупинити…",
    "Але коли світ потребував його найбільше — він проспав першу пару. 😴",
    "🧘 <i>Та я вірю: ЯА-32 врятує цей семестр.</i>",
)


def _fun(user: User) -> dict[str, Any]:
    return dict(user.fun or {})


def found(user: User, egg: str) -> bool:
    """Mark ``egg`` found; ``True`` the first time."""
    fun = _fun(user)
    eggs = list(fun.get("eggs", []))
    if egg in eggs:
        return False
    eggs.append(egg)
    fun["eggs"] = eggs
    user.fun = fun
    return True


def found_list(user: User) -> list[str]:
    return [e for e in _fun(user).get("eggs", []) if e in EGGS]


def next_tap(user: User, now: datetime) -> bool:
    """Count consecutive «наступний день» taps; ``True`` exactly when the goal is first hit."""
    fun = _fun(user)
    last_raw = fun.get("next_at")
    streak = int(fun.get("next_streak", 0))
    last = datetime.fromisoformat(last_raw) if last_raw else None
    streak = streak + 1 if last is not None and now - last <= STREAK_WINDOW else 1
    fun["next_streak"] = streak
    fun["next_at"] = now.isoformat()
    user.fun = fun
    return streak == NEXT_STREAK_GOAL and found(user, "ya32")


def reset_streak(user: User) -> None:
    fun = _fun(user)
    if fun.get("next_streak"):
        fun["next_streak"] = 0
        user.fun = fun


def once_per_day(user: User, key: str, today: date) -> bool:
    """``True`` the first time ``key`` is asked for on ``today``."""
    fun = _fun(user)
    if fun.get(key) == today.isoformat():
        return False
    fun[key] = today.isoformat()
    user.fun = fun
    return True


COFFEE_WORDS = ("кава", "кави", "каву", "кофе", "coffee", "☕")
AVATAR_TRIGGERS = ("вода, земля, вогонь", "вода земля вогонь", "water, earth, fire", "аватар")

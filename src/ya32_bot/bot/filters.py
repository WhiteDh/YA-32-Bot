"""Role gates for routers and single handlers."""

from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from ya32_bot.db.models import Role, User


class HasRole(Filter):
    def __init__(self, role: Role) -> None:
        self.role = role

    async def __call__(self, _event: Message | CallbackQuery, **data: Any) -> bool:
        # No alert here: as a router filter this sees updates meant for other routers too.
        # A denied admin button is answered by the catch-all in handlers/fallback.py.
        user: User | None = data.get("user")
        return user is not None and user.role_enum.at_least(self.role)

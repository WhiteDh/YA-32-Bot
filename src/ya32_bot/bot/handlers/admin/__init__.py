"""Admin panel — everything here needs at least :attr:`Role.ADMIN`."""

from __future__ import annotations

from aiogram import Router

from ya32_bot.bot.filters import HasRole
from ya32_bot.bot.handlers.admin import day, panel, semester, subjects, sync, template
from ya32_bot.db.models import Role

router = Router(name="admin")
router.message.filter(HasRole(Role.ADMIN))
router.callback_query.filter(HasRole(Role.ADMIN))
router.include_routers(panel.router, day.router, template.router, sync.router, semester.router, subjects.router)

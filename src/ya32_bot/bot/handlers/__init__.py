"""Router assembly. Order matters: commands and FSM-state handlers before free-text matchers."""

from __future__ import annotations

from aiogram import F, Router

from ya32_bot.bot.handlers import admin, easter, fallback, homework, inline, schedule, search, settings, start


def _detached(router: Router) -> Router:
    """Module-level routers may be attached once; a rebuilt dispatcher (tests) re-attaches them."""
    parent = router.parent_router
    if parent is not None:
        parent.sub_routers.remove(router)
        router._parent_router = None
    return router


def build_router() -> Router:
    root = Router(name="root")
    private = Router(name="private")
    private.message.filter(F.chat.type == "private")
    private.include_routers(
        *map(
            _detached,
            (
                start.router,  # /start, /cancel, /menu
                admin.router,  # admin text input (EditField, Broadcast…) before free-text matchers
                homework.router,
                settings.router,
                schedule.router,
                search.router,
                easter.router,
                fallback.router,
            ),
        )
    )
    root.include_routers(_detached(inline.router), private)
    return root

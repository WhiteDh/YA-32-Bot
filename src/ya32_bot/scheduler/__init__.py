"""APScheduler jobs: the minute tick (digests, reminders) and the daily KPI check."""

from __future__ import annotations

import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Adm
from ya32_bot.bot.keyboards.common import btn, kb
from ya32_bot.bot.notify import Notifier
from ya32_bot.bot.render.doc import Doc
from ya32_bot.services import sync
from ya32_bot.services.kv import kv_get
from ya32_bot.services.sources.base import SourceError

logger = logging.getLogger(__name__)


def build_scheduler(ctx: AppContext, notifier: Notifier) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ctx.settings.tz)
    scheduler.add_job(
        notifier.tick, CronTrigger(second=2, timezone=ctx.settings.tz), id="tick", max_instances=1, coalesce=True
    )
    if ctx.settings.heartbeat_file:
        scheduler.add_job(heartbeat, "interval", seconds=60, args=(ctx.settings.heartbeat_file,), id="heartbeat")
        heartbeat(ctx.settings.heartbeat_file)
    if ctx.settings.kpi_autosync:
        scheduler.add_job(
            kpi_check,
            CronTrigger(hour=ctx.settings.kpi_sync_hour, minute=15, timezone=ctx.settings.tz),
            args=(ctx, notifier),
            id="kpi_check",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
    return scheduler


def heartbeat(path: str) -> None:
    Path(path).touch()


async def kpi_check(ctx: AppContext, notifier: Notifier) -> None:
    """Fetch KPI; if something new appeared, tell the admins (or apply «Оновити» if allowed)."""
    async with ctx.db.session() as session:
        auto = await kv_get(session, "kpi_auto")
        if not auto.get("check", True):
            return
        try:
            schedule = await ctx.source.fetch()
        except SourceError:
            logger.warning("kpi auto-check failed", exc_info=True)
            return
        state = await sync.state(session)
        seen_before = state.get("seen_hash") == sync.fingerprint(schedule)
        diff = await sync.diff(session, schedule)
        if diff.empty:
            await sync.remember(session, schedule, now=ctx.now(), applied=False)
            await session.commit()
            return
        if auto.get("apply"):
            result = await sync.apply(
                session, schedule, sync.SyncMode.UPDATE, user_id=None, today=ctx.today(), now=ctx.now()
            )
            await session.commit()
            doc = (
                Doc()
                .h("🤖 Розклад КПІ оновлено автоматично")
                .p(f"+{result.added} ~{result.changed} −{result.removed}. Скасувати можна в журналі.")
            )
            await notifier.to_admins(doc, kb([btn("📜 Журнал", Adm(a="log"))]))
            return
        await sync.remember(session, schedule, now=ctx.now(), applied=False)
        await session.commit()
    if seen_before:
        return  # already told the admins about exactly this version
    doc = (
        Doc()
        .h("🔔 У КПІ змінився розклад")
        .p(
            f"➕ нових: {len(diff.added)} · ✏️ змінених: {len(diff.changed)} · ➖ зниклих: {len(diff.removed)}",
            "Переглянь і застосуй, якщо все гаразд.",
        )
    )
    await notifier.to_admins(doc, kb([btn("🔍 Переглянути", Adm(a="sychk"), "primary")]))

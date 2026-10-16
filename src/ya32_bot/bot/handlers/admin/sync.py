"""«🔄 Синхронізація КПІ»: check → preview the diff → apply in a chosen mode."""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Adm
from ya32_bot.bot.keyboards.common import btn, kb, url_btn
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.core.calendar import monday_of
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import WEEKDAYS_SHORT
from ya32_bot.db.models import User
from ya32_bot.services import semester, sync
from ya32_bot.services.kv import kv_get, kv_set
from ya32_bot.services.sources.base import SourceError, SourceLesson, SourceSchedule

router = Router(name="admin_sync")

AUTO_KEY = "kpi_auto"
PREVIEW_LINES = 8
FIELD_NAMES = {"teacher": "викладач", "room": "аудиторія", "room_url": "посилання", "dates": "дати"}


def _when(raw: str | None) -> str:
    if not raw:
        return "ще ні разу"
    try:
        return datetime.fromisoformat(raw).strftime("%d.%m %H:%M")
    except ValueError:
        return raw


def _line(lesson: SourceLesson) -> str:
    return f"{lesson.week}т · {WEEKDAYS_SHORT[lesson.weekday]} · {lesson.slot} · {esc(lesson.subject[:40])}"


async def auto_settings(session: AsyncSession) -> dict[str, bool]:
    raw = await kv_get(session, AUTO_KEY)
    return {"check": bool(raw.get("check", True)), "apply": bool(raw.get("apply", False))}


async def sync_home(session: AsyncSession, ctx: AppContext) -> tuple[Doc, InlineKeyboardMarkup]:
    state = await sync.state(session)
    auto = await auto_settings(session)
    source = ctx.source
    doc = Doc().h("🔄 Синхронізація з КПІ")
    doc.quote(
        f"🌐 Джерело: <b>{esc(source.title)}</b>",
        f"🔍 Остання перевірка: {_when(state.get('checked_at'))}",
        f"✅ Останнє застосування: {_when(state.get('applied_at'))}",
        f"🤖 Автоперевірка щодня о {ctx.settings.kpi_sync_hour:02d}:15: <b>{'так' if auto['check'] else 'ні'}</b>",
        f"⚡ Автозастосування «Оновити»: <b>{'так' if auto['apply'] else 'ні'}</b>",
    )
    doc.p(
        "<b>➕ Дозавантажити</b> — лише додати нові пари.",
        "<b>🔄 Оновити</b> — привести пари з КПІ у відповідність; ручні правки (✋) не чіпає.",
        "<b>♻️ Перезавантажити</b> — стерти шаблон і завантажити заново.",
        "<i>Разові зміни на дати, домашка й посилання не зачіпаються ніколи. Усе можна скасувати в журналі.</i>",
    )
    rows: list[list[InlineKeyboardButton]] = [
        [btn("🔍 Перевірити зараз", Adm(a="sychk"), "primary")],
        [
            btn(f"{'✅' if auto['check'] else '▫️'} Автоперевірка", Adm(a="syauto", v="check")),
            btn(f"{'✅' if auto['apply'] else '▫️'} Автооновлення", Adm(a="syauto", v="apply")),
        ],
    ]
    page = getattr(source, "page_url", None)
    if isinstance(page, str):
        rows.append([url_btn("🌐 Відкрити розклад на сайті", page)])
    rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


def diff_doc(diff: sync.SyncDiff, schedule: SourceSchedule) -> Doc:
    doc = Doc().h("🔍 Що змінилось у КПІ")
    weeks = f" · зараз {schedule.current_week}-й тиждень" if schedule.current_week else ""
    doc.p(f"<i>У джерелі {diff.total_source} пар{weeks}. Вручну змінених у нас: {diff.manual}.</i>")
    if diff.empty:
        doc.quote("✅ Усе збігається — нічого оновлювати.")
    if diff.added:
        extra = f"\n… і ще {len(diff.added) - PREVIEW_LINES}" if len(diff.added) > PREVIEW_LINES else ""
        doc.h(f"➕ Нові: {len(diff.added)}", 3).quote(*(_line(x) for x in diff.added[:PREVIEW_LINES]), extra.strip())
    if diff.changed:
        doc.h(f"✏️ Змінені: {len(diff.changed)}", 3).quote(
            *(
                f"{_line(c.lesson)} — {', '.join(FIELD_NAMES[f] for f in c.fields)}"
                for c in diff.changed[:PREVIEW_LINES]
            )
        )
    if diff.removed:
        doc.h(f"➖ Зникли з КПІ: {len(diff.removed)}", 3).quote(
            *(
                f"{r.week}т · {WEEKDAYS_SHORT[r.weekday]} · {r.slot} · {esc(r.subject[:40])}"
                for r in diff.removed[:PREVIEW_LINES]
            )
        )
    if schedule.warnings:
        doc.quote(*(f"⚠️ {esc(w)}" for w in schedule.warnings[:5]), expandable=True)
    return doc


def diff_kb(diff: sync.SyncDiff) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if diff.added:
        rows.append([btn(f"➕ Дозавантажити ({len(diff.added)})", Adm(a="syapp", v="append"), "success")])
    if not diff.empty:
        rows.append([btn("🔄 Оновити", Adm(a="syapp", v="update"), "primary")])
    rows.append([btn("♻️ Перезавантажити повністю", Adm(a="syrel"), "danger")])
    rows.append([btn("📅 Межі семестру з КПІ", Adm(a="sysem"))])
    rows.append([btn("← Синхронізація", Adm(a="sync"))])
    return kb(*rows)


async def _fetch(callback: CallbackQuery, ctx: AppContext, user: User) -> SourceSchedule | None:
    try:
        schedule = await ctx.source.fetch()
    except SourceError as exc:
        await ui.toast(callback, f"⚠️ {exc}", alert=True)
        return None
    ctx.pending_sync[user.id] = schedule
    return schedule


@router.callback_query(Adm.filter(F.a == "sync"))
async def cb_home(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    await ui.show(callback, *await sync_home(session, ctx), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "sychk"))
async def cb_check(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, user: User) -> None:
    await ui.toast(callback, "🔍 Питаю КПІ…")
    schedule = await _fetch(callback, ctx, user)
    if schedule is None:
        return
    diff = await sync.diff(session, schedule)
    await sync.remember(session, schedule, now=ctx.now(), applied=False)
    await ui.show(callback, diff_doc(diff, schedule), diff_kb(diff))


@router.callback_query(Adm.filter(F.a == "syapp"))
async def cb_apply(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User
) -> None:
    schedule = ctx.pending_sync.pop(user.id, None) or await _fetch(callback, ctx, user)
    if schedule is None:
        return
    try:
        mode = sync.SyncMode(callback_data.v)
    except ValueError:
        await ui.toast(callback, "Невідомий режим")
        return
    result = await sync.apply(session, schedule, mode, user_id=user.id, today=ctx.today(), now=ctx.now())
    week = f", тиждень: {result.week_set}-й" if result.week_set else ""
    await ui.toast(callback, f"✅ +{result.added} ~{result.changed} −{result.removed}{week}", alert=True)
    await ui.show(callback, *await sync_home(session, ctx))


@router.callback_query(Adm.filter(F.a == "syrel"))
async def cb_reload_confirm(callback: CallbackQuery) -> None:
    doc = (
        Doc()
        .h("♻️ Перезавантажити шаблон?")
        .p(
            "Весь шаблон тижня (і ручні пари ✋ теж) буде замінено розкладом з КПІ.",
            "Разові зміни, домашка й посилання лишаться. Скасувати можна в журналі.",
        )
    )
    markup = kb([btn("♻️ Так, перезавантажити", Adm(a="syapp", v="reload"), "danger")], [btn("← Ні", Adm(a="sync"))])
    await ui.show(callback, doc, markup)


@router.callback_query(Adm.filter(F.a == "syauto"))
async def cb_auto(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext) -> None:
    auto = await auto_settings(session)
    if callback_data.v in auto:
        auto[callback_data.v] = not auto[callback_data.v]
        await kv_set(session, AUTO_KEY, dict(auto))
    await ui.show(callback, *await sync_home(session, ctx))


@router.callback_query(Adm.filter(F.a == "sysem"))
async def cb_semester_from_source(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, user: User) -> None:
    """KPI dates mark lectures only, so they give the semester start but not its end."""
    schedule = ctx.pending_sync.get(user.id) or await _fetch(callback, ctx, user)
    if schedule is None:
        return
    dates = [d for lesson in schedule.lessons for d in lesson.dates]
    if not dates:
        await ui.toast(callback, "У КПІ немає дат, з яких можна взяти початок семестру", alert=True)
        return
    start = monday_of(min(dates))
    await semester.set_semester_bounds(session, start=start)
    await ui.toast(callback, f"📅 Початок семестру: {start:%d.%m}. Кінець задай у «Семестр і канікули».", alert=True)

"""Admin menu, statistics, edit journal, announcements, people & roles, and the shared text input."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import commands, ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.filters import HasRole
from ya32_bot.bot.handlers.admin.common import admin_menu
from ya32_bot.bot.handlers.admin.day import apply_day_field
from ya32_bot.bot.handlers.admin.template import apply_template_field
from ya32_bot.bot.keyboards.callbacks import Adm
from ya32_bot.bot.keyboards.common import BTN_ADMIN, btn, kb
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.states import Broadcast, EditField
from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import AuditLog, Homework, Override, Role, TemplateLesson, User, utcnow
from ya32_bot.services import audit, sync, users

router = Router(name="admin_panel")

PEOPLE_PAGE = 10


@router.message(Command("admin"))
@router.message(F.text == BTN_ADMIN)
async def msg_menu(message: Message, user: User, prefs: Prefs, state: FSMContext) -> None:
    await state.clear()
    await ui.show(message, *admin_menu(user), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "menu"))
async def cb_menu(callback: CallbackQuery, user: User, prefs: Prefs, state: FSMContext) -> None:
    await state.clear()
    await ui.show(callback, *admin_menu(user), rich=prefs.rich)


# ── Shared text input for lesson fields ────────────────────────────────────


@router.message(EditField.value, F.text)
async def edit_field_value(
    message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs, state: FSMContext
) -> None:
    data: dict[str, Any] = await state.get_data()
    await state.clear()
    if data.get("target") == "tpl":
        await apply_template_field(message, session, user, prefs, data)
    else:
        await apply_day_field(message, session, ctx, user, prefs, data)


# ── Statistics ─────────────────────────────────────────────────────────────


async def _count(session: AsyncSession, model: type[Any]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@router.callback_query(Adm.filter(F.a == "stats"))
async def cb_stats(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    people = await users.all_users(session, include_blocked=True)
    week_ago = utcnow() - timedelta(days=7)
    active = len([p for p in people if _aware(p.last_seen) >= week_ago])
    blocked = sum(1 for p in people if p.blocked)
    by_role: dict[Role, int] = {}
    for person in people:
        by_role[person.role_enum] = by_role.get(person.role_enum, 0) + 1
    state = await sync.state(session)
    doc = Doc().h("📊 Статистика")
    doc.quote(
        f"👥 Людей: <b>{len(people)}</b> · активних за тиждень: <b>{active}</b>",
        f"🚫 Заблокували бота: {blocked}",
        *(f"{role.label}: {count}" for role, count in sorted(by_role.items(), key=lambda x: -x[0].rank)),
    )
    doc.quote(
        f"🗂 Пар у шаблоні: {await _count(session, TemplateLesson)}",
        f"✏️ Разових змін: {await _count(session, Override)}",
        f"📚 Домашок: {await _count(session, Homework)}",
        f"📜 Записів у журналі: {await _count(session, AuditLog)}",
        f"🔄 Синхронізація: {esc(state.get('applied_at', 'ще ні разу')[:16].replace('T', ' '))}",
        f"🤖 Версія бота: {esc(ctx.settings.version)}",
    )
    await ui.show(callback, doc, kb([btn("🛠 Адмінка", Adm(a="menu"))]), rich=prefs.rich)


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes even for timezone=True columns; they are UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ── Journal with undo ──────────────────────────────────────────────────────


async def journal_screen(session: AsyncSession, ctx: AppContext) -> tuple[Doc, Any]:
    entries = await audit.recent(session, 12)
    authors = {u.id: u.first_name for u in await users.all_users(session, include_blocked=True)}
    doc = Doc().h("📜 Журнал правок")
    if not entries:
        doc.quote("<i>Поки порожньо.</i>")
    lines = []
    for e in entries:
        who = esc(authors.get(e.user_id or 0, "бот"))
        when = _aware(e.created_at).astimezone(ctx.tz).strftime("%d.%m %H:%M")
        undone = " <s>скасовано</s>" if e.undone else ""
        lines.append(f"<b>#{e.id}</b> {when} · {who}{undone}\n{esc(e.summary)}")
    if lines:
        doc.quote(*lines, expandable=len(lines) > 6)
    rows: list[list[InlineKeyboardButton]] = []
    undoable = [e for e in entries if not e.undone][:6]
    for i in range(0, len(undoable), 3):
        rows.append([btn(f"↩️ #{e.id}", Adm(a="undo", id=e.id)) for e in undoable[i : i + 3]])
    rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


@router.callback_query(Adm.filter(F.a == "log"))
async def cb_log(callback: CallbackQuery, session: AsyncSession, ctx: AppContext, prefs: Prefs) -> None:
    await ui.show(callback, *await journal_screen(session, ctx), rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "undo"))
async def cb_undo(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, prefs: Prefs
) -> None:
    entry = await audit.undo(session, callback_data.id)
    await ui.toast(callback, f"↩️ Скасовано: {entry.summary}" if entry else "Це вже скасовано")
    await ui.show(callback, *await journal_screen(session, ctx), rich=prefs.rich)


# ── Announcement ───────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.a == "bc"))
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.text)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("📣 Надішли текст оголошення для всієї групи (/cancel — скасувати).")


@router.message(Broadcast.text, F.text)
async def broadcast_preview(message: Message, state: FSMContext, prefs: Prefs) -> None:
    text = (message.text or "").strip()[:3500]
    await state.update_data(text=text)
    doc = Doc().h("📣 Попередній перегляд").p(esc(text))
    markup = kb([btn("📣 Надіслати всім", Adm(a="bcok"), "success"), btn("✖️ Скасувати", Adm(a="menu"), "danger")])
    await ui.show(message, doc, markup, rich=prefs.rich)


@router.callback_query(Adm.filter(F.a == "bcok"), Broadcast.text)
async def cb_broadcast_send(callback: CallbackQuery, ctx: AppContext, user: User, state: FSMContext) -> None:
    text = str((await state.get_data()).get("text", ""))
    await state.clear()
    if not text or ctx.notifier is None:
        await ui.toast(callback, "Нічого надсилати")
        return
    await ui.toast(callback, "📣 Надсилаю…")
    count = await ctx.notifier.announce(text, author=user)
    if isinstance(callback.message, Message):
        await callback.message.answer(f"✅ Оголошення отримали {count} людей.")


# ── People & roles (owner) ─────────────────────────────────────────────────

owner = Router(name="admin_owner")
owner.callback_query.filter(HasRole(Role.OWNER))
router.include_router(owner)


async def people_screen(session: AsyncSession, page: int) -> tuple[Doc, Any]:
    people = await users.all_users(session, include_blocked=True)
    people.sort(key=lambda p: (-p.role_enum.rank, p.first_name.lower()))
    total_pages = max(1, (len(people) + PEOPLE_PAGE - 1) // PEOPLE_PAGE)
    page = min(max(page, 0), total_pages - 1)
    chunk = people[page * PEOPLE_PAGE : (page + 1) * PEOPLE_PAGE]
    doc = Doc().h("👥 Люди й ролі").p(f"<i>Усього {len(people)} · сторінка {page + 1}/{total_pages}</i>")
    rows: list[list[InlineKeyboardButton]] = [
        [btn(f"{p.role_enum.label.split()[0]} {p.first_name[:24]}{' 🚫' if p.blocked else ''}", Adm(a="who", id=p.id))]
        for p in chunk
    ]
    nav = []
    if page > 0:
        nav.append(btn("◀️", Adm(a="people", s=page - 1)))
    if page < total_pages - 1:
        nav.append(btn("▶️", Adm(a="people", s=page + 1)))
    if nav:
        rows.append(nav)
    rows.append([btn("🔗 Запрошення з роллю", Adm(a="inv"), "success")])
    rows.append([btn("🛠 Адмінка", Adm(a="menu"))])
    return doc, kb(*rows)


@owner.callback_query(Adm.filter(F.a == "people"))
async def cb_people(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    await ui.show(callback, *await people_screen(session, callback_data.s), rich=prefs.rich)


@owner.callback_query(Adm.filter(F.a == "who"))
async def cb_who(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, prefs: Prefs) -> None:
    person = await session.get(User, callback_data.id)
    if person is None:
        await ui.toast(callback, "Не знайдено")
        return
    handle = f"@{esc(person.username)}" if person.username else "без юзернейму"
    doc = (
        Doc()
        .h(esc(person.first_name or "Без імені"))
        .quote(
            f"🆔 <code>{person.id}</code> · {handle}",
            f"Роль: <b>{esc(person.role_enum.label)}</b>",
            f"З нами з {person.created_at:%d.%m.%Y}",
        )
    )
    rows = [
        [btn(("✅ " if person.role_enum is role else "") + role.label, Adm(a="role", id=person.id, v=role.value))]
        for role in (Role.STUDENT, Role.EDITOR, Role.ADMIN, Role.OWNER)
    ]
    rows.append([btn("← Люди", Adm(a="people"))])
    await ui.show(callback, doc, kb(*rows), rich=prefs.rich)


@owner.callback_query(Adm.filter(F.a == "role"))
async def cb_role(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    try:
        role = Role(callback_data.v)
    except ValueError:
        await ui.toast(callback, "Невідома роль")
        return
    if callback_data.id == user.id and role is not Role.OWNER:
        await ui.toast(callback, "Себе понизити не можна — попроси іншого власника", alert=True)
        return
    if callback_data.id in ctx.settings.owner_ids and role is not Role.OWNER:
        await ui.toast(callback, "Ця людина — власник з OWNER_IDS", alert=True)
        return
    person = await users.set_role(session, callback_data.id, role)
    if person is not None and callback.bot is not None:
        await commands.sync_user_commands(callback.bot, person)
    await ui.toast(callback, f"Роль: {role.label}")
    await cb_who(callback, Adm(a="who", id=callback_data.id), session, prefs)


@owner.callback_query(Adm.filter(F.a == "inv"))
async def cb_invite_pick(callback: CallbackQuery, prefs: Prefs) -> None:
    doc = (
        Doc()
        .h("🔗 Запрошення")
        .p(
            "Посилання одноразове й діє 7 днів. Хто відкриє — отримає роль.",
            "<i>Переглядати розклад можна й без запрошення.</i>",
        )
    )
    markup = kb(
        [
            btn(Role.EDITOR.label, Adm(a="invmk", v=Role.EDITOR.value)),
            btn(Role.ADMIN.label, Adm(a="invmk", v=Role.ADMIN.value)),
        ],
        [btn("← Люди", Adm(a="people"))],
    )
    await ui.show(callback, doc, markup, rich=prefs.rich)


@owner.callback_query(Adm.filter(F.a == "invmk"))
async def cb_invite_make(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs
) -> None:
    try:
        role = Role(callback_data.v)
    except ValueError:
        await ui.toast(callback, "Невідома роль")
        return
    invite = await users.create_invite(session, role, user.id)
    link = f"https://t.me/{ctx.bot_username}?start=inv_{invite.code}"
    doc = Doc().h(f"🔗 Запрошення: {esc(role.label)}").p(f"<code>{esc(link)}</code>", "<i>Натисни, щоб скопіювати.</i>")
    await ui.show(callback, doc, kb([btn("← Люди", Adm(a="people"))]), rich=prefs.rich)

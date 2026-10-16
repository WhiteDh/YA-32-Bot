"""People, roles and invite links."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import Invite, Role, User, utcnow


async def touch(
    session: AsyncSession, user_id: int, first_name: str, username: str | None, owner_ids: list[int]
) -> tuple[User, bool]:
    """Upsert the user on every update. Returns ``(user, created)``."""
    user = await session.get(User, user_id)
    created = user is None
    if user is None:
        user = User(id=user_id, first_name=first_name[:128], username=username, prefs=Prefs().dump(), fun={})
        session.add(user)
    else:
        user.first_name = first_name[:128]
        user.username = username
        user.last_seen = utcnow()
        user.blocked = False
    if user_id in owner_ids and user.role != Role.OWNER.value:
        user.role = Role.OWNER.value
    await session.flush()
    return user, created


def prefs_of(user: User) -> Prefs:
    return Prefs.load(user.prefs)


def save_prefs(user: User, prefs: Prefs) -> None:
    user.prefs = prefs.dump()  # a new dict, so SQLAlchemy sees the change


async def all_users(session: AsyncSession, *, include_blocked: bool = False) -> list[User]:
    query = select(User).order_by(User.created_at)
    if not include_blocked:
        query = query.where(User.blocked.is_(False))
    return list((await session.scalars(query)).all())


async def by_role(session: AsyncSession, at_least: Role) -> list[User]:
    return [u for u in await all_users(session) if u.role_enum.at_least(at_least)]


async def count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(User)) or 0)


async def set_role(session: AsyncSession, user_id: int, role: Role) -> User | None:
    user = await session.get(User, user_id)
    if user is not None:
        user.role = role.value
        await session.flush()
    return user


async def create_invite(session: AsyncSession, role: Role, created_by: int, *, uses: int = 1, days: int = 7) -> Invite:
    invite = Invite(
        code=secrets.token_urlsafe(9),
        role=role.value,
        created_by=created_by,
        uses_left=uses,
        expires_at=utcnow() + timedelta(days=days),
    )
    session.add(invite)
    await session.flush()
    return invite


async def redeem_invite(session: AsyncSession, code: str, user: User, *, now: datetime | None = None) -> Role | None:
    """Promote ``user`` by an invite. Never demotes: an admin opening an editor link stays admin."""
    invite = await session.get(Invite, code)
    moment = now or utcnow()
    if invite is None or invite.uses_left <= 0:
        return None
    expires = invite.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=moment.tzinfo)
    if expires is not None and expires < moment:
        return None
    role = Role(invite.role)
    invite.uses_left -= 1
    if not user.role_enum.at_least(role):
        user.role = role.value
    await session.flush()
    return role

"""ORM models. One group, so no tenant column anywhere.

Portable types only (``JSON``, ``Date``, ``BigInteger``): Postgres in production,
SQLite in tests and for a quick local run.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    STUDENT = "student"
    EDITOR = "editor"  # may add homework
    ADMIN = "admin"  # may edit the schedule
    OWNER = "owner"  # may manage people

    @property
    def rank(self) -> int:
        return ROLE_RANK[self]

    @property
    def label(self) -> str:
        return ROLE_LABELS[self]

    def at_least(self, other: Role) -> bool:
        return self.rank >= other.rank


ROLE_RANK = {Role.STUDENT: 0, Role.EDITOR: 1, Role.ADMIN: 2, Role.OWNER: 3}
ROLE_LABELS = {
    Role.STUDENT: "🎓 Студент",
    Role.EDITOR: "✍️ Редактор ДЗ",
    Role.ADMIN: "🛠 Адмін",
    Role.OWNER: "👑 Власник",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), default=Role.STUDENT.value)
    prefs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Fun counters for the easter eggs (next-taps streak, achievements).
    fun: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # the user blocked the bot
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def role_enum(self) -> Role:
        try:
            return Role(self.role)
        except ValueError:
            return Role.STUDENT


class Subject(Base):
    """Per-subject extras that survive a schedule re-import: short name, emoji, links."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    short: Mapped[str | None] = mapped_column(String(64))
    emoji: Mapped[str | None] = mapped_column(String(16))
    link: Mapped[str | None] = mapped_column(String(512))  # Meet / Zoom / Classroom
    note: Mapped[str | None] = mapped_column(Text)


class TemplateLesson(Base):
    __tablename__ = "template_lessons"
    __table_args__ = (UniqueConstraint("week", "weekday", "slot", "subject", "kind", name="uq_template_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer)  # 1 | 2
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    slot: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default="other")
    teacher: Mapped[str | None] = mapped_column(String(255))
    room: Mapped[str | None] = mapped_column(String(64))
    room_url: Mapped[str | None] = mapped_column(String(512))
    dates: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ISO dates; empty = every such week
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | kpi


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))  # cancel | replace | add
    subject: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str | None] = mapped_column(String(16))
    teacher: Mapped[str | None] = mapped_column(String(255))
    room: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Homework(Base):
    __tablename__ = "homework"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(255))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{"type": "photo", "file_id": "..."}]
    author_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HomeworkDone(Base):
    __tablename__ = "homework_done"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    homework_id: Mapped[int] = mapped_column(Integer, ForeignKey("homework.id", ondelete="CASCADE"), primary_key=True)
    done_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(128), default="Вихідний")


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    uses_left: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="")
    # What undo needs: {"table": ..., "op": "insert|update|delete", "id": ..., "before": {...}}
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class KeyValue(Base):
    """Bot-wide settings: semester dates, week anchor, sync state."""

    __tablename__ = "kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

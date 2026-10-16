"""Typed callback data. Dates travel as ``yyyymmdd`` ints to stay under Telegram's 64 bytes."""

from __future__ import annotations

from datetime import date

from aiogram.filters.callback_data import CallbackData


def d2i(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def i2d(value: int) -> date:
    return date(value // 10000, value // 100 % 100, value % 100)


class Nav(CallbackData, prefix="n"):
    to: str  # menu | now | today | tomorrow | week | nextweek | hw | settings | admin | help


class DayCb(CallbackData, prefix="d"):
    d: int
    step: int = 0  # +1 / -1 when it came from the arrows (easter egg counter)


class WeekCb(CallbackData, prefix="w"):
    d: int  # Monday


class LessonCb(CallbackData, prefix="l"):
    d: int
    s: int


class CalCb(CallbackData, prefix="c"):
    p: str  # purpose: view | edit | hw | move | sem_s | sem_e | hol_s | hol_e
    y: int
    m: int
    d: int = 0  # 0 = navigate months; otherwise the picked day
    x: int = 0  # extra context (slot, holiday start, ...)


class HwCb(CallbackData, prefix="h"):
    a: str  # list | open | done | del | edit | add | pick | hide
    id: int = 0
    d: int = 0
    s: int = 0


class SetCb(CallbackData, prefix="s"):
    a: str  # open | tog | preset | time | timeset | remind | preview
    k: str = ""
    v: str = ""


class Adm(CallbackData, prefix="a"):
    a: str
    d: int = 0
    s: int = 0
    id: int = 0
    v: str = ""

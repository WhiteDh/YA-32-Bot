from datetime import date, datetime, time

import pytest

from ya32_bot.bot.handlers.schedule import parse_date
from ya32_bot.core.calendar import Holiday, Semester, WeekAnchor, monday_of
from ya32_bot.core.prefs import Prefs, apply_preset
from ya32_bot.core.slots import SLOTS, slot_for_start
from ya32_bot.core.texts_uk import human_minutes, plural
from ya32_bot.core.timetable import (
    LessonKind,
    Override,
    OverrideAction,
    TemplateLesson,
    build_day,
    is_break,
    now_status,
)

MON = date(2026, 10, 5)


def tpl(id: int, slot: int, subject: str, *, week: int = 2, weekday: int = 0, dates: tuple[date, ...] = ()):
    return TemplateLesson(id, week, weekday, slot, subject, LessonKind.LECTURE, "Teacher", "17-214", None, dates)


@pytest.mark.parametrize(("value", "slot"), [("08:30:00", 1), ("10:25", 2), ("20:20", 7), ("09:00", None), ("x", None)])
def test_slot_for_start(value, slot):
    assert slot_for_start(value) == slot


def test_week_parity_alternates_and_survives_year_boundary():
    anchor = WeekAnchor(date(2026, 10, 5), 2)
    assert anchor.week_of(date(2026, 10, 9)) == 2
    assert anchor.week_of(date(2026, 10, 12)) == 1
    assert anchor.week_of(date(2026, 9, 28)) == 1
    assert anchor.week_of(date(2027, 1, 4)) == 1  # 13 weeks later


def test_monday_of():
    assert monday_of(date(2026, 10, 11)) == MON


def test_build_day_respects_week_and_dates():
    lessons = [
        tpl(1, 1, "Every week-2 Monday"),
        tpl(2, 2, "Only listed dates", dates=(date(2026, 10, 19),)),
        tpl(3, 3, "Week 1", week=1),
    ]
    day = build_day(MON, 2, lessons, [])
    assert [x.subject for x in day.lessons] == ["Every week-2 Monday"]
    later = build_day(date(2026, 10, 19), 2, lessons, [])
    assert [x.slot for x in later.lessons] == [1, 2]


def test_overrides_cancel_replace_add():
    lessons = [tpl(1, 1, "A"), tpl(2, 2, "B")]
    overrides = [
        Override(10, MON, 1, OverrideAction.CANCEL, note="хворіє"),
        Override(11, MON, 2, OverrideAction.REPLACE, subject="B2", room="1-1"),
        Override(12, MON, 5, OverrideAction.ADD, subject="Extra", kind=LessonKind.LAB),
    ]
    day = build_day(MON, 2, lessons, overrides)
    a, b, extra = day.lessons
    assert a.cancelled and a.note == "хворіє"
    assert b.subject == "B2" and b.room == "1-1" and b.teacher == "Teacher" and b.changed
    assert extra.slot == 5 and extra.kind is LessonKind.LAB
    assert [x.subject for x in day.active] == ["B2", "Extra"]


def test_holiday_empties_the_day():
    day = build_day(MON, 2, [tpl(1, 1, "A")], [], holiday="День захисника")
    assert day.lessons == () and day.holiday == "День захисника"


def test_semester_bounds_and_holidays():
    sem = Semester(date(2026, 9, 1), date(2026, 12, 31), (Holiday(date(2026, 10, 14), date(2026, 10, 14), "Свято"),))
    assert sem.in_session(MON) and not sem.in_session(date(2027, 1, 2))
    assert sem.holiday_on(date(2026, 10, 14)) is not None
    assert sem.days_left(date(2026, 12, 30)) == 1


def test_now_status_inside_a_pair_and_break():
    day = build_day(MON, 2, [tpl(1, 1, "A"), tpl(2, 2, "B"), tpl(3, 3, "C")], [])
    status = now_status(datetime(2026, 10, 5, 10, 40), list(day.lessons))
    assert status.current is not None and status.current.subject == "B"
    assert status.minutes_left == 80
    assert status.next is not None and status.next.subject == "C"
    assert status.lessons_left_today == 1
    assert is_break(datetime(2026, 10, 5, 12, 10), list(day.lessons)) == 10
    assert is_break(datetime(2026, 10, 5, 11, 0), list(day.lessons)) is None


def test_prefs_quiet_hours_wrap_midnight():
    prefs = Prefs(quiet_from="23:00", quiet_to="07:00")
    assert prefs.is_quiet(time(23, 30)) and prefs.is_quiet(time(6, 59))
    assert not prefs.is_quiet(time(7, 0))
    assert not Prefs(quiet_hours=False).is_quiet(time(3, 0))


def test_prefs_ignore_unknown_and_broken_values():
    assert Prefs.load({"nope": 1, "show_room": True}).show_room
    assert Prefs.load({"remind_before": "abc"}) == Prefs()


def test_room_is_hidden_by_default_and_presets_only_touch_view():
    prefs = Prefs(morning_digest=False)
    assert prefs.show_room is False
    full = apply_preset(prefs, "full")
    assert full.show_room and full.morning_digest is False
    assert apply_preset(prefs, "minimal").compact


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12.10", date(2026, 10, 12)),
        ("1/9/2026", date(2026, 9, 1)),
        ("05.01", date(2027, 1, 5)),
        ("31.02", None),
        ("hi", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text, date(2026, 10, 5)) == expected


def test_words():
    assert plural(1, "пара", "пари", "пар") == "пара"
    assert plural(3, "пара", "пари", "пар") == "пари"
    assert plural(11, "пара", "пари", "пар") == "пар"
    assert human_minutes(95) == "1 год 35 хв"
    assert SLOTS[1].label == "08:30–10:05"

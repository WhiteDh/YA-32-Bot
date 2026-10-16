"""Schedule screens: a day, a week, «зараз», a lesson card. Every view honours :class:`Prefs`."""

from __future__ import annotations

from datetime import date, datetime

from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import WEEKDAYS_SHORT, human_date, human_day, human_minutes, plural
from ya32_bot.core.timetable import Lesson, NowStatus
from ya32_bot.db.models import Homework, Subject
from ya32_bot.services.schedule import DayBundle

SKULL_FRIDAY_SLOT = 7


def subject_name(name: str, subjects: dict[str, Subject], prefs: Prefs) -> str:
    extra = subjects.get(name)
    if prefs.short_names and extra and extra.short:
        return extra.short
    return name


def subject_icon(lesson: Lesson, subjects: dict[str, Subject], prefs: Prefs) -> str:
    if not prefs.emoji:
        return ""
    extra = subjects.get(lesson.subject)
    return (extra.emoji if extra and extra.emoji else lesson.kind.emoji) + " "


def bar(progress: float, width: int = 10) -> str:
    filled = round(max(0.0, min(progress, 1.0)) * width)
    return "▰" * filled + "▱" * (width - filled)


def week_label(week: int) -> str:
    return f"{week}-й тиждень"


def _lesson_lines(
    lesson: Lesson, bundle: DayBundle, prefs: Prefs, *, now: datetime | None, eggs: bool
) -> tuple[str, ...]:
    subj = bundle.subjects
    name = esc(subject_name(lesson.subject, subj, prefs))
    icon = subject_icon(lesson, subj, prefs)
    live = now is not None and lesson.starts_at() <= now < lesson.ends_at() and not lesson.cancelled
    marks = ""
    if live:
        marks += " ▶️"
    if lesson.changed and not lesson.cancelled:
        marks += " 🔄"
    if eggs and lesson.date.weekday() == 4 and lesson.slot == SKULL_FRIDAY_SLOT and not lesson.cancelled:
        marks += " 💀"

    head = f"<b>{lesson.slot}</b>"
    if prefs.show_time:
        head += f" · {lesson.time.label}"

    if prefs.compact:
        kind = f" · <i>{esc(lesson.kind.label.lower())}</i>" if prefs.show_kind else ""
        title = f"<s>{name}</s> ❌" if lesson.cancelled else f"<b>{name}</b>"
        line = f"{head}  {icon}{title}{kind}{marks}"
        if prefs.show_homework and not lesson.cancelled and bundle.homework.get(lesson.subject):
            line += " 📚"
        return (line,)

    lines = [head + marks]
    if lesson.cancelled:
        lines.append(f"{icon}<s>{name}</s> — <b>скасовано</b>")
    else:
        kind = f" · <i>{esc(lesson.kind.label)}</i>" if prefs.show_kind else ""
        lines.append(f"{icon}<b>{name}</b>{kind}")
        if prefs.show_teacher and lesson.teacher:
            lines.append(f"👤 {esc(lesson.teacher)}")
        if prefs.show_room and lesson.room:
            room = esc(lesson.room)
            lines.append(f'🚪 <a href="{esc(lesson.room_url)}">{room}</a>' if lesson.room_url else f"🚪 {room}")
        extra = subj.get(lesson.subject)
        if prefs.show_links and extra and extra.link:
            lines.append(f'🔗 <a href="{esc(extra.link)}">Посилання на пару</a>')
    if prefs.show_notes and lesson.note:
        lines.append(f"📝 <i>{esc(lesson.note)}</i>")
    if prefs.show_homework and not lesson.cancelled:
        for hw in bundle.homework.get(lesson.subject, [])[:2]:
            text = hw.text if len(hw.text) <= 90 else hw.text[:89] + "…"
            clip = " 📎" if hw.attachments else ""
            lines.append(f"📚 {esc(text) or 'див. вкладення'}{clip}")
    return tuple(lines)


def day_doc(
    bundle: DayBundle, prefs: Prefs, *, today: date, now: datetime | None = None, title: str | None = None
) -> Doc:
    day = bundle.day
    doc = Doc()
    heading = title or human_day(day.date)
    doc.h(esc(heading))

    meta: list[str] = []
    if title:
        meta.append(human_day(day.date))
    if prefs.show_week_number and not day.holiday and not day.out_of_semester:
        meta.append(week_label(day.week))
    shown = [x for x in day.lessons if prefs.show_cancelled or not x.cancelled]
    if day.active:
        n = len(day.active)
        meta.append(f"{n} {plural(n, 'пара', 'пари', 'пар')}")
    if meta:
        doc.p("<i>" + " · ".join(esc(m) for m in meta) + "</i>")

    if day.holiday:
        doc.quote(f"🎉 <b>{esc(day.holiday)}</b>", "Пар немає — відпочивай!")
        return doc
    if day.out_of_semester:
        doc.quote("🏖 Поза семестром — пар немає.")
        return doc
    if not shown:
        if day.date.weekday() >= 5:
            doc.quote("🛋 Вихідний. Пар немає.")
        else:
            doc.quote("🛋 Пар немає — вільний день!")
        return doc

    live_now = now if day.date == today else None
    previous: Lesson | None = None
    for lesson in shown:
        if prefs.show_gaps and previous is not None and not previous.cancelled and not lesson.cancelled:
            gap = lesson.slot - previous.slot - 1
            if gap > 0:
                minutes = int((lesson.starts_at() - previous.ends_at()).total_seconds() // 60)
                doc.p(f"🪟 <i>Вікно — {human_minutes(minutes)}</i>")
        doc.quote(*_lesson_lines(lesson, bundle, prefs, now=live_now, eggs=prefs.easter_eggs))
        previous = lesson
    return doc


def week_doc(bundles: list[DayBundle], prefs: Prefs, *, today: date) -> Doc:
    first, last = bundles[0].day.date, bundles[-1].day.date
    doc = Doc()
    span = (
        f"{first.day}–{human_date(last)}" if first.month == last.month else f"{human_date(first)} – {human_date(last)}"
    )
    doc.h(f"Тиждень · {esc(span)}")
    weeks = {b.day.week for b in bundles if not b.day.holiday}
    if prefs.show_week_number and len(weeks) == 1:
        doc.p(f"<i>{week_label(weeks.pop())}</i>")

    for bundle in bundles:
        day = bundle.day
        weekend = day.date.weekday() >= 5
        if weekend and not day.lessons and not prefs.show_weekends:
            continue
        marker = " 👈" if day.date == today else ""
        label = f"{WEEKDAYS_SHORT[day.date.weekday()]}, {day.date:%d.%m}{marker}"
        if day.holiday:
            doc.quote(f"<b>{esc(label)}</b>", f"🎉 {esc(day.holiday)}")
            continue
        lines = [f"<b>{esc(label)}</b>"]
        shown = [x for x in day.lessons if prefs.show_cancelled or not x.cancelled]
        if not shown:
            lines.append("<i>пар немає</i>")
        for lesson in shown:
            name = esc(subject_name(lesson.subject, bundle.subjects, prefs))
            icon = subject_icon(lesson, bundle.subjects, prefs)
            when = f"{lesson.time.start:%H:%M} " if prefs.show_time else ""
            title = f"<s>{name}</s>" if lesson.cancelled else name
            kind = f" <i>({esc(lesson.kind.label.lower())})</i>" if prefs.show_kind and not prefs.compact else ""
            hw = " 📚" if prefs.show_homework and bundle.homework.get(lesson.subject) and not lesson.cancelled else ""
            changed = " 🔄" if lesson.changed and not lesson.cancelled else ""
            lines.append(f"{lesson.slot}. {when}{icon}{title}{kind}{hw}{changed}")
        doc.quote(*lines)
    return doc


def now_doc(
    status: NowStatus, prefs: Prefs, subjects: dict[str, Subject], *, now: datetime, break_left: int | None = None
) -> Doc:
    doc = Doc().h(f"⏱ Зараз {now:%H:%M}")
    if status.current is not None:
        cur = status.current
        name = esc(subject_name(cur.subject, subjects, prefs))
        doc.quote(
            f"▶️ <b>{cur.slot} пара</b> · {cur.time.label}",
            f"{subject_icon(cur, subjects, prefs)}<b>{name}</b>",
            f"{bar(status.progress)}  ще <b>{human_minutes(status.minutes_left)}</b>",
        )
    nxt = status.next
    if nxt is not None:
        name = esc(subject_name(nxt.subject, subjects, prefs))
        when = (
            f"о {nxt.time.start:%H:%M}"
            if nxt.date == now.date()
            else f"{human_day(nxt.date).lower()}, {nxt.time.start:%H:%M}"
        )
        lines = [
            f"⏭ <b>Далі: {nxt.slot} пара</b> {esc(when)}",
            f"{subject_icon(nxt, subjects, prefs)}{name}",
        ]
        if nxt.date == now.date():
            lines.append(f"⏳ через <b>{human_minutes(status.minutes_to_next)}</b>")
        doc.quote(*lines)
    if status.current is None and nxt is None:
        doc.quote("🛋 Найближчим часом пар немає.")
    elif break_left is not None:
        doc.p(f"☕ <i>Перерва, ще {human_minutes(break_left)}.</i>")
    if status.lessons_left_today:
        n = status.lessons_left_today
        doc.p(f"<i>Сьогодні ще {n} {plural(n, 'пара', 'пари', 'пар')}.</i>")
    elif nxt is not None and nxt.date != now.date():
        doc.p("<i>На сьогодні все! 🎉</i>")
    return doc


def lesson_doc(lesson: Lesson, bundle: DayBundle, prefs: Prefs, homework: list[Homework], *, now: datetime) -> Doc:
    subjects = bundle.subjects
    doc = Doc().h(f"{subject_icon(lesson, subjects, prefs)}{esc(lesson.subject)}")
    lines = [
        f"📅 {esc(human_day(lesson.date))}",
        f"🕐 {lesson.slot} пара · {lesson.time.label}",
        f"🏷 {esc(lesson.kind.label)}",
    ]
    if lesson.teacher:
        lines.append(f"👤 {esc(lesson.teacher)}")
    if prefs.show_room and lesson.room:
        lines.append(f"🚪 {esc(lesson.room)}")
    if lesson.cancelled:
        lines.append("❌ <b>Скасовано</b>")
    elif lesson.changed:
        lines.append("🔄 <i>Змінено відносно шаблону</i>")
    if lesson.note:
        lines.append(f"📝 {esc(lesson.note)}")
    if lesson.starts_at() <= now < lesson.ends_at() and not lesson.cancelled:
        total = (lesson.ends_at() - lesson.starts_at()).total_seconds()
        left = int((lesson.ends_at() - now).total_seconds() // 60)
        lines.append(f"▶️ {bar((now - lesson.starts_at()).total_seconds() / total)} ще {human_minutes(left)}")
    doc.quote(*lines)

    extra = subjects.get(lesson.subject)
    if extra and extra.note:
        doc.p(f"ℹ️ {esc(extra.note)}")
    if homework:
        doc.h("📚 Домашка", 3)
        for hw in homework:
            text = esc(hw.text) if hw.text else "<i>див. вкладення</i>"
            clip = " 📎" if hw.attachments else ""
            doc.quote(f"<b>до {hw.due_date:%d.%m}</b>{clip}", text, expandable=len(hw.text) > 200)
    return doc

"""Homework screens."""

from __future__ import annotations

from datetime import date

from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.core.texts_uk import WEEKDAYS_SHORT, plural
from ya32_bot.db.models import Homework
from ya32_bot.services.homework import HomeworkItem


def countdown(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return "прострочено"
    if days == 0:
        return "🔥 сьогодні"
    if days == 1:
        return "⚡ завтра"
    return f"через {days} {plural(days, 'день', 'дні', 'днів')}"


def due_label(due: date) -> str:
    return f"{WEEKDAYS_SHORT[due.weekday()]}, {due:%d.%m}"


def list_doc(items: list[HomeworkItem], today: date, *, hide_done: bool) -> Doc:
    doc = Doc().h("📚 Домашка")
    shown = [i for i in items if not (hide_done and i.done)]
    left = sum(1 for i in items if not i.done)
    if not items:
        return doc.quote("🎉 Нічого не задано. Насолоджуйся!")
    doc.p(f"<i>Не зроблено: {left} з {len(items)}</i>")
    if not shown:
        return doc.quote("✅ Усе зроблено! Ти машина.")
    current: date | None = None
    lines: list[str] = []
    for item in shown:
        if item.hw.due_date != current:
            if lines:
                doc.quote(*lines)
            current = item.hw.due_date
            lines = [f"<b>{due_label(current)}</b> · <i>{countdown(current, today)}</i>"]
        mark = "✅" if item.done else "▫️"
        text = item.hw.text if len(item.hw.text) <= 70 else item.hw.text[:69] + "…"
        clip = " 📎" if item.hw.attachments else ""
        name = f"<s>{esc(item.hw.subject)}</s>" if item.done else f"<b>{esc(item.hw.subject)}</b>"
        lines.append(f"{mark} {name}{clip}" + (f" — {esc(text)}" if text else ""))
    if lines:
        doc.quote(*lines)
    return doc


def card_doc(hw: Homework, today: date, *, done: bool, done_total: int, author: str | None) -> Doc:
    doc = Doc().h(f"📚 {esc(hw.subject)}")
    meta = [f"📅 до <b>{due_label(hw.due_date)}</b> · {countdown(hw.due_date, today)}"]
    if hw.slot:
        meta.append(f"🕐 {hw.slot} пара")
    if hw.attachments:
        meta.append(f"📎 вкладень: {len(hw.attachments)}")
    meta.append(f"{'✅ Ти зробив' if done else '▫️ Ще не зроблено'} · зробили: {done_total}")
    if author:
        meta.append(f"✍️ {esc(author)}")
    doc.quote(*meta)
    doc.quote(esc(hw.text) if hw.text else "<i>Текст відсутній — див. вкладення.</i>", expandable=len(hw.text) > 300)
    return doc


def draft_doc(subject: str, due: date, text: str, attachments: int) -> Doc:
    doc = Doc().h("✍️ Нова домашка")
    doc.quote(f"<b>{esc(subject)}</b>", f"📅 до {due_label(due)}", f"📎 вкладень: {attachments}")
    doc.p(
        esc(text) if text else "<i>Поки порожньо.</i>",
        "",
        "Надсилай текст, фото, файли чи голосові — я все зберу.",
        "Коли готово — тисни <b>✅ Зберегти</b>.",
    )
    return doc

from datetime import date

from tests.conftest import NOW
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.render.doc import Doc
from ya32_bot.bot.render.schedule import day_doc, week_doc
from ya32_bot.core.prefs import Prefs, apply_preset
from ya32_bot.services import schedule

WED = date(2026, 10, 7)  # has rooms in KPI data


async def _bundle(ctx: AppContext, when: date):
    async with ctx.db.session() as session:
        return await schedule.day(session, when, today=NOW.date())


async def test_room_hidden_by_default_and_shown_when_enabled(seeded: AppContext):
    bundle = await _bundle(seeded, WED)
    default = day_doc(bundle, Prefs(), today=NOW.date()).classic()
    assert "17-214" not in default and "Черноусова" in default
    with_room = day_doc(bundle, Prefs(show_room=True), today=NOW.date()).classic()
    assert "17-214" in with_room


async def test_every_toggle_is_honoured(seeded: AppContext):
    bundle = await _bundle(seeded, WED)
    bare = Prefs(show_time=False, show_kind=False, show_teacher=False, show_week_number=False, emoji=False)
    text = day_doc(bundle, bare, today=NOW.date()).classic()
    assert "10:25" not in text and "Практика" not in text and "Черноусова" not in text and "тиждень" not in text
    compact = day_doc(bundle, apply_preset(Prefs(), "minimal"), today=NOW.date()).classic()
    assert compact.count("<blockquote>") == 3 and "Черноусова" not in compact


async def test_current_pair_is_marked(seeded: AppContext):
    bundle = await _bundle(seeded, NOW.date())
    text = day_doc(bundle, Prefs(), today=NOW.date(), now=NOW).classic()
    assert "▶️" in text


async def test_week_hides_empty_weekend(seeded: AppContext):
    async with seeded.db.session() as session:
        bundles = await schedule.week(session, NOW.date(), today=NOW.date())
    text = week_doc(bundles, Prefs(), today=NOW.date()).classic()
    assert "Пн, 05.10 👈" in text and "Нд" not in text
    assert "Нд" in week_doc(bundles, Prefs(show_weekends=True), today=NOW.date()).classic()


def test_doc_serialisers():
    doc = Doc().h("Title").p("a", "b").quote("q1", "q2", expandable=True)
    assert doc.classic() == "<b>Title</b>\n\na\nb\n\n<blockquote expandable>q1\nq2</blockquote>"
    assert doc.rich() == "<h1>Title</h1><p>a<br/>b</p><blockquote>q1<br/>q2</blockquote>"


async def test_subject_name_is_a_link(seeded: AppContext):
    bundle = await _bundle(seeded, WED)
    text = day_doc(bundle, Prefs(), today=NOW.date()).classic()
    assert '<a href="https://us04web.zoom.us/j/9026286574' in text  # Черноусова, practice
    assert "Посилання на пару" not in text
    week = week_doc([bundle], Prefs(), today=NOW.date()).classic()
    assert "<a href=" in week

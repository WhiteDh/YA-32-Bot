from datetime import datetime

from tests.conftest import NOW
from ya32_bot.bot.context import AppContext
from ya32_bot.services import export


async def test_ics_has_events_in_utc_and_respects_room_toggle(seeded: AppContext):
    async with seeded.db.session() as session:
        hidden = await export.ics_for_user(session, NOW.date(), "Europe/Kyiv", now=NOW, show_room=False)
        shown = await export.ics_for_user(session, NOW.date(), "Europe/Kyiv", now=NOW, show_room=True)
    assert hidden.startswith("BEGIN:VCALENDAR\r\n") and hidden.endswith("END:VCALENDAR\r\n")
    # Mon 05.10 08:30 Kyiv (UTC+3 in October) → 05:30Z
    assert "DTSTART:20261005T053000Z" in hidden
    assert "LOCATION" not in hidden and "LOCATION:17-214" in shown
    assert all(len(line.encode()) <= 75 for line in hidden.split("\r\n"))


def test_ics_folding_never_splits_cyrillic():
    lines = export._fold("SUMMARY:" + "Інтелектуальний аналіз економічних даних " * 3)
    assert len(lines) > 1 and all(len(x.encode()) <= 75 for x in lines)
    assert "".join(x[1:] if i else x for i, x in enumerate(lines)).startswith("SUMMARY:Інтелектуальний")


async def test_search_finds_next_pairs(seeded: AppContext):
    async with seeded.db.session() as session:
        hits = await export.search(session, "вебскрейп", NOW.date())
        nothing = await export.search(session, "зз", NOW.date())
    assert [h.subject for h in hits] == ["Вебскрейпінг та аналіз соціальних мереж"]
    assert hits[0].upcoming[0].starts_at() == datetime(2026, 10, 9, 8, 30)
    assert nothing == []

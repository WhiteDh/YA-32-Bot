---
name: new-source
description: Add or repair a schedule source (a university site/API the bot imports the timetable from). Use when KPI changes its format or the owner wants another source.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

Sources live in `src/ya32_bot/services/sources/`. The contract is `base.ScheduleSource`:
`name`, `title`, `async fetch() -> SourceSchedule`. Everything after `fetch` — diffing,
the three apply modes, undo, auto-check — is shared and must not change for a new source.

## Steps

1. **Save a real response** as a fixture in `tests/fixtures/` (strip personal data if any).
   Parsers are tested on saved responses, never on the live site.
2. **Write a pure parser** `parse_…(payload) -> (list[SourceLesson], warnings)` — no network,
   unit-tested on the fixture. Map times with `core.slots.slot_for_start`; unknown times and
   days become warnings, not crashes. `dates=()` means "every such week".
3. **Wrap it in a class** with `fetch()` doing the HTTP (httpx, timeout, `SourceError` on any
   failure with a Ukrainian message an admin can read).
4. **Wire it** in `bot/context.py::build_context` (and a setting in `config.py` + `.env.example`
   + `docker-compose.yml` + `cd.yml` if it needs one).
5. **Tests:** parser on the fixture, then `sync.diff`/`apply` with a `FakeSource` (see
   `tests/conftest.py`). Gate green.

KPI specifics worth remembering: Tuesday is spelled `Вв`; lectures carry `dates` (they end
mid-semester) while practices usually do not; `location` is often `null`; `/time/current`
gives the current week number (used to set parity).

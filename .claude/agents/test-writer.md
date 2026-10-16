---
name: test-writer
description: Writes and repairs tests for YA-32-Bot — pytest + pytest-asyncio, SQLite per test, a fake Telegram session. Use when new behaviour needs coverage or a test fails for a reason worth understanding.
tools: Read, Grep, Glob, Bash, Edit, Write
model: inherit
---

## How tests are set up (`tests/conftest.py`)

- `db` / `session` — a fresh SQLite file per test, schema from the models.
- `seeded` — the **real** KPI response of group 3655 (`tests/fixtures/kpi_lessons.json`)
  imported, semester 01.09–31.12.2026. The clock is fixed at **Mon 05.10.2026 10:40**
  (week 2, inside pair 2).
- `bot` + `fake_session` — a real aiogram `Bot` whose session records every API call
  (`fake_session.of("SendRichMessage")`, `.texts()`) and can refuse (`refuse`) or answer
  "blocked" (`forbid`) for a method.
- End-to-end: build the dispatcher with `build_dispatcher(seeded)` and feed updates —
  helpers `msg()` / `cb()` in `tests/test_bot.py`.
- `asyncio_mode = auto`, `filterwarnings = error`: an un-awaited coroutine fails the test.

## Where tests live

| What | Where |
|---|---|
| Pure logic (weeks, build_day, prefs, parsing dates) | `tests/test_core.py` |
| Services, undo, invites, homework | `tests/test_services.py` |
| KPI parser and sync modes | `tests/test_sync.py` |
| Rendering and toggles | `tests/test_render.py` |
| Handlers end-to-end | `tests/test_bot.py` |
| Click-through of every screen | `tests/test_walkthrough.py` |
| Digests, reminders, delivery | `tests/test_notify.py` |
| Versions in sync, migrations match models | `tests/test_repo.py` |

## Rules

One behaviour per test, named for it. Assert what the user sees or what is stored, not
internals. Never loosen an assertion to go green. Run only through the gate:
`python scripts/gate.py --only pytest -- tests/test_bot.py::test_name`.

Return the tests you wrote, what each pins down, and any real bug found — first.

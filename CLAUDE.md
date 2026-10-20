# YA-32-Bot

Telegram-бот расписания одной группы — ЯА-32 (КПИ, groupId 3655). Только личка, тексты бота
українською. Один процесс (long polling) + Postgres в docker compose.

Файл тонкий сознательно. Процесс — `.claude/docs/` (или `/playbook`), устройство кода —
`docs/architecture.md`, деплой — `docs/deploy.md`, что умеет бот — `README.md`.

## Система контроля

Веток и PR нет, работаем в `main`. **По умолчанию всё автоматически, наружу — только по слову.**

- Закончил изменение → гейт, ревью, доки, `CHANGELOG`, чистый локальный коммит (`/finish`).
- Владелец сказал **`push`** → `/push`. Сказал **`release`** / **`deploy`** → `/release`.
- Пока папка не git-репозиторий (репо будет у друга) — коммит пропускается, остальное как обычно.

**Проверки — только `python scripts/gate.py`** (ruff · ruff format · mypy strict · bandit ·
pip-audit · pytest · poetry-lock). Один тест — `--only pytest -- путь::тест`, формат — `--fix`.

**Автор коммитов — человек.** Ни `Co-Authored-By`, ни упоминаний ассистента — нигде. Формат —
одна строка `type(scope): summary`. `guard-git` блокирует нарушение.

**Язык.** Разговор, `CLAUDE.md`, доки, `CHANGELOG.md` — русский. Тексты бота — українська.
Код, комментарии, коммиты — английский.

**Прод.** SSH — действие наружу: спроси перед первым `ssh` в задаче. На сервере руками ничего
не меняем — только через релиз.

**Заметил постороннее** — спроси одной строкой: сейчас или в заметки (`/idea` → `_ideas/`).

## Раскладка

Entry point: `python -m ya32_bot` (`scripts\dev.bat`).

```
src/ya32_bot/
├── app.py            сборка: миграции → Bot/Dispatcher → команды → планировщик → polling
├── config.py         pydantic-settings; version зеркалится из VERSION
├── core/             ЧИСТОЕ ядро: slots, calendar (чётность, семестр), timetable (build_day,
│                     now_status), prefs (все пользовательские настройки), texts_uk
├── db/               models.py (SQLAlchemy 2), session.py (engine + alembic upgrade при старте)
├── services/         schedule, homework, users (роли, инвайты), semester, audit (журнал+undo),
│                     sync (diff/apply append|update|reload), sources/ (kpi.py), kv
├── bot/
│   ├── handlers/     start, schedule, homework, settings, inline, easter, fallback, admin/*
│   ├── render/       doc.py (Doc → Rich HTML | classic HTML), schedule.py, homework.py
│   ├── keyboards/    callbacks.py (CallbackData), common.py (кнопки, календарь, reply-меню)
│   ├── middlewares/  DbSession, User, NavigationReset, Throttle
│   ├── screens.py    экраны = Doc + клавиатура (переиспользуются в уведомлениях и inline)
│   ├── ui.py         send/edit: Rich Message → fallback на HTML
│   ├── notify.py     дайджесты, напоминания, рассылка изменений (debounce), объявления
│   ├── commands.py   меню «/» и описание бота из кода (дефолт + админам по scope)
│   └── easter.py     пасхалки
└── scheduler/        APScheduler: минутный tick, heartbeat, ежедневная проверка КПИ
migrations/  tests/  scripts/  docs/  .claude/
_temp/legacy/          старый бот (telebot) — только для справки, вне git
```

## Правила

- **`core/` чистый**: не импортирует aiogram/SQLAlchemy/httpx и не зовёт `now()` — время аргументом.
- **День вычисляется, не хранится**: шаблон (`template_lessons`, неделя 1/2, `dates` у лекций) +
  `overrides` на дату + каникулы → `core.timetable.build_day`.
- **Каждая правка расписания/ДЗ — через `services/` с журналом** (`audit.Change`), иначе нет undo.
- **HTML — только в `bot/render/` и `bot/screens.py`**; динамика всегда через `esc()`.
- **Отправка экранов — только через `bot/ui.py`** (Rich Message с откатом на HTML).
- **Callback data ≤ 64 байт, без `:` внутри значений** (время передаём как `HHMM`).
- **Настройка пользователя = поле в `core/prefs.Prefs`** (JSON-колонка, миграция не нужна).
  Пользователю доступны только уведомления: `NOTIFY_TOGGLES` + `NOTIFY_FIELDS`; остальное
  `Prefs.load` отбрасывает, вид у всех по умолчанию. Аудитории по умолчанию скрыты.
- **Ссылки на пары — `core/links.py`** (предмет как в КПИ [+ фамилия]); `Subject.link` — запасная.
- **Модель БД изменилась → новая миграция** (`scripts\dev.bat migrate "…"`); тест это ловит.
- **Новый экран → строка в `tests/test_walkthrough.py`** (кликает всё и ищет «😵»).
- **Синхронизация не трогает** overrides, домашку и `subjects`; «Оновити» не трогает строки `source="manual"`.
- **Время — локальное** (`TZ`, `Europe/Kyiv`), naive datetime в `core` — это «стенные часы».
- **Команды бота не настраиваются в @BotFather** — их публикует `bot/commands.py` при старте и при смене роли.

## Команды

```bash
python scripts/gate.py                 # единственный чекер, как CI
python scripts/gate.py --strict        # + покрытие (перед релизом)
python scripts/gate.py --fix           # ruff --fix + format, потом гейт
python scripts/release.py --bump minor --dry-run
```

```bat
scripts\dev.bat              :: бот локально (SQLite из .env)
scripts\dev.bat infra        :: Postgres в Docker на localhost:5432
scripts\dev.bat migrate "…"  :: новая миграция Alembic
scripts\prod.bat health      :: состояние контейнеров на проде (ssh)
```

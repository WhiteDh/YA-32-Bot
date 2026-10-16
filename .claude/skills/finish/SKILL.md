---
name: finish
description: Wrap up a finished change — gate, review, docs, then a clean local commit. Runs on its own when the work for a request is done; never asks permission and never pushes.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write
---

Run this **automatically** when the work for the owner's request is complete. Do not ask
"закоммитить?". Nothing leaves the machine without a word from the owner.

## The steps

1. **`/gate`** — green. Reds are fixed first.

2. **Review, sized to the change.** Trivial edit → a careful self-check. Substantial change →
   the **`code-reviewer`** agent; address blockers and majors.

3. **Migrations.** Touched `src/ya32_bot/db/models.py`? Then a new Alembic revision exists
   (`scripts\dev.bat migrate "what changed"`), and `tests/test_repo.py::test_migrations_match_models`
   is green. Never edit an applied migration — add a new one.

4. **Docs, if behaviour changed.** `CLAUDE.md` (rules, layout), `README.md` (features),
   `docs/` (architecture, deploy), `.claude/docs/` (process). User-visible change → a line in
   `## Unreleased` of `CHANGELOG.md`, in Russian, about what changed for the group.

5. **The "Як перевірити" block** — two to four concrete checks: a command or a button in
   Telegram, a targeted test through the gate, `scripts\prod.bat logs` after a deploy.

6. **Commit — never push.** If the folder is not a git repository yet, say so and stop here.
   One logical change per commit, one line, English, imperative: `type(scope): summary`.
   Types: `feat` `fix` `docs` `refactor` `test` `chore` `perf` `ci`. Scopes: `tg` `admin`
   `sync` `notify` `db` `infra` `deps` `tooling`. **No Co-Authored-By, no mention of the
   assistant or its vendor** — `guard-git` refuses it.

7. **Tell the owner it is committed**, and that `push` sends it to GitHub and `release` deploys.

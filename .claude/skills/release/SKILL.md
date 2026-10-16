---
name: release
description: Deploy YA-32-Bot to the production server — strict gate, CHANGELOG, version bump, tag, confirmation, push. Triggered by the owner saying "release" or "deploy". The model never tags or deploys on its own.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write
---

Pushing a `vX.Y.Z` tag is the only thing that reaches production: CD runs the gate, builds the
image, pushes it to GHCR, **dumps the database** (`/srv/ya32-bot/backups`, last 10 kept) and
runs `docker compose -p ya32 up -d`. Migrations apply themselves when the bot starts.

Trigger: the owner says **release** or **deploy**.

## The steps

1. **Agree the scope.** `git log $(git describe --tags --abbrev=0)..HEAD --oneline` and the bump:
   `patch` (fixes), `minor` (features), `major` (breaking). Propose; the owner decides.
2. **`## Unreleased` in `CHANGELOG.md`** filled — Russian, what changed for the group.
   Commit it (`docs(changelog): ...`). `release.py` refuses an empty section.
3. **Strict gate:** `python scripts/gate.py --strict`. Red → stop.
4. **Migrations that drop or rewrite data?** Say so plainly and get an explicit go: the
   pre-deploy dump is the only way back.
5. **Preview:** `python scripts/release.py --bump <kind> --dry-run`.
6. **Prepare:** `python scripts/release.py --bump <kind>` — VERSION and its mirrors
   (`pyproject.toml`, `config.py`, `__init__.py`), CHANGELOG stamp, commit, local tag, approvals.
7. **Final go** from the owner: the bot is offline for a few seconds.
8. **Ship:** `git push origin main`, then `git push origin vX.Y.Z`.
9. **Watch it land:** `gh run list --limit 3`; when CD is green — `scripts\prod.bat health`
   (fresh `started=` and `health=healthy`), `scripts\prod.bat logs ya32-bot 10m`
   (`ya32-bot X.Y.Z started as @…`).

Roll forward, not back: fix, `--bump patch`, release again. If a migration broke data, restore
the latest dump from `/srv/ya32-bot/backups` — with the owner, by hand, never on your own.

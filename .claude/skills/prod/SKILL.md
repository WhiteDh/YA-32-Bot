---
name: prod
description: Check the production server — container health, logs, backups. Use after a deploy, or when something looks wrong in production.
user-invocable: true
allowed-tools: Bash, Read
---

Production: compose project `ya32` in `/srv/ya32-bot` — containers `ya32-bot` and `ya32-db`
(Postgres 17-alpine, volume `ya32_ya32-db-data`). The bot uses long polling: no port, no
public URL. Use `scripts\prod.bat` instead of long `ssh` lines.

**SSH is an outward action — ask before the first connection in a task.**

```bat
scripts\prod.bat health                 :: status, healthcheck, start time, image tag
scripts\prod.bat ps
scripts\prod.bat logs                   :: bot, last 24h
scripts\prod.bat logs ya32-db 2h
scripts\prod.bat backups                :: pre-deploy dumps on the server
scripts\prod.bat backup                 :: fresh dump into backups\ here
```

## Reading the answer

- `health=unhealthy` → the scheduler stopped touching the heartbeat (event loop stuck or the
  process half-dead). Logs first, then a restart only with the owner's go.
- `Telegram rejected BOT_TOKEN` → the token is wrong or was revoked; the right one goes into the `BOT_TOKEN`
  secret and a re-run of CD.
- `rich message refused, switching to classic HTML` → the Bot API server refused a Rich
  Message; the bot keeps working in classic HTML. Note it via `/idea`, not an incident.
- `kpi auto-check failed` → api.campus.kpi.ua was down or changed format; admins can still
  edit by hand. Check `services/sources/kpi.py` against a fresh response.

## Never

Do not edit files on the server, restart containers or write to the database unless the owner
asked for exactly that in this conversation. Never print a container's environment
(`docker inspect` without `--format`, `docker exec … env`) — `guard-secrets` refuses it.

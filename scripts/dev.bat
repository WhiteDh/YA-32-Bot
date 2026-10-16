@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
rem dev.bat - run a piece of YA-32-Bot locally, without remembering the command.
rem
rem   dev                the bot (long polling, settings from .env; SQLite by default)
rem   dev infra          Postgres in Docker on localhost:5432 (data survives in a volume)
rem   dev stop           stop it
rem   dev psql           psql shell inside the local database
rem   dev gate [flags]   the quality gate (the same one CI runs)
rem   dev migrate "msg"  autogenerate an Alembic migration after changing db/models.py
rem   dev docker         build the image and run the whole stack locally
rem   dev install        poetry install

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "CMD=%~1"
if "!CMD!"=="" set "CMD=bot"
set "COMPOSE=docker compose -p ya32-dev -f "%ROOT%\docker-compose.yml" -f "%ROOT%\docker-compose.override.yml""

if /i "!CMD!"=="help" (
    echo dev                - the bot
    echo dev infra^|stop     - Postgres in Docker
    echo dev psql           - psql into the local database
    echo dev gate [flags]   - the quality gate
    echo dev migrate "msg"  - new Alembic migration
    echo dev docker         - whole stack in Docker
    echo dev install        - poetry install
    goto :end
)

if /i "!CMD!"=="bot" (
    pushd "%ROOT%" && poetry run python -m ya32_bot & popd
    goto :end
)
if /i "!CMD!"=="infra" (
    call :override
    set "BOT_TOKEN=unused" & set "OWNER_IDS=0"
    !COMPOSE! up -d ya32-db
    echo [dev] DATABASE_URL=postgresql+asyncpg://ya32:ya32@localhost:5432/ya32
    goto :end
)
if /i "!CMD!"=="stop" (
    call :override
    set "BOT_TOKEN=x" & set "OWNER_IDS=0"
    !COMPOSE! stop
    goto :end
)
if /i "!CMD!"=="psql" (
    docker exec -it ya32-db psql -U ya32 ya32
    goto :end
)
if /i "!CMD!"=="gate" (
    python "%ROOT%\scripts\gate.py" %2 %3 %4 %5 %6
    goto :end
)
if /i "!CMD!"=="migrate" (
    if "%~2"=="" ( echo Usage: dev migrate "what changed" & goto :end )
    pushd "%ROOT%" && poetry run alembic revision --autogenerate -m "%~2" & popd
    goto :end
)
if /i "!CMD!"=="docker" (
    call :override
    pushd "%ROOT%" && !COMPOSE! --env-file .env up -d --build & popd
    goto :end
)
if /i "!CMD!"=="install" (
    pushd "%ROOT%" && poetry install & popd
    goto :end
)

echo Unknown command: !CMD!.  Try: dev help
goto :end

:override
if not exist "%ROOT%\docker-compose.override.yml" (
    copy "%ROOT%\docker-compose.override.yml.example" "%ROOT%\docker-compose.override.yml" >nul
    echo [dev] created docker-compose.override.yml from the example
)
exit /b 0

:end
endlocal

@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
rem prod.bat - the production server, without long ssh lines.
rem
rem Target: set PROD_USER and PROD_HOST once as user environment variables
rem (the same values as the SERVER_USER / SERVER_HOST secrets in GitHub).
rem SSHing in is an outward action - confirm with the owner first.
rem
rem   prod                    interactive shell on the server
rem   prod health             container state + healthcheck of the bot
rem   prod ps                 the stack's containers and their uptime
rem   prod logs [c] [since]   docker logs with timestamps (bot, 24h by default)
rem   prod backup             pg_dump to backups\ on this machine
rem   prod backups            list the pre-deploy dumps on the server
rem   prod restart <c>        restart one container  (touches prod - ask first)
rem   prod <anything...>      run the rest as a raw command on the server
rem
rem Containers: ya32-bot, ya32-db. Compose: /srv/ya32-bot (project "ya32").

set "TARGET=%PROD_USER%@%PROD_HOST%"
set "CMD=%~1"
for %%I in ("%~dp0..") do set "ROOT=%%~fI"

if "%PROD_HOST%"=="" goto :noserver
if "%PROD_USER%"=="" goto :noserver
goto :dispatch

:noserver
if /i "%~1"=="help" goto :dispatch
echo Не задан адрес сервера. Один раз:
echo     setx PROD_USER ^<user^>
echo     setx PROD_HOST ^<host^>
echo и открой терминал заново.
goto :end

:dispatch
if "!CMD!"=="" (
    ssh !TARGET!
    goto :end
)
if /i "!CMD!"=="help" (
    echo prod                    - shell on the server
    echo prod health             - bot container state and healthcheck
    echo prod ps                 - containers and uptime
    echo prod logs [c] [since]   - docker logs ^(bot, 24h by default^)
    echo prod backup             - pg_dump into backups\ here
    echo prod backups            - pre-deploy dumps on the server
    echo prod restart ^<c^>        - restart one container
    goto :end
)
if /i "!CMD!"=="health" (
    ssh !TARGET! "docker inspect --format '{{.Name}}  {{.State.Status}}  health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}  started={{.State.StartedAt}}  image={{.Config.Image}}' ya32-bot ya32-db"
    goto :end
)
if /i "!CMD!"=="ps" (
    ssh !TARGET! "docker ps -a --filter name=ya32 --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'"
    goto :end
)
if /i "!CMD!"=="logs" (
    set "CONTAINER=%~2"
    if "!CONTAINER!"=="" set "CONTAINER=ya32-bot"
    set "SINCE=%~3"
    if "!SINCE!"=="" set "SINCE=24h"
    ssh !TARGET! "docker logs !CONTAINER! --since !SINCE! --timestamps"
    goto :end
)
if /i "!CMD!"=="backup" (
    if not exist "%ROOT%\backups" mkdir "%ROOT%\backups"
    for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%T"
    ssh !TARGET! "docker exec ya32-db pg_dump -U ya32 ya32 | gzip" > "%ROOT%\backups\ya32-!STAMP!.sql.gz"
    echo [prod] backups\ya32-!STAMP!.sql.gz
    goto :end
)
if /i "!CMD!"=="backups" (
    ssh !TARGET! "ls -lh /srv/ya32-bot/backups 2>/dev/null || echo 'no backups yet'"
    goto :end
)
if /i "!CMD!"=="restart" (
    if "%~2"=="" ( echo Usage: prod restart ^<container^> & goto :end )
    ssh !TARGET! "docker restart %~2"
    goto :end
)

ssh !TARGET! %*

:end
endlocal

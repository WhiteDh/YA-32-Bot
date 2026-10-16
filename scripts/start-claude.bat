@echo off
REM Open Claude Code at the YA-32-Bot root, so CLAUDE.md and .claude/ are in scope from the first message.
REM Inside Windows Terminal Shift+Enter gives a real newline; falls back to plain PowerShell.

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

where wt.exe >nul 2>nul
if errorlevel 1 goto fallback

wt.exe -d "%ROOT%" --title YA-32-Bot powershell -NoLogo -NoExit -ExecutionPolicy Bypass -Command claude
goto :eof

:fallback
start "YA-32-Bot — Claude Code" powershell -NoLogo -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; claude"

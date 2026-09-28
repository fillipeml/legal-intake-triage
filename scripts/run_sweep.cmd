@echo off
rem Runs one intake command (sweep | sync-board), called by the Task Scheduler. Log in logs\intake.log.

cd /d "%~dp0.."
if not exist logs mkdir logs
echo. >> logs\intake.log
echo ===== %date% %time% %1 ===== >> logs\intake.log
uv run intake %1 >> logs\intake.log 2>&1

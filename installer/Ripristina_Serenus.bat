@echo off
setlocal
set "L=%LOCALAPPDATA%\Serenus\launcher"
cd /d "%L%"
"%L%\.venv\Scripts\python.exe" -m updater.cli rollback
pause

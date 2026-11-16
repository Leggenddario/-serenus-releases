@echo off
setlocal
set "L=%LOCALAPPDATA%\Serenus\launcher"
if not exist "%L%\.venv\Scripts\python.exe" (
 echo Serenus incompleto. Riapri Serenus_Setup.exe.
 pause
 exit /b 1
)
cd /d "%L%"
"%L%\.venv\Scripts\python.exe" -m updater.launcher
if errorlevel 1 pause

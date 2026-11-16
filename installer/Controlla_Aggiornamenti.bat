@echo off
setlocal
set "L=%LOCALAPPDATA%\Serenus\launcher"
cd /d "%L%"
"%L%\.venv\Scripts\python.exe" -m updater.cli check --repo "Leggenddario/-serenus-releases" --public-key "%L%\release-public-key.txt"
if errorlevel 1 (pause & exit /b 1)
choice /M "Vuoi installare la nuova versione? Chiudi prima Serenus"
if errorlevel 2 exit /b 0
"%L%\.venv\Scripts\python.exe" -m updater.cli apply --repo "Leggenddario/-serenus-releases" --public-key "%L%\release-public-key.txt"
pause

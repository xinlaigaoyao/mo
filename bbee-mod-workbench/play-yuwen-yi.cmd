@echo off
setlocal
cd /d "%~dp0"
set "TEMP=%~dp0private\temp\play"
set "TMP=%~dp0private\temp\play"
if not exist "%TEMP%" mkdir "%TEMP%"
"%~dp0ZenithTerminal\Interpreter\pythoncore-3.14-64\python.exe" -B -E -s -X utf8 "%~dp0scripts\play_launcher.py" play
if errorlevel 1 (
  echo Normal play stopped. Recovery backups were retained; saves were not restored.
  pause
)
endlocal

@echo off
rem Starts The Zenith Terminal's window with the Python in this folder. The same thing ZenithTerminal.exe does.
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
if not exist "Interpreter\pythoncore-3.14-64\pythonw.exe" (
    echo The Interpreter folder is missing. Open the ZenithTerminal file you downloaded again: it puts back what is missing.
    pause
    exit /b 1
)
start "" "Interpreter\pythoncore-3.14-64\pythonw.exe" "Gui\run_gui.py" %*

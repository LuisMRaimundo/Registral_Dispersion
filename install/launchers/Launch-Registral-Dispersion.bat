@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Virtual environment not found.
    echo Run install\windows\INSTALL.bat once to set up this folder.
    echo.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m registral_dispersion
if errorlevel 1 pause

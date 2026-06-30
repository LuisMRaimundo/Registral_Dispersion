@echo off
setlocal EnableExtensions
title Registral_Dispersion - Installer
cd /d "%~dp0\..\.." || (
  echo ERROR: Cannot find project root.
  pause
  exit /b 1
)

echo.
echo  *** USE THIS FILE FOR NORMAL INSTALL ***
echo.
echo  ============================================================
echo   Registral_Dispersion - One-click installer (Windows)
echo  ============================================================
echo.
echo  GitHub: https://github.com/LuisMRaimundo/register-dispersion-analysis
echo.
echo  This installs the registral dispersion tool and launcher scripts.
echo  Do not close this window until finished.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Easy.ps1"
set ERR=%ERRORLEVEL%

echo.
if %ERR% NEQ 0 (
  echo Installation failed. See install.log in the project folder.
) else (
  echo Done.
)
echo.
pause
exit /b %ERR%

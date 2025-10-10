@echo off
REM =====================================================
REM  VN TOOLCHAIN - REN'PY LAUNCHER
REM =====================================================

SETLOCAL
SET RENPY_DIR=%~dp0data\renpy_project
SET RENPY_EXE=%~dp0renpy\renpy.exe

echo Launching VN Toolchain Ren'Py project...

REM 1️⃣  Check if a local Ren'Py SDK is present
IF EXIST "%RENPY_EXE%" (
    echo Found local Ren'Py SDK.
    "%RENPY_EXE%" "%RENPY_DIR%"
    GOTO :EOF
)

REM 2️⃣  Try system-installed Ren'Py
WHERE renpy >nul 2>&1
IF %ERRORLEVEL%==0 (
    echo Using system Ren'Py...
    renpy "%RENPY_DIR%"
    GOTO :EOF
)

REM 3️⃣  Fallback - Prompt user
echo -----------------------------------------------------
echo Ren'Py SDK not found.
echo Please download from: https://www.renpy.org/latest.html
echo Once downloaded, extract it beside this folder as /renpy
echo and re-run this launcher.
echo -----------------------------------------------------
pause
ENDLOCAL

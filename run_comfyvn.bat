@echo off
setlocal ENABLEDELAYEDEXPANSION

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=."
pushd "%SCRIPT_DIR%" >nul 2>&1

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ComfyVN] Python 3 interpreter not found on PATH.
    echo [ComfyVN] Install Python 3.10+ and ensure it is available as^: py -3 or python.
    popd >nul 2>&1
    exit /b 9009
)

echo [ComfyVN] Launching using %PYTHON_CMD% …
call %PYTHON_CMD% "%SCRIPT_DIR%run_comfyvn.py" %*

set "EXIT_CODE=%ERRORLEVEL%"
popd >nul 2>&1
exit /b %EXIT_CODE%

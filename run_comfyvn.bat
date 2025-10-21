@echo off
setlocal ENABLEDELAYEDEXPANSION
set "DEBUG_ENABLED=0"
if /I "%COMFYVN_DEBUG%"=="1" set "DEBUG_ENABLED=1"
if not "%~1"=="" (
    for %%I in (%*) do (
        if /I "%%~I"=="--install-defaults" set "INSTALL_DEFAULTS=1"
        if /I "%%~I"=="--debug" set "DEBUG_ENABLED=1"
    )
)

if "!DEBUG_ENABLED!"=="1" (
    echo [ComfyVN][DEBUG] Script directory resolved to "%SCRIPT_DIR%"
    echo [ComfyVN][DEBUG] Arguments: %*
)

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=."
pushd "%SCRIPT_DIR%" >nul 2>&1

set "INSTALL_DEFAULTS=0"


set "PYTHON_CMD="
py -3 --version >nul 2>&1
if !ERRORLEVEL!==0 (
    if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] Found Python via "py -3".
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>&1
    if !ERRORLEVEL!==0 (
        if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] Found Python via "python".
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ComfyVN] Python 3 interpreter not found on PATH.
    echo [ComfyVN] Install Python 3.10+ and ensure it is available as^: py -3 or python.
    popd >nul 2>&1
    exit /b 9009
)

rem -- Attempt auto-update when git is available and the working tree is clean.
if exist ".git" (
    where git >nul 2>&1
    if !ERRORLEVEL!==0 (
        if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] Git detected; checking repo cleanliness.
        git status --porcelain ^| findstr "." >nul
        if !ERRORLEVEL!==0 (
            echo [ComfyVN] Skipping auto-update (local changes detected).
            if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] git status detected local changes.
        ) else (
            echo [ComfyVN] Checking for updates ...
            git pull --ff-only
            if !ERRORLEVEL! NEQ 0 (
                echo [ComfyVN] Auto-update failed (git pull). Continuing with existing files.
            ) else (
                if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] Auto-update completed successfully.
            )
        )
    ) else (
        if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] Git not available on PATH; skipping auto-update.
    )
)
if "!DEBUG_ENABLED!"=="1" (
    if not exist ".git" echo [ComfyVN][DEBUG] Not a git checkout; skipping auto-update.
    if defined PYTHON_CMD echo [ComfyVN][DEBUG] Using interpreter: %PYTHON_CMD%.
)

if "%INSTALL_DEFAULTS%"=="1" (
    echo [ComfyVN] Launching defaults installer using %PYTHON_CMD% …
) else (
    echo [ComfyVN] Launching using %PYTHON_CMD% …
)
call %PYTHON_CMD% "%SCRIPT_DIR%run_comfyvn.py" %*

set "EXIT_CODE=!ERRORLEVEL!"

if "!DEBUG_ENABLED!"=="1" echo [ComfyVN][DEBUG] run_comfyvn.py exited with code !EXIT_CODE!.

if %EXIT_CODE% NEQ 0 (
    if "%INSTALL_DEFAULTS%"=="1" (
        echo [ComfyVN] Defaults installer exited with error level %EXIT_CODE%.
    ) else (
        echo [ComfyVN] Launcher exited with error level %EXIT_CODE%.
    )
    echo [ComfyVN] Check logs\launcher.log for additional details.
    echo [ComfyVN] Press any key to close this window.
    pause >nul
)

popd >nul 2>&1
exit /b %EXIT_CODE%

@echo off
setlocal ENABLEDELAYEDEXPANSION

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=."
pushd "%SCRIPT_DIR%" >nul 2>&1

set "INSTALL_DEFAULTS=0"
for %%I in (%*) do (
    if /I "%%~I"=="--install-defaults" set "INSTALL_DEFAULTS=1"
)

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

rem -- Attempt auto-update when git is available and the working tree is clean.
if exist ".git" (
    where git >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "GIT_DIRTY="
        for /f "delims=" %%S in ('git status --porcelain') do (
            set "GIT_DIRTY=1"
            goto :after_status
        )
:after_status
        if defined GIT_DIRTY (
            echo [ComfyVN] Skipping auto-update (local changes detected).
        ) else (
            echo [ComfyVN] Checking for updates ...
            git pull --ff-only
            if %ERRORLEVEL% NEQ 0 (
                echo [ComfyVN] Auto-update failed (git pull). Continuing with existing files.
            )
        )
    )
)

if "%INSTALL_DEFAULTS%"=="1" (
    echo [ComfyVN] Launching defaults installer using %PYTHON_CMD% …
) else (
    echo [ComfyVN] Launching using %PYTHON_CMD% …
)
call %PYTHON_CMD% "%SCRIPT_DIR%run_comfyvn.py" %*

set "EXIT_CODE=%ERRORLEVEL%"

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

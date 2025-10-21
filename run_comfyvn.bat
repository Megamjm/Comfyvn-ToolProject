@echo off
setlocal ENABLEDELAYEDEXPANSION
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=%CD%\"
set "INSTALL_DEFAULTS=0"
if not "%~1"=="" (
    for %%I in (%*) do (
        if /I "%%~I"=="--install-defaults" set "INSTALL_DEFAULTS=1"
    )
)

echo [ComfyVN] Script directory resolved to "%SCRIPT_DIR%"
echo [ComfyVN] Arguments: %*

pushd "%SCRIPT_DIR%" >nul 2>&1

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if !ERRORLEVEL!==0 (
    echo [ComfyVN] Found Python via "py -3".
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>&1
    if !ERRORLEVEL!==0 (
        echo [ComfyVN] Found Python via "python".
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ComfyVN] Python 3 interpreter not found on PATH.
    echo [ComfyVN] Install Python 3.10+ and ensure it is available as^: py -3 or python.
    popd >nul 2>&1
    exit /b 9009
)

rem -- Auto-update temporarily disabled to avoid script parsing issues.
echo [ComfyVN] Auto-update step skipped.
if defined PYTHON_CMD echo [ComfyVN] Using interpreter: %PYTHON_CMD%.

if "%INSTALL_DEFAULTS%"=="1" (
    echo [ComfyVN] Launching defaults installer using %PYTHON_CMD% ...
) else (
    echo [ComfyVN] Launching using %PYTHON_CMD% ...
)
call %PYTHON_CMD% "%SCRIPT_DIR%run_comfyvn.py" %*

set "EXIT_CODE=!ERRORLEVEL!"

echo [ComfyVN] run_comfyvn.py exited with code !EXIT_CODE!.

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

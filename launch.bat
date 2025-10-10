@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt

REM Optional auth
REM set VN_AUTH=1
REM set VN_PASSWORD=change_me

REM Optional data location
if "%VN_DATA_DIR%"=="" set VN_DATA_DIR=.\data

if not exist "%VN_DATA_DIR%" mkdir "%VN_DATA_DIR%"
if not exist "%VN_DATA_DIR%\assets" mkdir "%VN_DATA_DIR%\assets"

set FLASK_ENV=production
set PORT=5000

python server\app.py

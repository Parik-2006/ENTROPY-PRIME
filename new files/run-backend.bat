@echo off
title ENTROPY PRIME - Backend :8000
cd /d "%~dp0"

echo ================================================
echo    BACKEND - FastAPI on http://localhost:8000
echo    API Docs: http://localhost:8000/docs
echo    Press CTRL+C to stop
echo ================================================
echo.

REM ── Load secrets from .env.local (never committed to git) ────
set ENV_FILE=%~dp0.env.local

if not exist "%ENV_FILE%" (
    echo  ERROR: .env.local not found.
    echo  Copy .env.example to .env.local and fill in your local secrets:
    echo    copy .env.example .env.local
    echo.
    echo  DO NOT hardcode secrets in this file.
    pause
    exit /b 1
)

REM Parse .env.local — skip blank lines and comments
for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    set "line=%%A"
    if not "!line:~0,1!"=="#" (
        if not "%%A"=="" (
            set "%%A=%%B"
        )
    )
)

REM ── Verify required secrets are set ─────────────────────────
if "%EP_SESSION_SECRET%"=="" (
    echo  ERROR: EP_SESSION_SECRET not set in .env.local
    pause & exit /b 1
)
if "%EP_API_KEY_SECRET%"=="" (
    echo  ERROR: EP_API_KEY_SECRET not set in .env.local
    pause & exit /b 1
)
if "%MONGODB_URL%"=="" (
    echo  ERROR: MONGODB_URL not set in .env.local
    pause & exit /b 1
)

REM ── Activate venv ────────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo  ERROR: Python venv not found in backend\venv
    echo  Please run: cd backend ^& python -m venv venv ^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo  Environment loaded from .env.local
echo  Starting uvicorn...
echo.

REM Run from repo root so 'backend.main:app' import path works
python -m uvicorn backend.main:app --host %HOST% --port %PORT% --reload

pause

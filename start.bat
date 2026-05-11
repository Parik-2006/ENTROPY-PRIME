@echo off
cd /d "%~dp0"
title ENTROPY PRIME - Launcher

echo ================================================
echo    ENTROPY PRIME - Zero Trust Auth System
echo    Development Mode
echo ================================================
echo.

REM ── Stop any stale dev containers first ──────────────────────
echo [1/4] Cleaning up old dev containers...
docker-compose -f docker-compose.dev.yml down --remove-orphans >nul 2>&1

REM ── Start MongoDB + Redis via Docker ─────────────────────────
echo [2/4] Starting MongoDB ^& Redis (Docker)...
docker-compose -f docker-compose.dev.yml up -d
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Docker failed to start!
    echo  Is Docker Desktop running? Please open it and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo  Waiting 15s for MongoDB and Redis to be ready...
ping 127.0.0.1 -n 16 > nul

REM ── Start Backend in its own window ──────────────────────────
echo [3/4] Opening Backend terminal window...
start "ENTROPY PRIME - Backend :8000" cmd /k "%~dp0backend\run-backend.bat"

echo  Waiting 8s for backend to start...
ping 127.0.0.1 -n 9 > nul

REM ── Start Frontend in its own window ─────────────────────────
echo [4/4] Opening Frontend terminal window...
start "ENTROPY PRIME - Frontend :3000" cmd /k "%~dp0run-frontend.bat"

echo.
echo ================================================
echo    STARTUP COMPLETE
echo ================================================
echo.
echo   Infrastructure (Docker, hidden):
echo     MongoDB  ^>  localhost:27017
echo     Redis    ^>  localhost:6379
echo.
echo   Open these in your browser:
echo     Frontend   -^>  http://localhost:3000
echo     Backend    -^>  http://localhost:8000
echo     API Docs   -^>  http://localhost:8000/docs
echo.
echo   You should now see 2 new terminal windows:
echo     [ENTROPY PRIME - Backend :8000]
echo     [ENTROPY PRIME - Frontend :3000]
echo.
echo   To STOP everything, run: stop.bat
echo.
pause
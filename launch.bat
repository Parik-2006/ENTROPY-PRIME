@echo off
setlocal enabledelayedexpansion
title Entropy Prime Launcher
color 0B

echo.
echo  =========================================
echo   ENTROPY PRIME - Zero Trust Auth Engine
echo   Multi-Agent Behavioral Biometrics
echo  =========================================
echo.

REM Check for required tools
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Python not found in PATH
    echo  Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

where npm >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  WARNING: npm not found - frontend may not start
)

REM Check for virtual environment
if not exist "backend\venv" (
    echo  Creating Python virtual environment...
    cd backend
    python -m venv venv
    call venv\Scripts\activate.bat
    echo  Installing backend dependencies...
    pip install -r requirements.txt --quiet
    cd ..
)

REM ── Start Backend ─────────────────────────────────────────────────────────────
echo  [1/2] Starting Backend on port 8000...
start "EP Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && python -m uvicorn main:app --port 8000 --reload"

REM ── Start Frontend ────────────────────────────────────────────────────────────
echo  [2/2] Starting Frontend on port 3000...
start "EP Frontend" cmd /k "cd /d %~dp0 && npm run dev"

REM ── Wait for backend ──────────────────────────────────────────────────────────
echo.
echo  Waiting for backend to be ready (up to 60 seconds)...
set "BACKEND_READY=0"
for /L %%i in (1,1,60) do (
    if !BACKEND_READY! equ 0 (
        curl -s http://localhost:8000/health >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo  ✓ Backend is UP
            set "BACKEND_READY=1"
        ) else (
            if %%i equ 30 echo  (Still waiting... this is normal on first start)
            timeout /t 1 /nobreak >nul
        )
    )
)

if !BACKEND_READY! equ 0 (
    echo  WARNING: Backend didn't respond in 60 seconds
    echo  Check logs with: docker-compose logs backend -f
)

REM ── Wait for frontend ─────────────────────────────────────────────────────────
echo  Waiting for frontend to be ready (up to 60 seconds)...
set "FRONTEND_READY=0"
for /L %%i in (1,1,60) do (
    if !FRONTEND_READY! equ 0 (
        curl -s http://localhost:3000 >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo  ✓ Frontend is UP
            set "FRONTEND_READY=1"
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)

REM ── Open browser ──────────────────────────────────────────────────────────────
echo.
echo  =========================================
if !BACKEND_READY! equ 1 (
    echo   Both services ready!
    echo   Opening http://localhost:3000
    echo  =========================================
    echo.
    start http://localhost:3000
) else (
    echo   Services are starting...
    echo   Frontend: http://localhost:3000
    echo   Backend:  http://localhost:8000
    echo   API Docs: http://localhost:8000/docs
    echo  =========================================
    echo.
)

echo  Press any key to close this launcher window.
echo  (Backend and Frontend keep running in their own windows)
pause >nul

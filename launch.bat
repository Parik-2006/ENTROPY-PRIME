@echo off
title Entropy Prime Launcher
color 0B

echo.
echo  =========================================
echo   ENTROPY PRIME - Zero Trust Auth Engine
echo  =========================================
echo.

:: ── Start Backend ─────────────────────────────────────────────────────────────
echo  [1/2] Starting Backend on port 8000...
start "EP Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && python -m uvicorn main:app --port 8000 --reload"

:: ── Start Frontend ────────────────────────────────────────────────────────────
echo  [2/2] Starting Frontend on port 3000...
start "EP Frontend" cmd /k "cd /d %~dp0 && npm run dev"

:: ── Wait for backend ──────────────────────────────────────────────────────────
echo.
echo  Waiting for backend to be ready...
:wait_backend
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo  Backend not ready yet, retrying...
    goto wait_backend
)
echo  Backend is UP.

:: ── Wait for frontend ─────────────────────────────────────────────────────────
echo  Waiting for frontend to be ready...
:wait_frontend
timeout /t 2 /nobreak >nul
curl -s http://localhost:3000 >nul 2>&1
if errorlevel 1 (
    echo  Frontend not ready yet, retrying...
    goto wait_frontend
)
echo  Frontend is UP.

:: ── Open browser ──────────────────────────────────────────────────────────────
echo.
echo  =========================================
echo   Both services ready!
echo   Opening http://localhost:3000
echo  =========================================
echo.
start http://localhost:3000

echo  Press any key to close this launcher window.
echo  (Backend and Frontend keep running in their own windows)
pause >nul

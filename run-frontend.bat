@echo off
title ENTROPY PRIME - Frontend :3000
cd /d "%~dp0"

echo ================================================
echo    FRONTEND - Vite on http://localhost:3000
echo    API Proxy  -> http://localhost:8000
echo    Press CTRL+C to stop
echo ================================================
echo.

set VITE_API_URL=http://localhost:8000

npm run dev
pause

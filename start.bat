@echo off
echo ================================================
echo    ENTROPY PRIME - Zero Trust Auth System
echo ================================================
echo.

REM Check if already running
tasklist /FI "IMAGENAME eq node.exe" 2>NUL | find /I /N "node.exe">NUL
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Node.js processes already running. They will be terminated.
    taskkill /F /IM node.exe >nul 2>&1
)

tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Python processes already running. They will be terminated.
    taskkill /F /IM python.exe >nul 2>&1
)

tasklist /FI "IMAGENAME eq uvicorn.exe" 2>NUL | find /I /N "uvicorn.exe">NUL
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Uvicorn processes already running. They will be terminated.
    taskkill /F /IM uvicorn.exe >nul 2>&1
)

echo Starting MongoDB...
start "MongoDB" docker-compose up -d

echo Waiting for MongoDB to initialize...
timeout /t 8 /nobreak > nul

echo Starting Backend Server...
start "Entropy Prime Backend" cmd /k "cd backend && call .\venv\Scripts\activate.bat && set MONGODB_URL=mongodb://admin:changeme@localhost:27017/entropy_prime?authSource=admin && echo Backend starting... && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo Waiting for backend to start...
timeout /t 5 /nobreak > nul

echo Starting Frontend...
start "Entropy Prime Frontend" cmd /k "echo Frontend starting... && npm run dev"

echo.
echo ================================================
echo    ENTROPY PRIME STARTUP COMPLETE
echo ================================================
echo.
echo 🌐 Frontend: http://localhost:3001
echo 🔧 Backend API: http://localhost:8000
echo 📚 API Docs: http://localhost:8000/docs
echo 🗄️  MongoDB: localhost:27017
echo.
echo Close this window to stop all servers.
echo Individual server windows will stay open.
echo.
pause
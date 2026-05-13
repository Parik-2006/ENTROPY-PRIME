@echo off
title ENTROPY PRIME - Backend :8000
cd /d "%~dp0"

REM Optional local overrides. These files are ignored by git and can be
REM created on a developer machine without affecting the repo.
if exist "%~dp0.env.local" call :load_env "%~dp0.env.local"
if exist "%~dp0..\.env.local" call :load_env "%~dp0..\.env.local"

echo ================================================
echo    BACKEND - FastAPI on http://localhost:8000
echo    API Docs: http://localhost:8000/docs
echo    Press CTRL+C to stop
echo ================================================
echo.

REM Set environment variables for local dev
set MONGODB_URL=mongodb://mongo_user:viratkohli18@localhost:27017/entropy?authSource=admin
set MONGODB_DB_NAME=entropy
set REDIS_URI=redis://:c60ec64710c3e74ec8ed7fc1f0f6682f997ac952dc52c7f2@localhost:6379/0
set REDIS_URL=redis://:c60ec64710c3e74ec8ed7fc1f0f6682f997ac952dc52c7f2@localhost:6379/0
set EP_SESSION_SECRET=411eac7fce759bcf7d8c3229b079dc550ce128ae6ee3d2f6fb5415bc457a8993
set EP_API_KEY_SECRET=411eac7fce759bcf7d8c3229b079dc550ce128ae6ee3d2f6fb5415bc457a8993
set EP_SHADOW_SECRET=f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1
set EP_JWT_PUBLIC_KEY_PATH=%~dp0certs\jwt_public.pem
set JWT_SECRET=411eac7fce759bcf7d8c3229b079dc550ce128ae6ee3d2f6fb5415bc457a8993
set CORS_ORIGINS=*
set HOST=0.0.0.0
set PORT=8000
set DEBUG=true
set ENVIRONMENT=development

REM Activate venv
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo  ERROR: Python venv not found in backend\venv
    echo  Please run: cd backend ^& python -m venv venv ^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo  Starting uvicorn...
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause

:load_env
for /f "usebackq tokens=1* delims== eol=#" %%A in ("%~1") do (
    if not "%%A"=="" set "%%A=%%B"
)
goto :eof

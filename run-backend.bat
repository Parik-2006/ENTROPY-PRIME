@REM run-backend.bat — Start FastAPI backend with secrets from .env.local
@REM
@REM Usage:
@REM   run-backend.bat
@REM
@REM This batch file:
@REM   1. Checks for .env.local (must exist; contains secrets)
@REM   2. Activates virtual environment
@REM   3. Exports env vars from .env.local
@REM   4. Starts FastAPI development server on localhost:8000

@setlocal enabledelayedexpansion

REM Check for .env.local
if not exist ".env.local" (
    echo.
    echo ERROR: .env.local not found
    echo.
    echo Create .env.local by copying .env.local.template and filling in real values:
    echo   copy .env.local.template .env.local
    echo   (edit .env.local with real secrets)
    echo.
    exit /b 1
)

REM Check for virtual environment
if not exist ".venv-1\Scripts\activate.bat" (
    echo.
    echo ERROR: Virtual environment not found at .venv-1
    echo.
    echo Create it with:
    echo   python -m venv .venv-1
    echo   .venv-1\Scripts\pip install -r backend\requirements.txt
    echo.
    exit /b 1
)

REM Activate virtual environment
call .venv-1\Scripts\activate.bat

REM Load .env.local into environment (simple parsing)
for /f "tokens=1,2 delims==" %%A in (.env.local) do (
    set "%%A=%%B"
)

REM Set Python path
set PYTHONPATH=%CD%\backend;%PYTHONPATH%

REM Start backend
echo.
echo Starting Entropy Prime Backend v4.0.1
echo Port: 8000
echo Secrets: loaded from .env.local
echo.
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

@echo off
TITLE AttendAI -- VIT Attendance System Launcher
COLOR 0B
chcp 65001 > nul

cd /d "%~dp0"

echo ======================================================================
echo             ATTENDAI -- VIT ATTENDANCE DIGITIZATION SYSTEM
echo ======================================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment 'venv' not found!
    echo Please create it first by running: python -m venv venv
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%~dp0"

call venv\Scripts\activate.bat

echo [*] Starting FastAPI Backend on http://127.0.0.1:8000 ...
start "AttendAI Backend (FastAPI)" cmd /k "title AttendAI Backend (FastAPI) && cd /d "%~dp0" && call venv\Scripts\activate.bat && python -m uvicorn backend.main:app --reload --port 8000"

timeout /t 3 /nobreak > nul

echo [*] Starting Streamlit Academic Dashboard on http://localhost:8501 ...
start "AttendAI Frontend (Streamlit)" cmd /k "title AttendAI Frontend (Streamlit) && cd /d "%~dp0" && call venv\Scripts\activate.bat && python -m streamlit run frontend\app.py --server.port 8501"

echo.
echo ======================================================================
echo  Both Backend and Frontend are launching in separate windows!
echo  - API Docs:   http://127.0.0.1:8000/docs
echo  - Dashboard:  http://localhost:8501
echo ======================================================================
echo.
pause

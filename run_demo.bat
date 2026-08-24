@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python runtime not found at .venv\Scripts\python.exe
  pause
  exit /b 1
)

echo Starting Digital Trust Shield demo server...
start "Digital Trust Shield Demo Server" ".venv\Scripts\python.exe" app.py

timeout /t 2 >nul
start "" "http://127.0.0.1:5000/demo"

echo Demo launched at http://127.0.0.1:5000/demo
endlocal

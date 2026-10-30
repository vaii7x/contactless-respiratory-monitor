@echo off
cd /d "%~dp0"
if not exist "frontend\node_modules" (echo Run setup.bat first.& pause& exit /b 1)
cd frontend
call npm run dev
pause

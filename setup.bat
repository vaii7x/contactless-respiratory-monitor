
@echo off
cd /d "%~dp0"

echo Setting up PhaseBreathe...

python --version
if errorlevel 1 (
    echo Python was not found.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js and npm are required. Install Node.js LTS first.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)
if errorlevel 1 goto fail

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail

".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto fail

cd frontend
call npm install
if errorlevel 1 goto fail

cd ..
echo.
echo Setup completed successfully!
pause
exit /b 0

:fail
echo Setup failed. Check the error above.
pause
exit /b 1
@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo FAIL - Run setup.bat to create the project environment.
    exit /b 1
)
".venv\Scripts\python.exe" -I "game\tools\launch.py" test %*
exit /b %errorlevel%

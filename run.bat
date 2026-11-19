@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1
set "HARBOR_PYTHON=.venv\portable\python.exe"
if not exist "%HARBOR_PYTHON%" set "HARBOR_PYTHON=.venv\Scripts\python.exe"
if not exist "%HARBOR_PYTHON%" (
    echo FAIL - Run setup.bat to create the project runtime.
    exit /b 1
)
"%HARBOR_PYTHON%" -I "game\tools\launch.py" run %*
exit /b %errorlevel%

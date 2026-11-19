@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1
set "HARBOR_PYTHON="
set "HARBOR_PY_CHECK=import sys, sysconfig; raise SystemExit(sys.version_info[:2] not in ((3, 12), (3, 11)) or sysconfig.get_platform() != 'win-amd64')"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "%HARBOR_PY_CHECK%" >nul 2>&1
    if not errorlevel 1 goto existing
)

py -3.12-64 -c "%HARBOR_PY_CHECK%" >nul 2>&1
if not errorlevel 1 goto launcher312
call :find_python 12
if defined HARBOR_PYTHON goto standalone
py -3.11-64 -c "%HARBOR_PY_CHECK%" >nul 2>&1
if not errorlevel 1 goto launcher311
call :find_python 11
if defined HARBOR_PYTHON goto standalone

echo FAIL - Harbor City needs x86-64 Python 3.12 or 3.11 for Windows.
echo Install it for your user from https://www.python.org/downloads/windows/ with the Python launcher enabled, then reopen setup.bat.
if "%~1" == "" pause
exit /b 1

:existing
".venv\Scripts\python.exe" "game\tools\launch.py" setup
goto report

:launcher312
py -3.12-64 "game\tools\launch.py" setup
goto report

:launcher311
py -3.11-64 "game\tools\launch.py" setup
goto report

:standalone
"%HARBOR_PYTHON%" "game\tools\launch.py" setup
goto report

:report
set "HARBOR_STATUS=%errorlevel%"
if not "%HARBOR_STATUS%" == "0" echo See logs\setup.log for setup diagnostics.
if "%~1" == "" pause
exit /b %HARBOR_STATUS%

:find_python
call :try_python "%LocalAppData%\Programs\Python\Python3%~1\python.exe" "%~1"
if defined HARBOR_PYTHON exit /b 0
for /f "delims=" %%P in ('where python.exe 2^>nul') do call :try_python "%%P" "%~1"
exit /b 0

:try_python
if defined HARBOR_PYTHON exit /b 0
if not exist "%~1" exit /b 0
if /i "%~dp1" == "%LocalAppData%\Microsoft\WindowsApps\" exit /b 0
"%~1" -c "import sys, sysconfig; raise SystemExit(sys.version_info[:2] != (3, %~2) or sysconfig.get_platform() != 'win-amd64')" >nul 2>&1
if not errorlevel 1 set "HARBOR_PYTHON=%~1"
exit /b 0

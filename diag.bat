@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "game\tools\windows_bootstrap.ps1" -Diagnostics
set "HARBOR_STATUS=%errorlevel%"
if "%~1" == "" pause
exit /b %HARBOR_STATUS%

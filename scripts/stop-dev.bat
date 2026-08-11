@echo off
REM scripts/stop-dev.bat
REM Manually stop ComfyChat dev servers started by start-dev.bat.
REM Delegates to _job-helper.ps1 PreFlight: kills recorded PID trees,
REM deletes .dev-pids.json, and belt-and-suspenders frees both dev ports
REM (reading BACKEND_PORT / FRONTEND_PORT from .env).

setlocal
set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd >nul

if not exist "%REPO_ROOT%\storage\tmp\.dev-pids.json" echo No PID file. Running cleanup anyway (frees ports if occupied).

echo Stopping ComfyChat dev servers...
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\_job-helper.ps1" -Command PreFlight -RepoRoot "%REPO_ROOT%"

echo Done.
endlocal

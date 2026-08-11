@echo off
REM scripts/start-dev.bat
REM Start ComfyChat backend + frontend with Job-Object reaping on exit.

setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd >nul

set "WAIT_SECONDS=25"

:parse_args
if "%~1"=="" goto after_parse
if /i "%~1"=="-WaitSeconds" (
    set "WAIT_SECONDS=%~2"
    shift
    shift
    goto parse_args
)
echo Unknown argument: %~1
exit /b 1

:after_parse

REM Preflight file checks
if not exist "%REPO_ROOT%\backend\.venv\Scripts\python.exe" (
    echo [X] backend\.venv\ missing. Run setup from README.md first.
    exit /b 1
)
if not exist "%REPO_ROOT%\frontend\node_modules" (
    echo [X] frontend\node_modules\ missing. Run 'cd frontend ^&^& npm install' first.
    exit /b 1
)
if not exist "%REPO_ROOT%\storage\tmp" mkdir "%REPO_ROOT%\storage\tmp" 2>nul

echo ==^> Pre-flight
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\_job-helper.ps1" -Command PreFlight -RepoRoot "%REPO_ROOT%"
if errorlevel 1 exit /b 1

echo ==^> Starting backend + frontend (Ctrl+C to stop)
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\_job-helper.ps1" -Command RunServersAndWait -RepoRoot "%REPO_ROOT%" -WaitSeconds %WAIT_SECONDS%
if errorlevel 1 exit /b 1

endlocal

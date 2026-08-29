@echo off
REM AEGIS-Market local development: the analysis backend and the interface, together.
REM
REM Two processes, because they are two things. The Python service holds the research
REM code and the data; the Next.js app holds the interface and proxies to it. Running the
REM app alone is a supported state — it serves stored, provenance-stamped results and says
REM so — but nothing computes on request without the backend.
REM
REM   backend   http://127.0.0.1:8787   python -m backend.server
REM   frontend  http://localhost:3000   npm run dev
REM
REM Usage:  run_dev.bat            start both
REM         run_dev.bat backend    start only the analysis backend
REM         run_dev.bat frontend   start only the interface

setlocal
cd /d "%~dp0"

if "%AEGIS_BACKEND_PORT%"=="" set AEGIS_BACKEND_PORT=8787
if "%AEGIS_BACKEND_URL%"=="" set AEGIS_BACKEND_URL=http://127.0.0.1:%AEGIS_BACKEND_PORT%

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

if /I "%~1"=="backend" goto backend_only
if /I "%~1"=="frontend" goto frontend_only

echo [aegis] starting the analysis backend on port %AEGIS_BACKEND_PORT%
start "aegis backend" cmd /k "%PYTHON% -m backend.server --port %AEGIS_BACKEND_PORT%"

echo [aegis] starting the interface on http://localhost:3000
echo [aegis] AEGIS_BACKEND_URL=%AEGIS_BACKEND_URL%
call npm run dev
goto :eof

:backend_only
echo [aegis] analysis backend only, port %AEGIS_BACKEND_PORT%
"%PYTHON%" -m backend.server --port %AEGIS_BACKEND_PORT%
goto :eof

:frontend_only
echo [aegis] interface only. Without a backend, pages serve stored results labelled
echo         VERIFIED_ARTIFACT and report that live execution is unavailable.
call npm run dev
goto :eof
